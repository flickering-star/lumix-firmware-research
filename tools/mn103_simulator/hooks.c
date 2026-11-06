/* Instruction-boundary stops for GNU's unmodified generated CPU semantics.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "defs.h"
#include "sim-main.h"
#include "sim-fpu.h"
#include "sim-signal.h"
#include "mn10300-sim.h"
#include "hooks.h"

static gm5_instruction_hook instruction_hook;
static void *hook_context;
static uint32_t instruction_pc;

uint32_t gm5_current_instruction_pc(void) { return instruction_pc; }

void gm5_install_instruction_hook(gm5_instruction_hook callback, void *opaque) {
    instruction_hook = callback;
    hook_context = opaque;
}

void gm5_engine_instruction(struct sim_state *machine, uint32_t pc, uint32_t first_byte) {
    instruction_pc = pc;
    if (instruction_hook && instruction_hook(hook_context, pc, first_byte)) {
        PC = pc;
        sim_engine_halt(machine, STATE_CPU(machine, 0), NULL, pc, sim_stopped, SIM_SIGTRAP);
    }
}
