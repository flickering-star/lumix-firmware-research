/* Bounded, experimental GM1 service-USB read probe.
 *
 * The packet format and read operations come from retained FZ30/GH2 analysis,
 * NOT decoded GM1 firmware. A descriptor match alone proves no read semantics.
 * See docs/gm1-usb-service.md for the evidence and limits.
 *
 * inspect: registry only; access: open interface and inspect pipes, no requests.
 * settings: 16 fixed-area words containing public manufacturer/model markers.
 * flash: settings first, then 32 words at GH2's program-relative index zero.
 * block: settings first, then one 1024-byte absolute program read at 0x40000000.
 * window: two 8 KiB reads, second in reverse block order, requiring equality.
 * program: acquire the 9 MiB main-program interval described by GM1's update.
 * resume: preserve a verified prefix, compare three live anchors, then continue.
 * initializer: read the 32 KiB flash window enclosing the traced RAM initializer.
 * secondary-window/secondary: read 64 KiB / 3.375 MiB of the traced program2.
 * secondary-data: read the 18 KiB window enclosing program2's RAM initializer.
 * resume-secondary: preserve and resume a verified program2 prefix.
 * selftest: offline framing/integrity checks; does not enumerate USB.
 *
 * No reset, seize, detach, configuration/alternate-setting change, settings
 * write, flash write, arbitrary opcode, arbitrary address, or automatic retry.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/usb/IOUSBLib.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

#ifdef PROBE_GM5
#define PROBE_MODEL "DMC-GM5"
#ifdef PROBE_GM5_FULL_NOR
#define PROBE_MAIN_BYTES (32 * 1024 * 1024)
#else
#define PROBE_MAIN_BYTES (8 * 1024 * 1024)
#endif
#define PROBE_INITIALIZER_OFFSET 0x643800
#else
#define PROBE_MODEL "DMC-GM1"
#define PROBE_MAIN_BYTES (9 * 1024 * 1024)
#define PROBE_INITIALIZER_OFFSET 0x5a3800
#endif

enum { FRAME_BYTES = 16, BLOCK_BYTES = 1024, BLOCK_FRAME_BYTES = 1030,
       PROGRAM_BYTES = PROBE_MAIN_BYTES, SECONDARY_BYTES = 0x360000,
       SECONDARY_FIRST_BLOCK = 0x1400000 / BLOCK_BYTES,
       BLOCK_DELAY_MS = 100, TIMEOUT_MS = 1500 };
static FILE *events;
static unsigned control_attempts, bulk_write_attempts, valid_words;
static unsigned settings_bytes, flash_bytes;
static unsigned block_bytes;
static const char *resume_prefix_path;
static unsigned resume_input_bytes, copied_prefix_bytes, resume_anchor_blocks;
static bool interface_opened, markers_match;
#ifdef PROBE_RAM_CONTROL_TEST
static bool gm5_ram_toggle_test(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe,
                                UInt8 in_pipe, const char *directory);
#endif
#ifdef PROBE_CUSTOM_ACTION
static bool probe_custom_action(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe,
                                 UInt8 in_pipe, const char *directory);
#endif

static void api_result(const char *step, IOReturn result) {
    fprintf(events, "{\"event\":\"api_result\",\"step\":\"%s\","
            "\"result\":\"0x%08x\"}\n", step, (unsigned)result);
    fflush(events);
    if (result) fprintf(stderr, "%s failed: 0x%08x\n", step, (unsigned)result);
}

static void packet_event(const char *kind, const uint8_t *p, size_t n) {
    fprintf(events, "{\"event\":\"%s\",\"bytes\":%zu,\"hex\":\"", kind, n);
    for (size_t i = 0; i < n; ++i) fprintf(events, "%02x", p[i]);
    fprintf(events, "\"}\n");
    fflush(events);
}

static uint8_t frame_checksum(const uint8_t *p, size_t size) {
    uint8_t sum = 0;
    for (size_t i = 1; i < size - 2; ++i) sum = (uint8_t)(sum + p[i]);
    return sum;
}

static uint8_t checksum(const uint8_t *p) { return frame_checksum(p, FRAME_BYTES); }

static bool block_request(uint8_t p[BLOCK_FRAME_BYTES], uint32_t start) {
    /* Main interval from the retained GM1 update; program2 is corroborated by
     * the physically read startup copy. This is not a whole flash map.
     */
    bool main = start >= 0x40000000 && start < 0x40000000 + PROGRAM_BYTES;
    bool secondary = start >= 0x41400000 && start < 0x41400000 + SECONDARY_BYTES;
    bool runtime_control = false;
#ifdef PROBE_GM5
    runtime_control = start == 0x70a68400 || start == 0x702ff800 || start == 0x701f9400
        || start == 0x701af000 || start == 0x70a0f000 || start == 0x70a67800
        || (start >= 0x7bfb0000 && start < 0x7bfb4800);
