/* Bounded abstract command-completion model. GPL-3.0-or-later. */
#ifndef GM5_CONTROL_MODEL_H
#define GM5_CONTROL_MODEL_H
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
struct gm5_control_model {
    uint32_t busy_reads, stuck_mask, remaining[2];
    bool pending[2];
    uint64_t reads, writes, starts, completions;
    const char *halt_reason;
    FILE *log;
};
void gm5_control_init(struct gm5_control_model *, uint32_t, uint32_t);
bool gm5_control_read(struct gm5_control_model *, uint32_t, unsigned, uint16_t *, uint32_t);
bool gm5_control_write(struct gm5_control_model *, uint32_t, unsigned, uint16_t, uint32_t);
void gm5_control_report(const struct gm5_control_model *, FILE *);
#endif
