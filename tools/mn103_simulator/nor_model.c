/* Offline x16 NOR model of the sequences used by the GM5 native writer.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Geometry comes from the installed firmware's descriptor and native loops.
 * This is not a claim to identify the camera's exact memory part. Successful
 * operations complete after a deterministic number of status reads. Injected
 * failures leave that operation unapplied; power cuts occur between completed
 * operations. Analog timing, intra-operation power loss, protection and ECC
 * are not modeled.
 */
#include "nor_model.h"
#include <inttypes.h>
#include <string.h>

static void event(struct gm5_nor *n, const char *kind, uint32_t at, uint32_t size, uint32_t pc) {
    if (n->log)
        fprintf(n->log, "{\"event\":\"%s\",\"offset\":\"0x%08x\",\"bytes\":%u,\"pc\":\"0x%08x\"}\n", kind, at, size, pc);
}
static bool fault(struct gm5_nor *n, const char *reason, uint32_t at, uint32_t pc) {
    n->halt_reason = reason;
    event(n, reason, at, 0, pc);
    return false;
}
void gm5_nor_init(struct gm5_nor *n, uint8_t *data) {
    memset(n, 0, sizeof *n);
    n->data = data;
    n->busy_reads = 2;
}
static void begin(struct gm5_nor *n, enum gm5_nor_operation operation, uint32_t at, uint32_t pc) {
    n->pending = operation;
    n->phase = NOR_BUSY;
    n->remaining_reads = n->busy_reads;
    if (operation == NOR_ERASE) {
        n->start = at & ~(GM5_NOR_SECTOR - 1U);
        n->length = GM5_NOR_SECTOR;
        n->poll_address = at;
        ++n->erase_attempts;
        n->operation_fails = n->fail_erase && n->erase_attempts == n->fail_erase;
        event(n, "erase_begin", n->start, n->length, pc);
    } else {
        n->length = n->words * 2;
        n->poll_address = n->start + n->length - 2;
        ++n->program_attempts;
        n->operation_fails = n->fail_program && n->program_attempts == n->fail_program;
        event(n, "program_begin", n->start, n->length, pc);
    }
}
static bool complete(struct gm5_nor *n, uint32_t pc) {
    if (n->pending == NOR_ERASE) {
        memset(n->data+n->start, 0xff, n->length);
        ++n->erases;
        n->erased_bytes += n->length;
        event(n, "erase_commit", n->start, n->length, pc);
    } else {
        for (uint32_t i = 0; i < n->words; ++i) {
            uint32_t at = n->start + 2*i;
            uint16_t old = n->data[at] | (uint16_t)n->data[at+1]<<8;
            uint16_t result = old & n->buffer[i];
            if (result != n->buffer[i]) ++n->zero_to_one_words;
            n->data[at] = result;
            n->data[at+1] = result>>8;
        }
        ++n->programs;
        n->programmed_bytes += n->length;
        event(n, "program_commit", n->start, n->length, pc);
    }
    n->pending = NOR_NONE;
    n->phase = NOR_READ;
    ++n->completed;
    if (n->cut_after && n->completed == n->cut_after)
        return fault(n, "nor_power_cut", n->start, pc);
    return true;
}
bool gm5_nor_write(struct gm5_nor *n, uint32_t at, uint16_t value, uint32_t pc) {
    if ((at & 1) || at > GM5_NOR_SIZE-2)
        return fault(n, "nor_invalid_write_address", at, pc);
    ++n->writes;
    /* 0x00f0 is ordinary payload data while loading the program buffer. */
    if (n->phase != NOR_COUNT && n->phase != NOR_DATA && value == 0xf0) {
        n->phase = NOR_READ;
        n->pending = NOR_NONE;
        n->operation_fails = false;
        return true;
    }
    switch (n->phase) {
    case NOR_READ:
        if (at == 0xaaa && value == 0xaa) { n->phase = NOR_UNLOCK1; return true; }
        break;
    case NOR_UNLOCK1:
        if (at == 0x554 && value == 0x55) { n->phase = NOR_UNLOCK2; return true; }
        break;
    case NOR_UNLOCK2:
        if (at == 0xaaa && value == 0x80) { n->phase = NOR_ERASE1; return true; }
        if (value == 0x25) {
            n->command_address = at;
            n->phase = NOR_COUNT;
            return true;
        }
        break;
    case NOR_ERASE1:
        if (at == 0xaaa && value == 0xaa) { n->phase = NOR_ERASE2; return true; }
        break;
    case NOR_ERASE2:
        if (at == 0x554 && value == 0x55) { n->phase = NOR_ERASE3; return true; }
        break;
    case NOR_ERASE3:
        if (value == 0x30) { begin(n, NOR_ERASE, at, pc); return true; }
        break;
    case NOR_COUNT:
        if (at != n->command_address || value >= GM5_NOR_BUFFER/2)
            return fault(n, "nor_invalid_buffer_count", at, pc);
        n->words = (uint32_t)value+1;
        n->received = 0;
        n->phase = NOR_DATA;
        return true;
    case NOR_DATA:
        if (!n->received) {
            n->start = at;
            if ((at/GM5_NOR_SECTOR != n->command_address/GM5_NOR_SECTOR)
                    || (at & (GM5_NOR_BUFFER-1U)) + n->words*2 > GM5_NOR_BUFFER
                    || (uint64_t)at+n->words*2 > GM5_NOR_SIZE)
                return fault(n, "nor_buffer_boundary", at, pc);
        }
        if (at != n->start+n->received*2)
            return fault(n, "nor_nonsequential_buffer", at, pc);
        n->buffer[n->received++] = value;
        if (n->received == n->words) n->phase = NOR_CONFIRM;
        return true;
    case NOR_CONFIRM:
        if (at == n->command_address && value == 0x29) {
            begin(n, NOR_PROGRAM, n->start, pc);
            return true;
        }
        break;
    case NOR_BUSY:
        if (n->operation_fails && !n->remaining_reads && at == 0xaaa && value == 0xaa) {
            n->phase = NOR_ABORT1;
            return true;
        }
        break;
    case NOR_ABORT1:
        if (at == 0x554 && value == 0x55) { n->phase = NOR_ABORT2; return true; }
        break;
    case NOR_ABORT2:
        /* The common reset handling above accepts the final F0 command. */
        break;
    }
    return fault(n, "nor_unmodeled_command", at, pc);
}
bool gm5_nor_read(struct gm5_nor *n, uint32_t at, void *out, unsigned size, uint32_t pc) {
    if (!size || at >= GM5_NOR_SIZE || size > GM5_NOR_SIZE-at)
        return fault(n, "nor_invalid_read_address", at, pc);
    ++n->reads;
    if (n->phase == NOR_BUSY) {
        bool correct_address = n->pending == NOR_PROGRAM
            ? at == n->poll_address : at/GM5_NOR_SECTOR == n->start/GM5_NOR_SECTOR;
        if (!correct_address || size > 2)
            return fault(n, "nor_unmodeled_status_read", at, pc);
        if (n->remaining_reads || n->operation_fails) {
            uint16_t target = n->pending == NOR_ERASE ? 0xffff : n->buffer[n->words-1];
            uint16_t status = (target ^ 0x80) & (uint16_t)~0x22;
            if (n->remaining_reads) --n->remaining_reads;
            else status |= 0x20; /* DQ5 failure after the configured busy polls. */
            ((uint8_t *)out)[0] = status;
            if (size == 2) ((uint8_t *)out)[1] = status>>8;
            return true;
        }
        if (!complete(n, pc)) return false;
    }
    memcpy(out, n->data+at, size);
    return true;
}
void gm5_nor_report(const struct gm5_nor *n, FILE *stream) {
    fprintf(stream, "{\"bytes\":%u,\"sector_bytes\":%u,\"buffer_bytes\":%u,\"erase_attempts\":%u,\"program_attempts\":%u,\"erases\":%u,\"programs\":%u,\"reads\":%" PRIu64 ",\"writes\":%" PRIu64 ",\"erased_bytes\":%" PRIu64 ",\"programmed_bytes\":%" PRIu64 ",\"zero_to_one_words\":%" PRIu64 ",\"phase\":%d,\"pending\":%d}",
            GM5_NOR_SIZE, GM5_NOR_SECTOR, GM5_NOR_BUFFER, n->erase_attempts, n->program_attempts,
            n->erases, n->programs, n->reads, n->writes, n->erased_bytes, n->programmed_bytes,
            n->zero_to_one_words, (int)n->phase, (int)n->pending);
}