#endif
    if ((!main && !secondary && !runtime_control) || start % BLOCK_BYTES) return false;
    memset(p, 0, BLOCK_FRAME_BYTES);
    p[0] = 1; /* GH2 class-one request, not the type-eight word-read frame. */
    p[2] = 0xff;
    p[3] = 0x5c;
    uint32_t end = start + BLOCK_BYTES;
    for (unsigned i = 0; i < 4; ++i) {
        p[4 + i] = (uint8_t)(start >> (8 * i));
        p[8 + i] = (uint8_t)(end >> (8 * i));
    }
    p[BLOCK_FRAME_BYTES - 2] = frame_checksum(p, BLOCK_FRAME_BYTES);
    return true;
}

static bool block_response(const uint8_t *p, size_t n, uint8_t out[BLOCK_BYTES]) {
    if (n != BLOCK_FRAME_BYTES || p[0] != 1 || p[1] != 0 || p[2] != 0xff ||
        p[3] != 5 || p[n - 2] != frame_checksum(p, n) || p[n - 1] != 0) return false;
    memcpy(out, p + 4, BLOCK_BYTES);
    return true;
}

static bool request_packet(uint8_t p[FRAME_BYTES], uint8_t operation, uint32_t index) {
    memset(p, 0, FRAME_BYTES);
    /* Bounds are intentionally narrower than the GH2 handlers' addressing. */
    if (operation == 0x38) {
        if (index < 0x3f80 || index >= 0x3f90) return false;
        p[4] = (uint8_t)index;
        p[5] = (uint8_t)(index >> 8);
        p[6] = 0x20; /* fixed adjustment area */
    } else if (operation == 0x70) {
        if (index >= 32) return false;
        p[4] = (uint8_t)index;
    } else return false;
    p[0] = 8;
    p[2] = 0xff; /* sequence zero and its complement */
    p[3] = operation;
    p[14] = checksum(p);
    return true;
}

static bool response_word(const uint8_t *p, size_t n, uint8_t out[2]) {
    if (n != FRAME_BYTES || p[0] != 8 || p[1] != 0 || p[2] != 0xff ||
        p[3] != 0x36 || p[14] != checksum(p) || p[15] != 0) return false;
    /* GH2's two-byte success response zero-fills bytes six through thirteen. */
    for (unsigned i = 6; i <= 13; ++i) if (p[i]) return false;
    out[0] = p[4];
    out[1] = p[5];
    return true;
}

static int selftest(void) {
    uint8_t p[FRAME_BYTES], out[2];
    const uint8_t settings_golden[FRAME_BYTES] = {
        8, 0, 0xff, 0x38, 0x80, 0x3f, 0x20, 0, 0, 0, 0, 0, 0, 0, 0x16, 0};
    const uint8_t flash_golden[FRAME_BYTES] = {
        8, 0, 0xff, 0x70, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x6f, 0};
    /* A Pa word response in the independently reviewed GH2 response format. */
    const uint8_t reply[FRAME_BYTES] = {
        8, 0, 0xff, 0x36, 0x50, 0x61, 0, 0, 0, 0, 0, 0, 0, 0, 0xe6, 0};
    if (!request_packet(p, 0x38, 0x3f80) || memcmp(p, settings_golden, sizeof p) ||
        !request_packet(p, 0x70, 0) || memcmp(p, flash_golden, sizeof p) ||
        request_packet(p, 0x39, 0x3f80) || request_packet(p, 0x38, 0x3f7f) ||
        request_packet(p, 0x38, 0x3f90) || request_packet(p, 0x70, 32) ||
        request_packet(p, 0x70, UINT32_MAX) ||
        !response_word(reply, sizeof reply, out) || out[0] != 'P' || out[1] != 'a')
        return 1;
    for (size_t n = 0; n < FRAME_BYTES; ++n)
        if (response_word(reply, n, out)) return 1;
    if (response_word(reply, FRAME_BYTES + 1, out)) return 1;
    /* Reject every single-bit corruption, including data/checksum/trailer. */
    for (unsigned i = 0; i < FRAME_BYTES; ++i) {
        for (unsigned bit = 0; bit < 8; ++bit) {
            memcpy(p, reply, sizeof p);
            p[i] ^= (uint8_t)(1u << bit);
            if (response_word(p, sizeof p, out)) return 1;
        }
    }
    memcpy(p, reply, sizeof p);
    p[3] = 1; /* syntactically intact error/status response */
    p[14] = checksum(p);
    if (response_word(p, sizeof p, out)) return 1;
    memcpy(p, reply, sizeof p);
    p[6] = 1; /* intact checksum but unexpected payload layout */
    p[14] = checksum(p);
    if (response_word(p, sizeof p, out)) return 1;
    uint8_t large[BLOCK_FRAME_BYTES], block[BLOCK_BYTES];
    const uint8_t large_header[] = {1, 0, 0xff, 0x5c, 0, 0, 0, 0x40, 0, 4, 0, 0x40};
    if (!block_request(large, 0x40000000) ||
        memcmp(large, large_header, sizeof large_header) ||
        large[BLOCK_FRAME_BYTES - 2] != 0xdf || large[BLOCK_FRAME_BYTES - 1] ||
        !block_request(large, 0x40000000 + PROGRAM_BYTES - BLOCK_BYTES) ||
        !block_request(large, 0x41400000) || !block_request(large, 0x4175fc00) ||
        block_request(large, 0x3ffffc00) || block_request(large, 0x40000000 + PROGRAM_BYTES) ||
        block_request(large, 0x40000002) || block_request(large, UINT32_MAX)) return 1;
#ifdef PROBE_GM5_FULL_NOR
    if (!block_request(large, 0x413ffc00) || !block_request(large, 0x41760000)
        || !block_request(large, 0x41fffc00) || block_request(large, 0x42000000)) return 1;
#else
    if (block_request(large, 0x413ffc00) || block_request(large, 0x41760000)) return 1;
#endif
#ifdef PROBE_GM5
    if (!block_request(large, 0x701f9400) || block_request(large, 0x701f9000)
        || block_request(large, 0x701f9800)) return 1;
#else
    if (block_request(large, 0x701f9400)) return 1;
#endif
    memset(large, 0, sizeof large);
    large[0] = 1; large[2] = 0xff; large[3] = 5;
    for (unsigned i = 0; i < BLOCK_BYTES; ++i) large[4 + i] = (uint8_t)i;
    large[BLOCK_FRAME_BYTES - 2] = 4; /* independent sum of repeating 0..255 */
    if (!block_response(large, sizeof large, block) || block[0] || block[1023] != 255) return 1;
    for (size_t n = 0; n < sizeof large; ++n)
        if (block_response(large, n, block)) return 1;
    if (block_response(large, sizeof large + 1, block)) return 1;
    for (unsigned i = 0; i < sizeof large; ++i) {
        for (unsigned bit = 0; bit < 8; ++bit) {
            large[i] ^= (uint8_t)(1u << bit);
            if (block_response(large, sizeof large, block)) return 1;
            large[i] ^= (uint8_t)(1u << bit);
        }
    }
    puts("Offline word/block framing tests passed (golden packets, bounds, truncations, corruptions, error responses).");
    return 0;
}

