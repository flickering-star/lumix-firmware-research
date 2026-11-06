/* The native routine sets bit4 and polls for it to clear at these two words.
 * This model assumes zero other bits and deterministic completion; it does
 * not identify the controller or reproduce its undocumented physical work.
 * GPL-3.0-or-later.
 */
#include "control_model.h"
#include <inttypes.h>
#include <string.h>

void gm5_control_init(struct gm5_control_model *m, uint32_t busy, uint32_t stuck) {
    memset(m, 0, sizeof *m);
    m->busy_reads = busy;
    m->stuck_mask = stuck;
}
static int slot(uint32_t at) {
    return at == 0x9c010008U ? 0 : at == 0x9c01000eU ? 1 : -1;
}
bool gm5_control_read(struct gm5_control_model *m, uint32_t at, unsigned width,
                      uint16_t *value, uint32_t pc) {
    int n = slot(at);
    if (width != 2 || n < 0) { m->halt_reason = "control_unsupported_access"; return false; }
    ++m->reads;
    *value = 0;
    if (!m->pending[n]) return true;
    if ((m->stuck_mask & (1U<<n)) || m->remaining[n]) {
        if (m->remaining[n]) --m->remaining[n];
        *value = 16;
    } else {
        m->pending[n] = false;
        ++m->completions;
        if (m->log) fprintf(m->log, "{\"event\":\"command_complete\",\"address\":\"0x%08x\",\"pc\":\"0x%08x\"}\n", at, pc);
    }
    return true;
}
bool gm5_control_write(struct gm5_control_model *m, uint32_t at, unsigned width,
                       uint16_t value, uint32_t pc) {
    int n = slot(at);
    if (width != 2 || n < 0) { m->halt_reason = "control_unsupported_access"; return false; }
    if (value != 16 || m->pending[n]) { m->halt_reason = "control_unmodeled_command"; return false; }
    ++m->writes;
    ++m->starts;
    m->pending[n] = true;
    m->remaining[n] = m->busy_reads;
    if (m->log) fprintf(m->log, "{\"event\":\"command_start\",\"address\":\"0x%08x\",\"value\":16,\"pc\":\"0x%08x\"}\n", at, pc);
    return true;
}
void gm5_control_report(const struct gm5_control_model *m, FILE *out) {
    fprintf(out, "{\"model\":\"abstract_bit4_completion\",\"busy_reads\":%u,\"stuck_mask\":%u,"
            "\"reads\":%" PRIu64 ",\"writes\":%" PRIu64 ",\"starts\":%" PRIu64 ",\"completions\":%" PRIu64
            ",\"pending\":[%s,%s]}", m->busy_reads, m->stuck_mask, m->reads, m->writes,
            m->starts, m->completions, m->pending[0] ? "true" : "false", m->pending[1] ? "true" : "false");
}
