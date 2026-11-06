/* Fixed GM5 English selection in its UPDATE settings shadow.
 * Exactly one op34 request: area10, word00dc, value0100. No bank commit,
 * region/calibration edit, firmware flash, reset or arbitrary write argument.
 */
#define PROBE_GM5
#define PROBE_CUSTOM_ACTION
#define main shared_language_read_main
#include "gm1_usb_probe_macos.c"
#undef main
#include <CommonCrypto/CommonDigest.h>

enum { UPDATE_BYTES = 18432, LANGUAGE_OFFSET = 0x1b8 };
static bool english_readback;
static bool language_inspect_only;
static bool ui_english_readback;
static unsigned ui_language_write_attempts;
static unsigned language_write_attempts, readback_differences;

static void language_request(uint8_t packet[16]) {
    const uint8_t fixed[16] = {8,0,255,0x34,0xdc,0,0,1,0x10,0,0,0,0,0,0x20,0};
    memcpy(packet,fixed,16);
}

static void ui_language_request(uint8_t packet[16]) {
    const uint8_t fixed[16] = {8,0,255,0x9c,0x38,0xf2,0x1a,0x70,0,1,0,0,0,0,0x50,0};
    memcpy(packet,fixed,16);
}

static bool language_ack(const uint8_t *packet, size_t length) {
    if (length != 16 || packet[0] != 8 || packet[1] || packet[2] != 255
        || packet[3] != 1 || packet[14] != checksum(packet) || packet[15]) return false;
    for (unsigned i = 4; i < 14; i++) if (packet[i]) return false;
    return true;
}

static int language_selftest(void) {
    uint8_t packet[16]; language_request(packet);
    if (packet[14] != checksum(packet) || packet[3] != 0x34 || packet[4] != 0xdc
        || packet[5] || packet[6] || packet[7] != 1 || packet[8] != 0x10) return 1;
    ui_language_request(packet);
    if (packet[14] != checksum(packet) || packet[3] != 0x9c || packet[8] || packet[9] != 1) return 1;
    const uint8_t ack[16] = {8,0,255,1,0,0,0,0,0,0,0,0,0,0,0,0};
    if (!language_ack(ack,16) || language_ack(ack,17)) return 1;
    for (size_t n = 0; n < 16; n++) if (language_ack(ack,n)) return 1;
    for (unsigned i = 0; i < 16; i++) for (unsigned bit = 0; bit < 8; bit++) {
        memcpy(packet,ack,16); packet[i] ^= (uint8_t)(1u << bit);
        if (language_ack(packet,16)) return 1;
    }
    puts("Fixed English request, ACK, truncation and corruption controls passed.");
    return 0;
}

static bool language_read(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe, UInt8 in_pipe,
                          const char *directory, const char *name, uint32_t address,
                          unsigned count, uint8_t *data) {
    FILE *file = new_file(directory,name);
    if (!file) return false;
    bool ok = true;
    for (unsigned n = 0; n < count; n++) {
        if (!read_program_block(usb,out_pipe,in_pipe,(address-0x40000000)/1024+n,data+1024*n)
            || fwrite(data+1024*n,1,1024,file) != 1024 || fflush(file)) { ok = false; break; }
        block_bytes += 1024;
    }
    if (fclose(file)) ok = false;
    return ok;
}