static int registry_number(io_service_t service, CFStringRef key) {
    CFTypeRef value = IORegistryEntryCreateCFProperty(service, key, kCFAllocatorDefault, 0);
    int result = -1;
    if (value && CFGetTypeID(value) == CFNumberGetTypeID())
        CFNumberGetValue(value, kCFNumberIntType, &result);
    if (value) CFRelease(value);
    return result;
}

static bool is_gm1_service(io_service_t service) {
    CFTypeRef name = IORegistryEntryCreateCFProperty(
        service, CFSTR("USB Product Name"), kCFAllocatorDefault, 0);
    bool matches = name && CFGetTypeID(name) == CFStringGetTypeID() &&
        CFEqual(name, CFSTR(PROBE_MODEL));
    if (name) CFRelease(name);
    return matches && registry_number(service, CFSTR("idVendor")) == 0x04da &&
        registry_number(service, CFSTR("idProduct")) == 0x2370 &&
        registry_number(service, CFSTR("bInterfaceClass")) == 0xff &&
        registry_number(service, CFSTR("bInterfaceSubClass")) == 0xa0 &&
        registry_number(service, CFSTR("bInterfaceProtocol")) == 0xb0 &&
        registry_number(service, CFSTR("bConfigurationValue")) == 1 &&
        registry_number(service, CFSTR("bInterfaceNumber")) == 0 &&
        registry_number(service, CFSTR("bAlternateSetting")) == 0 &&
        registry_number(service, CFSTR("bNumEndpoints")) == 3;
}

static io_service_t find_interface(void) {
    io_iterator_t iterator = IO_OBJECT_NULL;
    IOReturn result = IOServiceGetMatchingServices(kIOMainPortDefault,
        IOServiceMatching("IOUSBHostInterface"), &iterator);
    api_result("enumerate_interfaces", result);
    if (result) return IO_OBJECT_NULL;
    io_service_t selected = IO_OBJECT_NULL, service;
    unsigned matches = 0;
    while ((service = IOIteratorNext(iterator))) {
        if (is_gm1_service(service)) {
            ++matches;
            if (!selected) { selected = service; continue; }
        }
        IOObjectRelease(service);
    }
    IOObjectRelease(iterator);
    fprintf(events, "{\"event\":\"matching_interfaces\",\"count\":%u}\n", matches);
    fflush(events);
    if (matches != 1) {
        fprintf(stderr, "Expected exactly one " PROBE_MODEL " service interface; found %u.\n", matches);
        if (selected) IOObjectRelease(selected);
        return IO_OBJECT_NULL;
    }
    fprintf(events, "{\"event\":\"registry_identity\",\"product_name\":\"" PROBE_MODEL "\","
            "\"vendor_id\":1242,\"product_id\":9072,\"interface\":[255,160,176],"
            "\"configuration\":1,\"alternate_setting\":0,\"endpoints\":3}\n");
    fflush(events);
    return selected;
}

