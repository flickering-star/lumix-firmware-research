/* GM5 offline execution harness around GNU's MN10300/AM33-2 simulator.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * The configuration protocol maps host buffers into simulated memory. It has
 * no camera/USB interface. Target host-syscall instructions are stopped before
 * execution; unmapped hardware is left unmapped. Every run has a step budget.
 */
#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <bfd.h>
#include <sim/callback.h>
#include <sim/sim.h>
#include "hooks.h"
#include "devices.h"

enum { REG_PC = 9, MAX_STOPS = 64, MAX_BYTES = 128 * 1024 * 1024 };
static SIM_DESC machine;
static FILE *trace;
static uint32_t stop_pc[MAX_STOPS];
static char stop_name[MAX_STOPS][80];
static bool stop_compare[MAX_STOPS];
static unsigned stop_left[MAX_STOPS], stop_right[MAX_STOPS];
static unsigned stops;
static uint32_t watch_pc[MAX_STOPS];
static char watch_name[MAX_STOPS][80];
static unsigned watches;
enum { MAX_MEMORY_WATCH_BYTES = 64 };
static struct {
    uint32_t address, size;
    uint8_t previous[MAX_MEMORY_WATCH_BYTES];
    char label[80];
} memory_watch[MAX_STOPS];
static unsigned memory_watches;
static uint32_t previous_pc;
static bool previous_pc_valid;
static uint64_t budget = 100000, steps;
static uint64_t trace_every = 1;
static bool fast_mode;
static const char *stop_reason;

static void die(const char *message) { fprintf(stderr, "%s\n", message); exit(1); }
static uint32_t reg_get(unsigned index) {
    uint8_t data[4];
    if (index >= 32 || sim_fetch_register(machine, index, data, 4) != 4) die("Register fetch failed");
    return (uint32_t)data[0] | (uint32_t)data[1]<<8 | (uint32_t)data[2]<<16 | (uint32_t)data[3]<<24;
}
static void reg_set(unsigned index, uint32_t value) {
    uint8_t data[4] = {value, value>>8, value>>16, value>>24};
    if (index >= 32 || sim_store_register(machine, index, data, 4) != 4) die("Register store failed");
}
static uint64_t number(char **cursor) {
    while (isspace((unsigned char)**cursor)) ++*cursor;
    char *end;
    errno = 0;
    uint64_t result = strtoull(*cursor, &end, 0);
    if (errno || end == *cursor) die("Invalid number in scenario");
    *cursor = end;
    return result;
}
static char *rest(char *cursor) {
    while (isspace((unsigned char)*cursor)) ++cursor;
    size_t n = strlen(cursor);
    while (n && isspace((unsigned char)cursor[n-1])) cursor[--n] = 0;
    return cursor;
}
static uint32_t address(char **cursor) {
    uint64_t value = number(cursor);
    if (value > UINT32_MAX) die("Address outside 32-bit target");
    return (uint32_t)value;
}
static void region(uint32_t at, uint64_t size) {
    if (!size || size > MAX_BYTES || (uint64_t)at+size > UINT64_C(0x100000000)) die("Invalid memory region");
    char command[160];
    snprintf(command, sizeof command, "memory region 0x%08x,0x%" PRIx64, at, size);
    sim_do_command(machine, command);
}
static void ram_alias(uint32_t at, uint64_t size, uint32_t shadow) {
    if (!size || at < 0x70000000U || (uint64_t)at+size > 0x71000000U
            || (uint64_t)at+0x40000000U != shadow)
        die("RAM alias must pair bounded 0x70 RAM with its 0xb0 view");
    char command[160];
    snprintf(command, sizeof command, "memory alias 0x%08x,0x%" PRIx64 ",0x%08x", at, size, shadow);
    sim_do_command(machine, command);
}
static void load(uint32_t at, const char *path) {
    FILE *input = fopen(path, "rb");
    if (!input) die("Cannot open scenario input");
    if (fseek(input, 0, SEEK_END)) die("Cannot seek input");
    long size = ftell(input);
    if (size <= 0 || size > MAX_BYTES || (uint64_t)at+(uint64_t)size > UINT64_C(0x100000000)) die("Invalid input extent");
    rewind(input);
    uint8_t *data = malloc((size_t)size);
    if (!data || fread(data, 1, (size_t)size, input) != (size_t)size || fclose(input)) die("Input read failed");
    if (sim_write(machine, at, data, (uint64_t)size) != (uint64_t)size) die("Input does not fit simulated memory");
    free(data);
}
static void bytes(uint32_t at, char *hex) {
    size_t n = strlen(hex);
    if (!n || n%2 || n > MAX_BYTES*2U) die("Invalid hex memory input");
    uint8_t *data = malloc(n/2);
    if (!data) die("Out of memory");
    for (size_t i = 0; i < n/2; ++i) {
        char pair[3] = {hex[2*i], hex[2*i+1], 0};
        if (!isxdigit((unsigned char)pair[0]) || !isxdigit((unsigned char)pair[1])) die("Invalid hex digit");
        data[i] = (uint8_t)strtoul(pair, NULL, 16);
    }
    if (sim_write(machine, at, data, n/2) != n/2) die("Hex data outside mapped memory");
    free(data);
}
static void dump(uint32_t at, uint64_t size, const char *path) {
    if (!size || size > MAX_BYTES) die("Invalid dump length");
    uint8_t *data = malloc((size_t)size);
    if (!data || sim_read(machine, at, data, size) != size) die("Dump outside mapped memory");
    FILE *output = fopen(path, "wx");
    if (!output || fwrite(data, 1, (size_t)size, output) != size || fclose(output)) die("Dump write failed");
    free(data);
}