static bool probe_custom_action(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe,
                                 UInt8 in_pipe, const char *directory) {
    uint8_t guard[1024], ui_before[1024], digest[32], before[UPDATE_BYTES], after[UPDATE_BYTES];
    static const uint8_t expected_hash[32] = {
        0x56,0xa2,0x84,0x2a,0xa1,0x9e,0xc1,0x9b,0x43,0x6a,0xfd,0x9e,0x0d,0x82,0xa4,0x0e,
        0x88,0xa9,0x6c,0x42,0xe9,0x5c,0x34,0x21,0x08,0x30,0xc0,0xa8,0x08,0xf3,0x65,0xa5};
    if (!language_read(usb,out_pipe,in_pipe,directory,"settings-dispatch.bin",0x4061e400,1,guard)
        || memcmp(guard+0x164,"\x65\xcd\x36\x40",4)
        || memcmp(guard+0x304,"\x71\xce\x36\x40",4)
        || !language_read(usb,out_pipe,in_pipe,directory,"settings-branch.bin",0x4036cc00,1,guard)
        || memcmp(guard+0x165,"\xcd\x22\x08\xf0\x14\xdf\x00\x04",8)
        || memcmp(guard+0x271,"\xcd\x15\x12\xf0\x18\xdf\x00\x04",8)
        || !language_read(usb,out_pipe,in_pipe,directory,"settings-writer.bin",0x4036d400,1,guard)) return false;
    CC_SHA256(guard+0x187,0x94,digest);
    if (memcmp(digest,expected_hash,32)) {
        fputs("Installed settings writer differs; no language write.\n",stderr); return false;
    }
    if (!language_read(usb,out_pipe,in_pipe,directory,"language-ui-state.bin",0x701af000,1,ui_before)
        || !language_read(usb,out_pipe,in_pipe,directory,"language-menu-state.bin",0x70a0f000,1,guard)) return false;
    bool english_allowed = false;
    for (unsigned n = 0x150; n+8 <= 0x300; n += 8) {
        unsigned id = (unsigned)guard[n] | (unsigned)guard[n+1]<<8;
        if (id == 65535) break;
        if (id == 1 && guard[n+2] == 4) english_allowed = true;
    }
    if (!language_read(usb,out_pipe,in_pipe,directory,"shutdown-state.bin",0x70a67800,1,guard)) return false;
    if (language_inspect_only) return true;
    if (!english_allowed || ui_before[0x238] || ui_before[0x239]) {
        fputs("Expected enabled English option and Japanese UI cache differ; no write.\n",stderr); return false;
    }
    static const uint8_t absolute_hash[32] = {
        0xa2,0x92,0xe0,0xed,0x6f,0x22,0xe6,0x31,0xcb,0x78,0x76,0xbf,0x74,0xe6,0x49,0x1b,
        0x4b,0x5a,0x5a,0x64,0x2f,0x15,0xf8,0x16,0x04,0x25,0xad,0x11,0x2a,0x80,0xc3,0x54};
    if (!language_read(usb,out_pipe,in_pipe,directory,"ui-write-handler.bin",0x4036e000,1,guard)) return false;
    CC_SHA256(guard+0x86,0x71,digest);
    if (memcmp(digest,absolute_hash,32)
        || !language_read(usb,out_pipe,in_pipe,directory,"ui-write-mode.bin",0x702ff800,1,guard)
        || guard[0x5d]) return false;
    if (!language_read(usb,out_pipe,in_pipe,directory,"update-before.bin",0x7bfb0000,18,before)) return false;
    const uint8_t japanese[12] = {0,0,0,0,0x0f,0x27,0x63,0x63,0x0f,0x27,0x63,0x63};
    if (memcmp(before+LANGUAGE_OFFSET,japanese,12)) {
        fputs("Expected Japanese language pattern differs; no write.\n",stderr); return false;
    }
    uint8_t packet[16], ack[16]; language_request(packet);
    fprintf(events,"{\"event\":\"language_write_intent\",\"area\":16,\"word\":220,"
            "\"before\":0,\"after\":256}\n"); fflush(events);
    language_write_attempts++;
    if (!send_request(usb,out_pipe,packet,16,100) || !receive_frame(usb,in_pipe,8,ack,16)
        || !language_ack(ack,16)) return false;
    ui_language_request(packet);
    fprintf(events,"{\"event\":\"ui_language_write_intent\",\"halfword_address\":\"0x701af238\","
            "\"before\":0,\"after\":256,\"preserved_adjacent_byte\":0}\n"); fflush(events);
    ui_language_write_attempts++;
    if (!send_request(usb,out_pipe,packet,16,100) || !receive_frame(usb,in_pipe,8,ack,16)
        || !language_ack(ack,16)
        || !language_read(usb,out_pipe,in_pipe,directory,"language-ui-after.bin",0x701af000,1,guard)) return false;
    ui_english_readback = guard[0x238] == 0 && guard[0x239] == 1;
    if (!language_read(usb,out_pipe,in_pipe,directory,"update-after.bin",0x7bfb0000,18,after)) return false;
    english_readback = after[LANGUAGE_OFFSET] == 0 && after[LANGUAGE_OFFSET+1] == 1;
    for (unsigned n = 0; n < UPDATE_BYTES; n++) if (before[n] != after[n]) readback_differences++;
    fprintf(events,"{\"event\":\"language_readback\",\"english_word_verified\":%s,\"changed_bytes\":%u}\n",
            english_readback?"true":"false",readback_differences); fflush(events);
    printf("English settings word readback: %s; changed bytes in full settings area: %u.\n",
           english_readback?"verified":"failed",readback_differences);
    return english_readback && ui_english_readback;
}

int main(int argc, char **argv) {
    if (selftest() || language_selftest()) return 1;
    if (argc == 2 && !strcmp(argv[1],"selftest")) return 0;
    if (argc != 3 || (strcmp(argv[1],"english") && strcmp(argv[1],"inspect"))) {
        fputs("Usage: gm5-language selftest | {inspect|english} NEW_OUTPUT_DIRECTORY\n",stderr); return 2;
    }
    language_inspect_only = !strcmp(argv[1],"inspect");
    if (mkdir(argv[2],0700)) return 1;
    events = new_file(argv[2],"events.jsonl"); if (!events) return 1;
    fprintf(events,"{\"event\":\"start\",\"mode\":\"language-%s\",\"epoch_utc\":%lld}\n",argv[1],(long long)time(NULL));
    int status = probe("language-english",argv[2]);
    FILE *summary = new_file(argv[2],"summary.json");
    if (!summary) status = 1;
    else {
        fprintf(summary,"{\"schema\":1,\"model\":\"DMC-GM5\",\"mode\":\"language-%s\","
                "\"exit_status\":%d,\"control_requests_attempted\":%u,\"bulk_writes_attempted\":%u,"
                "\"validated_word_responses\":%u,\"program_block_bytes\":%u,\"language_writes_attempted\":%u,"
                "\"english_ram_readback\":%s,\"ui_language_writes_attempted\":%u,\"ui_english_readback\":%s,"
                "\"changed_bytes\":%u,\"persistent_verified\":false,"
                "\"eeprom_commit_command_sent\":false,\"firmware_flash\":false}\n",argv[1],status,
                control_attempts,bulk_write_attempts,valid_words,block_bytes,language_write_attempts,
                english_readback?"true":"false",ui_language_write_attempts,
                ui_english_readback?"true":"false",readback_differences);
        if (fclose(summary)) status = 1;
    }
    if (fclose(events)) status = 1;
    printf("Evidence: %s\n",argv[2]); return status;
}
