/* GNU memory callbacks for a private, in-memory GM5 NOR image.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "defs.h"
#include "sim-main.h"
#include "sim-fpu.h"
#include "sim-signal.h"
#include "mn10300-sim.h"
#include "hw-base.h"
#include "hw-main.h"
#include "sim-core.h"
#include "hooks.h"
#include "nor_model.h"
#include "devices.h"
#include "control_model.h"

static struct gm5_nor nor;
static struct hw *device;
static struct sim_state *owner;
static uint32_t sync_lock_pc, sync_unlock_pc, sync_id, sync_locks, sync_unlocks;
static bool sync_locked;
static struct gm5_control_model control;
static struct hw *control_device;

static void die(const char *message) { fprintf(stderr, "%s\n", message); exit(1); }
static void halt_model(void) {
    uint32_t pc = gm5_current_instruction_pc();
    PC = pc;
    sim_engine_halt(owner, STATE_CPU(owner, 0), NULL, pc, sim_stopped, SIM_SIGTRAP);
}
static unsigned read_control(struct hw *hw, void *dest, int space, unsigned_word at, unsigned size) {
    (void)hw; (void)space;
    uint16_t value;
    if (!gm5_control_read(&control, at, size, &value, gm5_current_instruction_pc())) halt_model();
    uint8_t *bytes = dest;
    bytes[0] = value;
    bytes[1] = value>>8;
    return size;
}
static unsigned write_control(struct hw *hw, const void *source, int space, unsigned_word at, unsigned size) {
    (void)hw; (void)space;
    const uint8_t *bytes = source;
    uint16_t value = size == 2 ? bytes[0] | (uint16_t)bytes[1]<<8 : 0;
    if (!gm5_control_write(&control, at, size, value, gm5_current_instruction_pc())) halt_model();
    return size;
}
void gm5_devices_control(struct sim_state *machine, uint32_t busy, uint32_t stuck, const char *path) {
    if (control_device || busy > 1000000 || stuck > 3) die("Invalid command-controller fixture");
    gm5_control_init(&control, busy, stuck);
    if (!(control.log = fopen(path, "wx"))) die("Cannot create command-controller log");
    owner = machine;
    control_device = hw_create(machine, NULL, "cfi", "gm5-control", NULL, NULL);
    set_hw_io_read_buffer(control_device, read_control);
    set_hw_io_write_buffer(control_device, write_control);
    sim_core_attach(machine, NULL, -1, access_read_write, 0, 0x9c010008U, 2, 0, control_device, NULL);
    sim_core_attach(machine, NULL, -1, access_read_write, 0, 0x9c01000eU, 2, 0, control_device, NULL);
}
int gm5_devices_control_enabled(void) { return control_device != NULL; }
void gm5_devices_control_report(FILE *out) { gm5_control_report(&control, out); }
static uint32_t offset(unsigned_word address) {
    if (address >= 0x80000000U && address < 0x82000000U) return address-0x80000000U;
    if (address >= 0x40000000U && address < 0x42000000U) return address-0x40000000U;
    die("NOR callback address is outside the two modeled aliases");
    return 0;
}
static unsigned read_nor(struct hw *hw, void *dest, int space, unsigned_word address, unsigned size) {
    (void)hw; (void)space;
    if (!gm5_nor_read(&nor, offset(address), dest, size, gm5_current_instruction_pc())) halt_model();
    return size;
}
static unsigned write_nor(struct hw *hw, const void *source, int space, unsigned_word address, unsigned size) {
    (void)hw; (void)space;
    if (size != 2) {
        nor.halt_reason = "nor_unsupported_bus_width";
        halt_model();
    }
    const uint8_t *bytes = source;
    uint16_t value = bytes[0] | (uint16_t)bytes[1]<<8;
    if (!gm5_nor_write(&nor, offset(address), value, gm5_current_instruction_pc())) halt_model();
    return size;
}
void gm5_devices_nor(struct sim_state *machine, const char *path, uint32_t busy,
                     uint32_t fail_erase, uint32_t fail_program, uint32_t cut_after) {
    if (device || busy > 1000000) die("NOR already configured or invalid busy-read count");
    uint8_t *data = malloc(GM5_NOR_SIZE);
    FILE *input = fopen(path, "rb");
    if (!data || !input || fread(data, 1, GM5_NOR_SIZE, input) != GM5_NOR_SIZE
            || fgetc(input) != EOF || fclose(input)) die("NOR input must be exactly 32 MiB");
    gm5_nor_init(&nor, data);
    nor.busy_reads = busy;
    nor.fail_erase = fail_erase;
    nor.fail_program = fail_program;
    nor.cut_after = cut_after;
    owner = machine;
    /* Use GNU's primitive CFI device allocation, then bind our reviewed command
       subset directly. The generic Intel CFI finish/command model is not used. */
    device = hw_create(machine, NULL, "cfi", "gm5-nor", NULL, NULL);
    set_hw_io_read_buffer(device, read_nor);
    set_hw_io_write_buffer(device, write_nor);
    /* The cached read view uses the same backing buffer, keeping instruction
       fetches fast. Every write is still routed through the command decoder. */
    sim_core_attach(machine, NULL, -1, access_read_exec, 0, 0x40000000U,
                    GM5_NOR_SIZE, 0, NULL, data);
    sim_core_attach(machine, NULL, -1, access_write, 0, 0x40000000U,
                    GM5_NOR_SIZE, 0, device, NULL);
    sim_core_attach(machine, NULL, -1, access_read_write, 0, 0x80000000U,
                    GM5_NOR_SIZE, 0, device, NULL);
}
void gm5_devices_log(const char *path) {
    if (!device || nor.log || !(nor.log = fopen(path, "wx"))) die("Cannot create NOR event log");
}
void gm5_devices_save(const char *path) {
    if (!device) die("NOR not configured");
    FILE *output = fopen(path, "wx");
    if (!output || fwrite(nor.data, 1, GM5_NOR_SIZE, output) != GM5_NOR_SIZE || fclose(output))
        die("Cannot save private virtual NOR image");
}
void gm5_devices_sync(uint32_t lock_pc, uint32_t unlock_pc, uint32_t identifier) {
    if (!device || sync_lock_pc || !lock_pc || !unlock_pc || lock_pc == unlock_pc)
        die("Invalid single-thread synchronization model");
    sync_lock_pc = lock_pc;
    sync_unlock_pc = unlock_pc;
    sync_id = identifier;
}
int gm5_devices_instruction(uint32_t pc) {
    if (!sync_lock_pc || (pc != sync_lock_pc && pc != sync_unlock_pc)) return 0;
    bool acquire = pc == sync_lock_pc;
    if (State.regs[REG_D0] != sync_id || sync_locked == acquire) {
        nor.halt_reason = "single_thread_sync_error";
        return 1;
    }
    sync_locked = acquire;
    if (acquire) ++sync_locks;
    else ++sync_unlocks;
    if (nor.log)
        fprintf(nor.log, "{\"event\":\"sync_%s\",\"id\":%u,\"pc\":\"0x%08x\"}\n",
                acquire ? "lock" : "unlock", sync_id, pc);
    return 0;
}
void gm5_devices_service_report(FILE *stream) {
    if (!sync_lock_pc) { fputs("null", stream); return; }
    fprintf(stream, "{\"model\":\"single_thread_mutex\",\"id\":%u,\"locks\":%u,\"unlocks\":%u,\"held\":%s}",
            sync_id, sync_locks, sync_unlocks, sync_locked ? "true" : "false");
}
const char *gm5_devices_stop_reason(void) { return control.halt_reason ? control.halt_reason : nor.halt_reason; }
void gm5_devices_report(FILE *stream) {
    if (device) gm5_nor_report(&nor, stream);
    else fputs("null", stream);
}
void gm5_devices_close(void) {
    if (control_device) {
        if (control.log && fclose(control.log)) die("Command-controller log flush failed");
        hw_delete(control_device);
        control_device = NULL;
    }
    if (!device) return;
    if (nor.log && fclose(nor.log)) die("NOR log flush failed");
    hw_delete(device);
    free(nor.data);
    device = NULL;
}
