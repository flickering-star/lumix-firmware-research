/* Read the fixed GM5 32 MiB NOR mapping, with optional verified-prefix resume.
 * Only settings-control reads and 1 KiB memory reads are sent. No RAM/settings
 * writes, flash commands, reset, USB reconfiguration, or automatic retry.
 */
#define PROBE_GM5
#ifndef PROBE_GM5_MAIN_ONLY
#define PROBE_GM5_FULL_NOR
#endif
#define main shared_gm5_backup_main
#include "gm1_usb_probe_macos.c"
#undef main

int main(int argc, char **argv) {
    if (selftest()) return 1;
    if (argc == 2 && !strcmp(argv[1], "selftest")) return 0;
    bool secondary = argc > 1 && (!strcmp(argv[1], "backup-secondary") || !strcmp(argv[1], "resume-secondary"));
#ifdef PROBE_GM5_MAIN_ONLY
    if (secondary) { fputs("Main-only build cannot select a different component.\n", stderr); return 2; }
#endif
    bool resume = argc == 4 && (!strcmp(argv[1], "resume") || !strcmp(argv[1], "resume-secondary"));
    unsigned target_bytes = secondary ? SECONDARY_BYTES : PROGRAM_BYTES;
    if (!resume && (argc != 3 || (strcmp(argv[1], "backup") && strcmp(argv[1], "backup-secondary")))) {
        fputs("Usage: gm5-flash-backup selftest | {backup|backup-secondary} NEW_DIRECTORY | {resume|resume-secondary} NEW_DIRECTORY VERIFIED_PREFIX\n", stderr);
        return 2;
    }
    if (resume) {
        struct stat st;
        if (stat(argv[3], &st) || !S_ISREG(st.st_mode) || st.st_size <= 0
            || st.st_size > target_bytes || st.st_size % BLOCK_BYTES) {
            fputs("Resume prefix must be a nonempty, aligned file within the fixed component.\n", stderr);
            return 2;
        }
        resume_prefix_path = argv[3];
        resume_input_bytes = (unsigned)st.st_size;
    }
    if (mkdir(argv[2], 0700)) { perror("Create backup directory"); return 1; }
    events = new_file(argv[2], "events.jsonl");
    if (!events) return 1;
#ifdef PROBE_GM5_MAIN_ONLY
    const char *mode = resume ? "resume" : "program";
#else
    const char *mode = secondary ? (resume ? "resume-secondary" : "secondary") : (resume ? "resume-nor-backup" : "nor-backup");
#endif
    fprintf(events, "{\"event\":\"start\",\"mode\":\"%s\",\"epoch_utc\":%lld,\"block_delay_ms\":%u}\n",
            mode, (long long)time(NULL), BLOCK_DELAY_MS);
    fflush(events);
    int status = probe(secondary ? (resume ? "resume-secondary" : "secondary") : (resume ? "resume" : "program"), argv[2]);
#ifndef PROBE_GM5_MAIN_ONLY
    char old_path[4096], new_path[4096];
    int old_n = snprintf(old_path, sizeof old_path, "%s/program-main.bin", argv[2]);
    int new_n = snprintf(new_path, sizeof new_path, "%s/flash32m.bin", argv[2]);
    struct stat st;
    if (old_n < 0 || new_n < 0 || (size_t)old_n >= sizeof old_path || (size_t)new_n >= sizeof new_path)
        status = 1;
    else if (!secondary && !stat(old_path, &st) && rename(old_path, new_path)) status = 1;
#endif
    FILE *summary = new_file(argv[2], "summary.json");
    if (!summary) status = 1;
    else {
        fprintf(summary, "{\"schema\":1,\"model\":\"DMC-GM5\",\"mode\":\"%s\",\"exit_status\":%d,"
                "\"interface_opened\":%s,\"control_requests_attempted\":%u,\"bulk_writes_attempted\":%u,"
                "\"validated_word_responses\":%u,\"settings_bytes\":%u,\"program_block_bytes\":%u,"
                "\"copied_prefix_bytes\":%u,\"resume_anchor_blocks\":%u,\"physical_flash_bytes\":%u,"
                "\"target_bytes\":%u,\"host_ram_writes\":0,\"host_flash_writes\":0}\n", mode, status,
                interface_opened ? "true" : "false", control_attempts, bulk_write_attempts,
                valid_words, settings_bytes, block_bytes, copied_prefix_bytes, resume_anchor_blocks, 32u*1024u*1024u, target_bytes);
        if (fclose(summary)) status = 1;
    }
    if (fclose(events)) status = 1;
    printf("Backup %s. Evidence: %s\n", status ? "stopped; prefix retained" : "complete", argv[2]);
    return status;
}