static void observe_memory(uint32_t next_pc, bool initialize) {
    for (unsigned n = 0; n < memory_watches; ++n) {
        uint8_t current[MAX_MEMORY_WATCH_BYTES];
        uint32_t at = memory_watch[n].address, size = memory_watch[n].size;
        if (sim_read(machine, at, current, size) != size) die("Memory observation outside mapped RAM");
        if (!initialize && memcmp(current, memory_watch[n].previous, size)) {
            if (!trace || !previous_pc_valid) die("Memory observation requires an execution trace");
            fprintf(trace, "{\"event\":\"memory_change\",\"label\":\"%s\",\"step\":%" PRIu64
                    ",\"instruction_pc\":\"0x%08x\",\"next_pc\":\"0x%08x\",\"address\":\"0x%08x\",\"before\":\"",
                    memory_watch[n].label, steps, previous_pc, next_pc, at);
            for (unsigned i = 0; i < size; ++i) fprintf(trace, "%02x", memory_watch[n].previous[i]);
            fputs("\",\"after\":\"", trace);
            for (unsigned i = 0; i < size; ++i) fprintf(trace, "%02x", current[i]);
            fputs("\"}\n", trace);
        }
        memcpy(memory_watch[n].previous, current, size);
    }
}

static bool before_instruction(uint32_t pc, uint32_t first_byte) {
    if (memory_watches) observe_memory(pc, false);
    for (unsigned i = 0; i < stops; ++i) if (pc == stop_pc[i]
            && (!stop_compare[i] || reg_get(stop_left[i]) != reg_get(stop_right[i]))) {
        stop_reason = stop_name[i]; return true;
    }
    if (gm5_devices_instruction(pc)) { stop_reason = gm5_devices_stop_reason(); return true; }
    for (unsigned i = 0; trace && i < watches; ++i) if (pc == watch_pc[i])
        fprintf(trace, "{\"event\":\"watch\",\"label\":\"%s\",\"step\":%" PRIu64 ",\"pc\":\"0x%08x\",\"d0\":\"0x%08x\",\"d1\":\"0x%08x\"}\n",
                watch_name[i], steps, pc, reg_get(0), reg_get(1));
    if (first_byte == 0xff) { stop_reason = "target_break"; return true; }
    uint8_t instruction[8] = {0};
    uint64_t got = 0;
    if (first_byte == 0xf0 || (trace && steps % trace_every == 0)) {
        got = sim_read(machine, pc, instruction, sizeof instruction);
        if (got < 2) { stop_reason = "unmapped_instruction"; return true; }
        if (instruction[0] == 0xf0 && instruction[1] == 0xc0) {
            stop_reason = "unmodeled_host_syscall"; return true;
        }
    }
    if (trace && steps % trace_every == 0) {
        fprintf(trace, "{\"step\":%" PRIu64 ",\"pc\":\"0x%08x\",\"d0\":\"0x%08x\",\"psw\":\"0x%08x\",\"bytes\":\"",
                steps, pc, reg_get(0), reg_get(11));
        for (unsigned i = 0; i < got; ++i) fprintf(trace, "%02x", instruction[i]);
        fputs("\"}\n", trace);
    }
    previous_pc = pc;
    previous_pc_valid = true;
    return false;
}

static int fast_instruction(void *opaque, uint32_t pc, uint32_t first_byte) {
    (void)opaque;
    if (steps >= budget) { stop_reason = "budget_exhausted"; return 1; }
    if (before_instruction(pc, first_byte)) return 1;
    ++steps;
    return 0;
}

