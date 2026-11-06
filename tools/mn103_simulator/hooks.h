/* Optional instruction-boundary debugging hook. GPL-3.0-or-later. */
#ifndef GM5_EXECUTION_HOOKS_H
#define GM5_EXECUTION_HOOKS_H
#include <stdint.h>
struct sim_state;
typedef int (*gm5_instruction_hook)(void *, uint32_t, uint32_t);
void gm5_install_instruction_hook(gm5_instruction_hook callback, void *opaque);
void gm5_engine_instruction(struct sim_state *machine, uint32_t pc, uint32_t first_byte);
uint32_t gm5_current_instruction_pc(void);
#define ENGINE_ISSUE_PREFIX_HOOK() gm5_engine_instruction(sd, (uint32_t)cia, (uint32_t)instruction_0)
#endif