static bool prepare(IOUSBInterfaceInterface300 **usb, UInt16 index) {
    IOUSBDevRequestTO request = {0};
    request.bmRequestType = 0x40;
    request.bRequest = 0;
    request.wValue = 0;
    request.wIndex = index;
    request.wLength = 0;
    request.noDataTimeout = TIMEOUT_MS;
    request.completionTimeout = TIMEOUT_MS;
    ++control_attempts;
    fprintf(events, "{\"event\":\"control_attempt\",\"setup_hex\":\"40000000%02x000000\"}\n", index);
    fflush(events);
    IOReturn result = (*usb)->ControlRequestTO(usb, 0, &request);
    api_result(index ? "prepare_bulk_in" : "prepare_bulk_out", result);
    return result == kIOReturnSuccess;
}

static bool send_request(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe,
                         uint8_t *tx, UInt32 size, unsigned delay_ms) {
    if (!prepare(usb, 0)) return false;
    packet_event("bulk_out_attempt", tx, size);
    ++bulk_write_attempts;
    IOReturn result = (*usb)->WritePipeTO(usb, out_pipe, tx, size, TIMEOUT_MS, TIMEOUT_MS);
    api_result("bulk_out", result);
    if (result) return false;
    if (delay_ms) {
        struct timespec delay = {.tv_sec = delay_ms / 1000,
                                 .tv_nsec = (long)(delay_ms % 1000) * 1000000};
        while (nanosleep(&delay, &delay) && errno == EINTR) {}
    }
    return true;
}

static bool receive_frame(IOUSBInterfaceInterface300 **usb, UInt8 in_pipe,
                          uint8_t expected_type, uint8_t *rx, UInt32 capacity) {
    if (!prepare(usb, 1)) return false;
    /* FZ30's 0x40ca2c first reads one type byte, then prepares another read
     * for the entire frame (including its type byte), not the remaining 15.
     * The first GM1 observation independently returned exactly that type byte.
     */
    UInt32 length = 1;
    IOReturn result = (*usb)->ReadPipeTO(usb, in_pipe, rx, &length, TIMEOUT_MS, TIMEOUT_MS);
    api_result("bulk_in_type", result);
    /* IOUSBLib documents length/data as invalid on a failed timed read. */
    if (result) return false;
    packet_event("bulk_in_type", rx, length <= capacity ? length : capacity);
    if (length != 1 || rx[0] != expected_type) {
        fprintf(stderr, "Unexpected response type; stopped without retrying.\n");
        return false;
    }
    if (!prepare(usb, 1)) return false;
    memset(rx, 0, capacity);
    length = capacity;
    result = (*usb)->ReadPipeTO(usb, in_pipe, rx, &length, TIMEOUT_MS, TIMEOUT_MS);
    api_result("bulk_in_frame", result);
    if (result) return false;
    packet_event("bulk_in", rx, length <= capacity ? length : capacity);
    if (length != capacity) {
        fprintf(stderr, "Unexpected response length; stopped without retrying.\n");
        return false;
    }
    return true;
}

static bool read_word(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe, UInt8 in_pipe,
                      uint8_t operation, uint32_t index, uint8_t out[2]) {
    uint8_t tx[FRAME_BYTES], rx[FRAME_BYTES] = {0};
    if (!request_packet(tx, operation, index) || !send_request(usb, out_pipe, tx, sizeof tx, 100) ||
        !receive_frame(usb, in_pipe, 8, rx, sizeof rx)) return false;
    if (!response_word(rx, sizeof rx, out)) {
        fprintf(stderr, "Unexpected reply; stopped without retrying. Inspect events.jsonl.\n");
        return false;
    }
    ++valid_words;
    return true;
}

static FILE *new_file(const char *directory, const char *name) {
    char path[4096];
    int n = snprintf(path, sizeof path, "%s/%s", directory, name);
    if (n < 0 || (size_t)n >= sizeof path) return NULL;
    return fopen(path, "wx");
}

static bool read_program_block(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe,
                               UInt8 in_pipe, unsigned index, uint8_t data[BLOCK_BYTES]) {
    uint8_t tx[BLOCK_FRAME_BYTES], rx[BLOCK_FRAME_BYTES];
    return block_request(tx, 0x40000000 + BLOCK_BYTES * index) &&
        send_request(usb, out_pipe, tx, sizeof tx, BLOCK_DELAY_MS) &&
        receive_frame(usb, in_pipe, 1, rx, sizeof rx) &&
        block_response(rx, sizeof rx, data);
}