static void run(void) {
    stop_reason = NULL;
    enum sim_stop reason = sim_stopped;
    int signal_number = 0;
    steps = 0;
    previous_pc_valid = false;
    if (memory_watches) {
        if (!trace) die("Memory observation requires TRACE");
        observe_memory(reg_get(REG_PC), true);
    }
    if (fast_mode) {
        gm5_install_instruction_hook(fast_instruction, NULL);
        sim_resume(machine, 0, 0);
        sim_stop_reason(machine, &reason, &signal_number);
        gm5_install_instruction_hook(NULL, NULL);
        if (!stop_reason) stop_reason = gm5_devices_stop_reason();
        if (!stop_reason) stop_reason = "target_exception";
    } else {
        while (steps < budget) {
            uint32_t pc = reg_get(REG_PC);
            uint8_t first;
            if (sim_read(machine, pc, &first, 1) != 1) { stop_reason = "unmapped_instruction"; break; }
            if (before_instruction(pc, first)) break;
            ++steps;
            sim_resume(machine, 1, 0);
            sim_stop_reason(machine, &reason, &signal_number);
            if (gm5_devices_stop_reason()) { stop_reason = gm5_devices_stop_reason(); break; }
            if (reason != sim_stopped || signal_number != SIGTRAP) { stop_reason = "target_exception"; break; }
        }
        if (!stop_reason) stop_reason = "budget_exhausted";
    }
    if (memory_watches) observe_memory(reg_get(REG_PC), false);
    if (trace) { if (fclose(trace)) die("Trace flush failed"); trace = NULL; }
    printf("{\"event\":\"result\",\"stop\":\"%s\",\"steps\":%" PRIu64 ",\"pc\":\"0x%08x\",\"sim_reason\":%d,\"signal\":%d,\"registers\":[",
           stop_reason, steps, reg_get(REG_PC), (int)reason, signal_number);
    for (unsigned i = 0; i < 32; ++i) printf("%s\"0x%08x\"", i ? "," : "", reg_get(i));
    fputs("],\"nor\":", stdout);
    gm5_devices_report(stdout);
    fputs(",\"services\":", stdout);
    gm5_devices_service_report(stdout);
    if (gm5_devices_control_enabled()) {
        fputs(",\"command_controller\":", stdout);
        gm5_devices_control_report(stdout);
    }
    puts("}");
    fflush(stdout);
}

