/* Fixed-geometry virtual GM5 NOR command model. GPL-3.0-or-later. */
#ifndef GM5_NOR_MODEL_H
#define GM5_NOR_MODEL_H
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

enum { GM5_NOR_SIZE = 32 * 1024 * 1024, GM5_NOR_SECTOR = 128 * 1024,
       GM5_NOR_BUFFER = 1024 };
enum gm5_nor_phase { NOR_READ, NOR_UNLOCK1, NOR_UNLOCK2, NOR_ERASE1,
                     NOR_ERASE2, NOR_ERASE3, NOR_COUNT, NOR_DATA,
                     NOR_CONFIRM, NOR_BUSY, NOR_ABORT1, NOR_ABORT2 };
enum gm5_nor_operation { NOR_NONE, NOR_ERASE, NOR_PROGRAM };
struct gm5_nor {
    uint8_t *data;
    FILE *log;
    enum gm5_nor_phase phase;
    enum gm5_nor_operation pending;
    uint32_t command_address, start, length, words, received, poll_address;
    uint32_t busy_reads, remaining_reads, fail_erase, fail_program, cut_after;
    uint32_t erase_attempts, program_attempts, erases, programs, completed;
    uint64_t reads, writes, erased_bytes, programmed_bytes, zero_to_one_words;
    bool operation_fails;
    uint16_t buffer[GM5_NOR_BUFFER / 2];
    const char *halt_reason;
};
void gm5_nor_init(struct gm5_nor *nor, uint8_t *data);
bool gm5_nor_write(struct gm5_nor *nor, uint32_t offset, uint16_t value, uint32_t pc);
bool gm5_nor_read(struct gm5_nor *nor, uint32_t offset, void *out, unsigned size, uint32_t pc);
void gm5_nor_report(const struct gm5_nor *nor, FILE *stream);
#endif