static bool read_program_blocks(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe,
                                UInt8 in_pipe, const char *directory, const char *name,
                                unsigned file_base_block, unsigned first_block, unsigned blocks, bool reverse,
                                uint8_t *comparison, const char *prefix_path) {
    uint8_t data[BLOCK_BYTES];
    FILE *file = new_file(directory, name);
    if (!file) { perror("Create program-block sample"); return false; }
    bool ok = true;
    if (prefix_path) {
        FILE *source = fopen(prefix_path, "rb");
        if (!source) { perror("Read resume prefix"); ok = false; goto finish; }
        unsigned prefix_blocks = resume_input_bytes / BLOCK_BYTES;
        if (first_block != file_base_block + prefix_blocks) {
            fclose(source); ok = false; goto finish;
        }
        for (unsigned n = 0; n < prefix_blocks; ++n) {
            if (fread(data, 1, BLOCK_BYTES, source) != BLOCK_BYTES ||
                fwrite(data, 1, BLOCK_BYTES, file) != BLOCK_BYTES) { ok = false; break; }
            copied_prefix_bytes += BLOCK_BYTES;
        }
        if (ok && (fgetc(source) != EOF || ferror(source) || fflush(file))) ok = false;
        if (!ok) { fclose(source); goto finish; }
        fprintf(events, "{\"event\":\"resume_prefix\",\"bytes\":%u}\n", copied_prefix_bytes);
        fflush(events);
        unsigned anchors[] = {0, prefix_blocks / 2, prefix_blocks - 1};
        for (unsigned n = 0; n < 3; ++n) {
            if ((n > 0 && anchors[n] == anchors[0]) || (n > 1 && anchors[n] == anchors[1])) continue;
            uint8_t expected[BLOCK_BYTES];
            unsigned relative_index = anchors[n], index = file_base_block + relative_index;
            if (fseek(source, (long)relative_index * BLOCK_BYTES, SEEK_SET) ||
                fread(expected, 1, BLOCK_BYTES, source) != BLOCK_BYTES ||
                !read_program_block(usb, out_pipe, in_pipe, index, data) ||
                memcmp(expected, data, BLOCK_BYTES)) {
                fprintf(stderr, "Resume anchor failed at 0x%08x; no new program blocks appended.\n",
                        0x40000000 + index * BLOCK_BYTES);
                ok = false; break;
            }
            ++resume_anchor_blocks;
            fprintf(events, "{\"event\":\"resume_anchor\",\"block\":%u,\"match\":true}\n", index);
            fflush(events);
        }
        fclose(source);
        if (!ok) goto finish;
        printf("Resume anchors match; continuing at 0x%08x after %u preserved bytes.\n",
                0x40000000 + first_block * BLOCK_BYTES, copied_prefix_bytes);
        fflush(stdout);
    }
    for (unsigned n = 0; n < blocks; ++n) {
        unsigned index = first_block + (reverse ? blocks - 1 - n : n);
        unsigned file_index = index - file_base_block;
        uint32_t start = 0x40000000 + BLOCK_BYTES * index;
        if (!read_program_block(usb, out_pipe, in_pipe, index, data)) { ok = false; break; }
        if (comparison) {
            if (reverse && memcmp(comparison + BLOCK_BYTES * file_index, data, BLOCK_BYTES)) {
                fprintf(stderr, "Repeated block differs at 0x%08x; stopped.\n", start);
                ok = false; break;
            }
            if (!reverse) memcpy(comparison + BLOCK_BYTES * file_index, data, BLOCK_BYTES);
        }
        if (fseek(file, (long)BLOCK_BYTES * file_index, SEEK_SET) ||
            fwrite(data, 1, sizeof data, file) != sizeof data || fflush(file)) {
            ok = false; break;
        }
        block_bytes += sizeof data;
        if ((n + 1) % 256 == 0 || n + 1 == blocks) {
            printf("Read %u / %u program blocks%s.\n", n + 1, blocks, reverse ? " (reverse verification)" : "");
            fflush(stdout);
        }
    }
finish:
    if (fclose(file)) ok = false;
    if (!ok) fprintf(stderr, "Program-block sample stopped; inspect events.jsonl.\n");
    return ok;
}

