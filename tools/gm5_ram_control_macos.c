/* One reversible GM5 RAM-control experiment, never a flash/settings writer.
 * No address/opcode/value arguments: only 0x70a68490, halfwords 0 and 1.
 * The ordinary read probe is compiled without PROBE_RAM_CONTROL_TEST.
 */
#define PROBE_GM5
#define PROBE_RAM_CONTROL_TEST
#define main shared_read_probe_main
#include "gm1_usb_probe_macos.c"
#undef main
#include <CommonCrypto/CommonDigest.h>

static unsigned ram_write_attempts;
static bool ram_restore_verified;
enum { RAM_TOGGLE, RAM_ENABLE, RAM_RESTORE };
static unsigned ram_action;

static bool ram_request(uint8_t packet[16], unsigned value) {
    if (value > 1) return false;
    memset(packet, 0, 16);
    packet[0] = 8; packet[2] = 255; packet[3] = 0x9c;
    packet[4] = 0x90; packet[5] = 0x84; packet[6] = 0xa6; packet[7] = 0x70;
    packet[8] = (uint8_t)value;
    packet[14] = checksum(packet);
    return true;
}

static bool ram_ack(const uint8_t *packet, size_t size) {
    if (size != 16 || packet[0] != 8 || packet[1] || packet[2] != 255
        || packet[3] != 1 || packet[14] != checksum(packet) || packet[15]) return false;
    for (unsigned i = 4; i < 14; i++) if (packet[i]) return false;
    return true;
}

static int ram_selftest(void) {
    const uint8_t expected[16] = {8,0,255,0x9c,0x90,0x84,0xa6,0x70,0,0,0,0,0,0,0xc5,0};
    const uint8_t success[16] = {8,0,255,1,0,0,0,0,0,0,0,0,0,0,0,0};
    uint8_t packet[16];
    if (!ram_request(packet, 0) || memcmp(packet, expected, 16)
        || !ram_request(packet, 1) || packet[8] != 1 || packet[14] != 0xc6
        || ram_request(packet, 2) || ram_request(packet, UINT32_MAX)
        || !ram_ack(success, 16)) return 1;
    for (size_t length = 0; length < 16; length++) if (ram_ack(success, length)) return 1;
    if (ram_ack(success, 17)) return 1;
    for (unsigned byte = 0; byte < 16; byte++)
        for (unsigned bit = 0; bit < 8; bit++) {
            memcpy(packet, success, 16); packet[byte] ^= (uint8_t)(1u << bit);
            if (ram_ack(packet, 16)) return 1;
        }
    memcpy(packet, success, 16); packet[4] = 1; packet[14] = checksum(packet);
    if (ram_ack(packet, 16)) return 1;
    puts("Fixed-address RAM request and ACK controls passed.");
    return 0;
}

static bool read_control_block(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe, UInt8 in_pipe,
                               const char *directory, const char *name,
                               uint32_t address, uint8_t data[1024]) {
    if (!read_program_block(usb, out_pipe, in_pipe, (address-0x40000000)/1024, data)) return false;
    FILE *file = new_file(directory, name);
    if (!file) return false;
    bool ok = fwrite(data, 1, 1024, file) == 1024;
    if (fclose(file)) ok = false;
    if (ok) block_bytes += 1024;
    return ok;
}

static bool write_control(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe, UInt8 in_pipe,
                           unsigned value) {
    uint8_t packet[16], response[16];
    if (!ram_request(packet, value)) return false;
    fprintf(events, "{\"event\":\"ram_halfword_write_intent\",\"address\":\"0x70a68490\",\"value\":%u}\n", value);
    fflush(events);
    ram_write_attempts++;
    return send_request(usb, out_pipe, packet, 16, 100)
        && receive_frame(usb, in_pipe, 8, response, 16) && ram_ack(response, 16);
}

static uint16_t little_halfword(const uint8_t *data) {
    return (uint16_t)((unsigned)data[0] | (unsigned)data[1] << 8);
}

