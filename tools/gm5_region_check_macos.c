/* Read only the three fixed 1 KiB GM5 language-patch ROM windows.
 * Uses the established model/settings guards and stops on the first error.
 * No RAM/settings/NOR writes, reset, USB reconfiguration or retry.
 */
#define PROBE_GM5
#define PROBE_CUSTOM_ACTION
#define main shared_region_read_main
#include "gm1_usb_probe_macos.c"
#undef main

static bool probe_custom_action(IOUSBInterfaceInterface300 **usb, UInt8 out_pipe,
                                 UInt8 in_pipe, const char *directory) {
    static const struct { uint32_t address; const char *name; } windows[] = {
        {0x400aa000, "language-visibility.bin"},
        {0x40379800, "language-list.bin"},
        {0x40491800, "language-normalizer.bin"}
    };
    for (unsigned n = 0; n < sizeof windows / sizeof windows[0]; ++n) {
        unsigned index = (windows[n].address - 0x40000000) / BLOCK_BYTES;
        if (!read_program_blocks(usb, out_pipe, in_pipe, directory, windows[n].name,
                                 index, index, 1, false, NULL, NULL)) return false;
    }
    return true;
}

int main(int argc, char **argv) {
    if (selftest()) return 1;
    if (argc == 2 && !strcmp(argv[1], "selftest")) return 0;
    if (argc != 3 || strcmp(argv[1], "inspect")) {
        fputs("Usage: gm5-region-check selftest | inspect NEW_OUTPUT_DIRECTORY\n", stderr);
        return 2;
    }
    if (mkdir(argv[2], 0700)) return 1;
    events = new_file(argv[2], "events.jsonl");
    if (!events) return 1;
    fprintf(events, "{\"event\":\"start\",\"mode\":\"region-check\",\"epoch_utc\":%lld}\n",
            (long long)time(NULL));
    int status = probe("region-check", argv[2]);
    FILE *summary = new_file(argv[2], "summary.json");
    if (!summary) status = 1;
    else {
        fprintf(summary, "{\"schema\":1,\"model\":\"DMC-GM5\",\"mode\":\"region-check\","
                "\"exit_status\":%d,\"interface_opened\":%s,\"control_requests_attempted\":%u,"
                "\"bulk_writes_attempted\":%u,\"validated_word_responses\":%u,"
                "\"settings_bytes\":%u,\"program_block_bytes\":%u,"
                "\"host_ram_writes\":0,\"host_flash_writes\":0}\n",
                status, interface_opened ? "true" : "false", control_attempts,
                bulk_write_attempts, valid_words, settings_bytes, block_bytes);
        if (fclose(summary)) status = 1;
    }
    if (fclose(events)) status = 1;
    printf("Three-window read %s. Evidence: %s\n", status ? "stopped" : "complete", argv[2]);
    return status;
}