int main(int argc, char **argv) {
    if (argc != 2) die("Usage: gm5-mn103-sim SCENARIO_PROTOCOL_FILE");
    bfd_init();
    default_callback.init(&default_callback);
    char *options[] = {"gm5-mn103-sim", "--architecture=am33-2", NULL};
    machine = sim_open(SIM_OPEN_DEBUG, &default_callback, NULL, options);
    if (!machine || sim_create_inferior(machine, NULL, NULL, NULL) != SIM_RC_OK) die("Simulator initialization failed");
    sim_do_command(machine, "memory delete all");
    sim_do_command(machine, "memory clear");
    FILE *input = fopen(argv[1], "r");
    if (!input) die("Cannot open scenario protocol");
    char *line = NULL;
    size_t capacity = 0;
    bool ran = false;
    while (getline(&line, &capacity, input) >= 0) {
        char *cursor = strchr(line, ' ');
        if (!cursor) {
            if (!strcmp(rest(line), "RUN")) { if (ran) die("Only one RUN allowed"); run(); ran = true; continue; }
            die("Unknown protocol line");
        }
        *cursor++ = 0;
        if (!strcmp(line, "MAP") && !ran) { uint32_t at = address(&cursor); region(at, number(&cursor)); }
        else if (!strcmp(line, "RAM_ALIAS") && !ran) {
            uint32_t at = address(&cursor);
            uint64_t size = number(&cursor);
            uint32_t shadow = address(&cursor);
            ram_alias(at, size, shadow);
        }
        else if (!strcmp(line, "LOAD") && !ran) { uint32_t at = address(&cursor); load(at, rest(cursor)); }
        else if (!strcmp(line, "BYTES") && !ran) { uint32_t at = address(&cursor); bytes(at, rest(cursor)); }
        else if (!strcmp(line, "REG") && !ran) { unsigned index = (unsigned)number(&cursor); reg_set(index, address(&cursor)); }
        else if (!strcmp(line, "BUDGET") && !ran) { budget = number(&cursor); if (!budget || budget > UINT64_C(10000000000)) die("Step budget outside range"); }
        else if (!strcmp(line, "TRACE_EVERY") && !ran) { trace_every = number(&cursor); if (!trace_every || trace_every > 1000000) die("Trace interval outside range"); }
        else if (!strcmp(line, "MODE") && !ran) {
            char *mode = rest(cursor);
            if (strcmp(mode, "fast") && strcmp(mode, "step")) die("Unknown execution mode");
            fast_mode = !strcmp(mode, "fast");
        }
        else if (!strcmp(line, "NOR") && !ran) {
            uint32_t busy = address(&cursor), fail_erase = address(&cursor);
            uint32_t fail_program = address(&cursor), cut_after = address(&cursor);
            gm5_devices_nor(machine, rest(cursor), busy, fail_erase, fail_program, cut_after);
        }
        else if (!strcmp(line, "NOR_LOG") && !ran) gm5_devices_log(rest(cursor));
        else if (!strcmp(line, "CONTROL") && !ran) {
            uint32_t busy = address(&cursor), stuck = address(&cursor);
            gm5_devices_control(machine, busy, stuck, rest(cursor));
        }
        else if (!strcmp(line, "SYNC") && !ran) {
            uint32_t lock_pc = address(&cursor), unlock_pc = address(&cursor);
            gm5_devices_sync(lock_pc, unlock_pc, address(&cursor));
        }
        else if (!strcmp(line, "NOR_SAVE") && ran) gm5_devices_save(rest(cursor));
        else if (!strcmp(line, "TRACE") && !ran) { if (trace) die("Trace already configured"); trace = fopen(rest(cursor), "wx"); if (!trace) die("Cannot create trace"); }
        else if (!strcmp(line, "STOP") && !ran) {
            if (stops == MAX_STOPS) die("Too many stops");
            stop_pc[stops] = address(&cursor);
            char *label = rest(cursor);
            if (!*label || strlen(label) >= sizeof stop_name[0]) die("Invalid stop name");
            for (char *p = label; *p; ++p) if (!isalnum((unsigned char)*p) && *p != '_') die("Invalid stop name");
            strcpy(stop_name[stops++], label);
        }
        else if (!strcmp(line, "STOPDIFF") && !ran) {
            if (stops == MAX_STOPS) die("Too many stops");
            stop_pc[stops] = address(&cursor);
            stop_left[stops] = address(&cursor);
            stop_right[stops] = address(&cursor);
            if (stop_left[stops] >= 32 || stop_right[stops] >= 32) die("Invalid conditional-stop register");
            stop_compare[stops] = true;
            char *label = rest(cursor);
            if (!*label || strlen(label) >= sizeof stop_name[0]) die("Invalid stop name");
            for (char *p = label; *p; ++p) if (!isalnum((unsigned char)*p) && *p != '_') die("Invalid stop name");
            strcpy(stop_name[stops++], label);
        }
        else if (!strcmp(line, "WATCH") && !ran) {
            if (watches == MAX_STOPS) die("Too many watchpoints");
            watch_pc[watches] = address(&cursor);
            char *label = rest(cursor);
            if (!*label || strlen(label) >= sizeof watch_name[0]) die("Invalid watch name");
            for (char *p = label; *p; ++p) if (!isalnum((unsigned char)*p) && *p != '_') die("Invalid watch name");
            strcpy(watch_name[watches++], label);
        }
        else if (!strcmp(line, "MEMWATCH") && !ran) {
            if (memory_watches == MAX_STOPS) die("Too many memory observations");
            uint32_t at = address(&cursor), size = address(&cursor);
            uint64_t end = (uint64_t)at+size;
            /* Observation reads must never poll NOR/MMIO or alter device state. */
            bool ram = (at >= 0x70000000U && end <= 0x71000000U)
                || (at >= 0x7bfb0000U && end <= 0x7bff0000U);
            if (!size || size > MAX_MEMORY_WATCH_BYTES || !ram) die("Memory observation requires a bounded ordinary RAM interval");
            char *label = rest(cursor);
            if (!*label || strlen(label) >= sizeof memory_watch[0].label) die("Invalid memory observation label");
            for (char *p = label; *p; ++p) if (!isalnum((unsigned char)*p) && *p != '_') die("Invalid memory observation label");
            memory_watch[memory_watches].address = at;
            memory_watch[memory_watches].size = size;
            strcpy(memory_watch[memory_watches++].label, label);
        }
        else if (!strcmp(line, "DUMP") && ran) { uint32_t at = address(&cursor); uint64_t size = number(&cursor); dump(at, size, rest(cursor)); }
        else die("Unknown or out-of-order protocol command");
    }
    if (ferror(input) || fclose(input) || !ran) die("Scenario did not complete RUN");
    free(line);
    gm5_devices_close();
    sim_close(machine, 1);
    default_callback.shutdown(&default_callback);
    return 0;
}