static bool read_sample(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe, UInt8 in_pipe,
                        const char *directory, bool flash) {
    unsigned count = flash ? 32 : 16;
    uint8_t data[64] = {0};
    FILE *file = new_file(directory, flash ? "flash-prefix.bin" : "fixed-markers.bin");
    if (!file) { perror("Create sample"); return false; }
    bool ok = true;
    for (unsigned i = 0; i < count; ++i) {
        uint8_t word[2];
        if (!read_word(usb, out_pipe, in_pipe, flash ? 0x70 : 0x38,
                       flash ? i : 0x3f80 + i, word)) { ok = false; break; }
        memcpy(data + 2 * i, word, 2);
        if (fwrite(word, 1, 2, file) != 2 || fflush(file)) { ok = false; break; }
        if (flash) flash_bytes += 2; else settings_bytes += 2;
    }
    if (fclose(file)) ok = false;
    if (ok && !flash) {
#ifdef PROBE_GM5
        /* Repeated control from this body, not a manufacturer/model marker.
         * GM1's marker coordinates differ on GM5. Exact registry identity is
         * still mandatory; retain the failed first comparison separately.
         */
        const uint8_t gm5_control[32] = {
            0x81,0,0x58,0,2,0,0x81,0,0x58,0,2,0,0x2c,0,0x18,0,
            2,0,0x2c,0,0x18,0,2,0,0,0,2,0,0,0,0,0};
        bool control_match = !memcmp(data, gm5_control, sizeof gm5_control);
        fprintf(events, "{\"event\":\"gm5_settings_control\",\"matches_prior_body_sample\":%s,"
                "\"model_markers_verified\":false}\n", control_match ? "true" : "false");
        fflush(events);
        if (!control_match) {
            fprintf(stderr, "GM5 settings control changed; stopped.\n");
            ok = false;
        }
#else
        markers_match = !memcmp(data, "Panasonic\0", 10) &&
                        !memcmp(data + 16, PROBE_MODEL "\0", 8);
        fprintf(events, "{\"event\":\"fixed_markers\",\"manufacturer_and_model_match\":%s}\n",
                markers_match ? "true" : "false");
        fflush(events);
        if (!markers_match) {
            fprintf(stderr, "Marker bytes differ from the expected " PROBE_MODEL "; stopped.\n");
            ok = false;
        }
#endif
    }
    return ok;
}

static int probe(const char *mode, const char *directory) {
    io_service_t service = find_interface();
    if (!service) return 1;
    if (!strcmp(mode, "inspect")) { IOObjectRelease(service); return 0; }
    IOCFPlugInInterface **plugin = NULL;
    IOUSBInterfaceInterface300 **usb = NULL;
    SInt32 score = 0;
    IOReturn result = IOCreatePlugInInterfaceForService(service,
        kIOUSBInterfaceUserClientTypeID, kIOCFPlugInInterfaceID, &plugin, &score);
    IOObjectRelease(service);
    api_result("create_interface_user_client", result);
    if (result || !plugin) {
        if (plugin) (*plugin)->Release(plugin);
        return 1;
    }
    HRESULT query = (*plugin)->QueryInterface(plugin,
        CFUUIDGetUUIDBytes(kIOUSBInterfaceInterfaceID300), (LPVOID *)&usb);
    (*plugin)->Release(plugin);
    api_result("query_interface_300", (IOReturn)query);
    if (query != S_OK || !usb) return 1;
    int status = 1;
    result = (*usb)->USBInterfaceOpen(usb);
    api_result("open_interface", result);
    if (result) goto cleanup;
    interface_opened = true;
    UInt8 count = 0, out_pipe = 0, in_pipe = 0;
    unsigned interrupt_count = 0;
    result = (*usb)->GetNumEndpoints(usb, &count);
    api_result("get_endpoints", result);
    if (result || count != 3) goto cleanup;
    for (UInt8 pipe = 1; pipe <= count; ++pipe) {
        UInt8 direction = 0, number = 0, type = 0, interval = 0;
        UInt16 size = 0;
        result = (*usb)->GetPipeProperties(usb, pipe, &direction, &number, &type, &size, &interval);
        api_result("get_pipe_properties", result);
        if (result) goto cleanup;
        fprintf(events, "{\"event\":\"pipe\",\"pipe_ref\":%u,\"direction\":%u,"
                "\"endpoint_number\":%u,\"transfer_type\":%u,\"max_packet\":%u,\"interval\":%u}\n",
                pipe, direction, number, type, size, interval);
        fflush(events);
        if (size != 64 && size != 512) goto cleanup;
        if (type == kUSBBulk && direction == kUSBOut && number == 1 && !out_pipe) out_pipe = pipe;
        else if (type == kUSBBulk && direction == kUSBIn && number == 2 && !in_pipe) in_pipe = pipe;
        else if (type == kUSBInterrupt && direction == kUSBIn && number == 3) ++interrupt_count;
        else goto cleanup;
    }
    if (!out_pipe || !in_pipe || interrupt_count != 1) goto cleanup;
    if (!strcmp(mode, "access")) { status = 0; goto cleanup; }
    if (!read_sample(usb, out_pipe, in_pipe, directory, false)) goto cleanup;
#ifdef PROBE_CUSTOM_ACTION
    status = probe_custom_action(usb, out_pipe, in_pipe, directory) ? 0 : 1;
    goto cleanup;
#endif
#ifdef PROBE_RAM_CONTROL_TEST
    if (!strcmp(mode, "ram-toggle-test")) {
        status = gm5_ram_toggle_test(usb, out_pipe, in_pipe, directory) ? 0 : 1;
        goto cleanup;
    }
#endif
    if (!strcmp(mode, "flash") && !read_sample(usb, out_pipe, in_pipe, directory, true)) goto cleanup;
    if (!strcmp(mode, "block") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "program-block.bin", 0, 0, 1, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "window")) {
        uint8_t comparison[8 * BLOCK_BYTES];
        if (!read_program_blocks(usb, out_pipe, in_pipe, directory, "program-window.bin", 0, 0, 8, false, comparison, NULL) ||
            !read_program_blocks(usb, out_pipe, in_pipe, directory, "program-window-repeat.bin", 0, 0, 8, true, comparison, NULL))
            goto cleanup;
    }
    if (!strcmp(mode, "program") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "program-main.bin",
                             0, 0, PROGRAM_BYTES / BLOCK_BYTES, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "initializer") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "ram-initializer.bin",
                             PROBE_INITIALIZER_OFFSET / BLOCK_BYTES,
                             PROBE_INITIALIZER_OFFSET / BLOCK_BYTES, 32, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "resume") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "program-main.bin",
                             0, resume_input_bytes / BLOCK_BYTES,
                             (PROGRAM_BYTES - resume_input_bytes) / BLOCK_BYTES,
                             false, NULL, resume_prefix_path)) goto cleanup;
    if ((!strcmp(mode, "secondary-window") || !strcmp(mode, "secondary")) &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory,
                             !strcmp(mode, "secondary-window") ? "program2-window.bin" : "program2.bin",
                             SECONDARY_FIRST_BLOCK, SECONDARY_FIRST_BLOCK,
                             !strcmp(mode, "secondary-window") ? 64 : SECONDARY_BYTES / BLOCK_BYTES,
                             false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "secondary-data") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "program2-data.bin",
                             0x16c3000 / BLOCK_BYTES, 0x16c3000 / BLOCK_BYTES,
                             18, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "resume-secondary") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "program2.bin",
                             SECONDARY_FIRST_BLOCK, SECONDARY_FIRST_BLOCK + resume_input_bytes / BLOCK_BYTES,
                             (SECONDARY_BYTES - resume_input_bytes) / BLOCK_BYTES,
                             false, NULL, resume_prefix_path)) goto cleanup;