static bool gm5_ram_toggle_test(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe,
                                UInt8 in_pipe, const char *directory) {
    uint8_t data[1024], digest[32];
    static const uint8_t handler_hash[32] = {
        0xa2,0x92,0xe0,0xed,0x6f,0x22,0xe6,0x31,0xcb,0x78,0x76,0xbf,0x74,0xe6,0x49,0x1b,
        0x4b,0x5a,0x5a,0x64,0x2f,0x15,0xf8,0x16,0x04,0x25,0xad,0x11,0x2a,0x80,0xc3,0x54};
    if (!read_control_block(usb,out_pipe,in_pipe,directory,"dispatch-table.bin",0x4061e400,data)
        || memcmp(data+0x304,"\x71\xce\x36\x40",4)
        || !read_control_block(usb,out_pipe,in_pipe,directory,"dispatch-branch.bin",0x4036cc00,data)
        || memcmp(data+0x271,"\xcd\x15\x12\xf0\x18\xdf\x00\x04",8)
        || !read_control_block(usb,out_pipe,in_pipe,directory,"write-handler.bin",0x4036e000,data)) {
        fputs("Installed dispatch guard failed before any RAM write.\n",stderr); return false;
    }
    CC_SHA256(data+0x86,0x71,digest);
    if (memcmp(digest,handler_hash,32)
        || !read_control_block(usb,out_pipe,in_pipe,directory,"usb-mode.bin",0x702ff800,data)
        || data[0x5d]
        || !read_control_block(usb,out_pipe,in_pipe,directory,"ram-before.bin",0x70a68400,data)) {
        fputs("Installed handler, USB mode or expected RAM value differs; no RAM write.\n",stderr);
        return false;
    }
    unsigned prior = little_halfword(data+0x90);
    if (ram_action == RAM_RESTORE && prior == 1) {
        ram_restore_verified = true;
        puts("Original RAM value is already one; no write needed.");
        return true;
    }
    if (prior != (ram_action == RAM_RESTORE ? 0u : 1u)) {
        fputs("Unexpected RAM halfword; stopped before any write.\n",stderr);
        return false;
    }
    if (ram_action == RAM_RESTORE) {
        bool ack = write_control(usb,out_pipe,in_pipe,1);
        ram_restore_verified = ack
            && read_control_block(usb,out_pipe,in_pipe,directory,"ram-restored.bin",0x70a68400,data)
            && little_halfword(data+0x90) == 1;
        printf("Original RAM value restored: %s.\n",ram_restore_verified?"verified":"unverified");
        return ram_restore_verified;
    }
    bool clear_ack = write_control(usb,out_pipe,in_pipe,0);
    bool clear_read = clear_ack
        && read_control_block(usb,out_pipe,in_pipe,directory,"ram-cleared.bin",0x70a68400,data)
        && little_halfword(data+0x90) == 0;
    if (ram_action == RAM_ENABLE && clear_ack && clear_read) {
        puts("Temporary unsigned-input RAM flag is zero; readback verified.");
        return true;
    }
    /* One cleanup restoration is intentional even if the clear ACK/read failed. */
    bool restore_ack = write_control(usb,out_pipe,in_pipe,1);
    ram_restore_verified = restore_ack
        && read_control_block(usb,out_pipe,in_pipe,directory,"ram-restored.bin",0x70a68400,data)
        && little_halfword(data+0x90) == 1;
    fprintf(events,"{\"event\":\"ram_toggle_result\",\"clear_ack\":%s,\"zero_readback\":%s,"
            "\"restore_ack\":%s,\"restored_readback\":%s}\n",clear_ack?"true":"false",
            clear_read?"true":"false",restore_ack?"true":"false",ram_restore_verified?"true":"false");
    fflush(events);
    printf("RAM clear readback: %s; original value restored: %s.\n",
           clear_read?"verified":"failed",ram_restore_verified?"verified":"unverified");
    return clear_ack && clear_read && ram_restore_verified;
}

int main(int argc, char **argv) {
    if (selftest() || ram_selftest()) return 1;
    if (argc == 2 && !strcmp(argv[1],"selftest")) return 0;
    if (argc != 3 || (strcmp(argv[1],"toggle-test") && strcmp(argv[1],"enable-unsigned") && strcmp(argv[1],"restore-signed"))) {
        fputs("Usage: gm5-ram-control selftest | {toggle-test|enable-unsigned|restore-signed} NEW_OUTPUT_DIRECTORY\n",stderr);
        return 2;
    }
    ram_action = !strcmp(argv[1],"enable-unsigned") ? RAM_ENABLE
        : !strcmp(argv[1],"restore-signed") ? RAM_RESTORE : RAM_TOGGLE;
    const char *mode = ram_action == RAM_ENABLE ? "ram-enable" : ram_action == RAM_RESTORE ? "ram-restore" : "ram-toggle-test";
    if (mkdir(argv[2],0700)) { perror("New output"); return 1; }
    events = new_file(argv[2],"events.jsonl");
    if (!events) return 1;
    fprintf(events,"{\"event\":\"start\",\"mode\":\"%s\",\"epoch_utc\":%lld}\n",mode,(long long)time(NULL));
    int status = probe("ram-toggle-test",argv[2]);
    FILE *summary = new_file(argv[2],"summary.json");
    if (!summary) status = 1;
    else {
        fprintf(summary,"{\"schema\":1,\"model\":\"DMC-GM5\",\"mode\":\"%s\","
                "\"exit_status\":%d,\"control_requests_attempted\":%u,\"bulk_writes_attempted\":%u,"
                "\"validated_word_responses\":%u,\"settings_bytes\":%u,\"program_block_bytes\":%u,"
                "\"ram_halfword_writes_attempted\":%u,\"ram_restore_verified\":%s,"
                "\"flash_or_settings_writes\":false}\n",mode,status,control_attempts,bulk_write_attempts,
                valid_words,settings_bytes,block_bytes,ram_write_attempts,ram_restore_verified?"true":"false");
        if (fclose(summary)) status = 1;
    }
    if (fclose(events)) status = 1;
    printf("Evidence: %s\n",argv[2]);
    return status;
}