#ifdef PROBE_GM5
    if (!strcmp(mode, "startup-data") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "startup-data.bin",
                             0x3000 / BLOCK_BYTES, 0x3000 / BLOCK_BYTES,
                             1, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "security-flag") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "security-flag.bin",
                             0x6b1800 / BLOCK_BYTES, 0x6b1800 / BLOCK_BYTES,
                             1, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "updater-window") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "updater-window.bin",
                             0x154e000 / BLOCK_BYTES, 0x154e000 / BLOCK_BYTES,
                             16, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "runtime-control") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "runtime-control.bin",
                             0x30a68400 / BLOCK_BYTES, 0x30a68400 / BLOCK_BYTES,
                             1, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "update-ui-state") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "update-ui-state.bin",
                             0x301f9400 / BLOCK_BYTES, 0x301f9400 / BLOCK_BYTES,
                             1, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "update-entry") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "update-entry.bin",
                             0x23b800 / BLOCK_BYTES, 0x23b800 / BLOCK_BYTES,
                             3, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "update-profile") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "update-profile.bin",
                             0x162a400 / BLOCK_BYTES, 0x162a400 / BLOCK_BYTES,
                             1, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "usb-handler") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "usb-handler.bin",
                             0x36c000 / BLOCK_BYTES, 0x36c000 / BLOCK_BYTES,
                             16, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "usb-state") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "usb-state.bin",
                             0x302ff800 / BLOCK_BYTES, 0x302ff800 / BLOCK_BYTES,
                             1, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "language-head") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "language-settings-head.bin",
                             0x3bfb0000 / BLOCK_BYTES, 0x3bfb0000 / BLOCK_BYTES,
                             1, false, NULL, NULL)) goto cleanup;
    if (!strcmp(mode, "update-settings") &&
        !read_program_blocks(usb, out_pipe, in_pipe, directory, "update-settings.bin",
                             0x3bfb0000 / BLOCK_BYTES, 0x3bfb0000 / BLOCK_BYTES,
                             18, false, NULL, NULL)) goto cleanup;
#endif
    status = 0;
cleanup:
    if (interface_opened) {
        result = (*usb)->USBInterfaceClose(usb);
        api_result("close_interface", result);
        if (result) status = 1;
    }
    (*usb)->Release(usb);
    return status;
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "selftest")) return selftest();
#ifdef PROBE_GM5
    /* Initial cross-model validation: no guessed initializer or long capture. */
    if (argc != 3 || (strcmp(argv[1], "inspect") && strcmp(argv[1], "access") &&
                     strcmp(argv[1], "settings") && strcmp(argv[1], "flash") &&
                     strcmp(argv[1], "block") && strcmp(argv[1], "window") &&
                     strcmp(argv[1], "initializer") && strcmp(argv[1], "startup-data") &&
                     strcmp(argv[1], "security-flag") && strcmp(argv[1], "updater-window") &&
                     strcmp(argv[1], "runtime-control") && strcmp(argv[1], "update-profile") &&
                     strcmp(argv[1], "usb-handler") && strcmp(argv[1], "usb-state") &&
                     strcmp(argv[1], "language-head") && strcmp(argv[1], "update-settings") &&
                     strcmp(argv[1], "update-ui-state") && strcmp(argv[1], "update-entry"))) {
        fprintf(stderr, "Unsupported bounded GM5 probe mode.\n");
        return 2;
    }
#endif
    if (argc == 4 && (!strcmp(argv[1], "resume") || !strcmp(argv[1], "resume-secondary"))) {
        struct stat prefix_stat;
        unsigned limit = !strcmp(argv[1], "resume-secondary") ? SECONDARY_BYTES : PROGRAM_BYTES;
        if (stat(argv[3], &prefix_stat) || !S_ISREG(prefix_stat.st_mode) ||
            prefix_stat.st_size <= 0 || prefix_stat.st_size > limit ||
            prefix_stat.st_size % BLOCK_BYTES) {
            fprintf(stderr, "Resume requires a nonempty, block-aligned prefix within the selected component.\n");
            return 2;
        }
        resume_prefix_path = argv[3];
        resume_input_bytes = (unsigned)prefix_stat.st_size;
    } else if (argc != 3 || (strcmp(argv[1], "inspect") && strcmp(argv[1], "access") &&
                     strcmp(argv[1], "settings") && strcmp(argv[1], "flash") && strcmp(argv[1], "block") &&
                     strcmp(argv[1], "window") && strcmp(argv[1], "program") && strcmp(argv[1], "initializer") &&
                     strcmp(argv[1], "secondary-window") && strcmp(argv[1], "secondary") &&
                     strcmp(argv[1], "secondary-data")
#ifdef PROBE_GM5
                     && strcmp(argv[1], "startup-data") && strcmp(argv[1], "security-flag")
                     && strcmp(argv[1], "updater-window") && strcmp(argv[1], "runtime-control")
                     && strcmp(argv[1], "update-profile") && strcmp(argv[1], "usb-handler")
                     && strcmp(argv[1], "usb-state")
                     && strcmp(argv[1], "language-head")
                     && strcmp(argv[1], "update-settings")
                     && strcmp(argv[1], "update-ui-state") && strcmp(argv[1], "update-entry")
#endif
                     )) {
        fprintf(stderr, "usage: gm1-usb-probe selftest | {inspect|access|settings|flash|block|window|program|initializer|secondary-window|secondary|secondary-data} NEW_OUTPUT_DIRECTORY | {resume|resume-secondary} NEW_OUTPUT_DIRECTORY VERIFIED_PREFIX_FILE\n");
        return 2;
    }
    if (mkdir(argv[2], 0700)) { perror("Create fresh output directory"); return 1; }
    events = new_file(argv[2], "events.jsonl");
    if (!events) { perror("Create event log"); return 1; }
    fprintf(events, "{\"event\":\"start\",\"mode\":\"%s\",\"epoch_utc\":%lld,\"block_delay_ms\":%u}\n",
            argv[1], (long long)time(NULL), BLOCK_DELAY_MS);
    fflush(events);
    int status = probe(argv[1], argv[2]);
    FILE *summary = new_file(argv[2], "summary.json");
    if (!summary) { perror("Create summary"); status = 1; }
    else {
        fprintf(summary, "{\n  \"schema\": 1,\n  \"model\": \"" PROBE_MODEL "\",\n  \"mode\": \"%s\",\n  \"exit_status\": %d,\n"
                "  \"interface_opened\": %s,\n  \"control_requests_attempted\": %u,\n"
                "  \"bulk_writes_attempted\": %u,\n  \"validated_word_responses\": %u,\n"
                "  \"settings_bytes\": %u,\n  \"settings_markers_match\": %s,\n"
                "  \"flash_prefix_bytes\": %u,\n  \"program_block_bytes\": %u,\n"
                "  \"copied_prefix_bytes\": %u,\n  \"resume_anchor_blocks\": %u\n}\n", argv[1], status,
                interface_opened ? "true" : "false", control_attempts, bulk_write_attempts,
                valid_words, settings_bytes, markers_match ? "true" : "false", flash_bytes, block_bytes,
                copied_prefix_bytes, resume_anchor_blocks);
        if (fclose(summary)) status = 1;
    }
    if (fclose(events)) status = 1;
    printf("Probe %s. Evidence: %s\n", status ? "stopped" : "completed", argv[2]);
    return status;
}
