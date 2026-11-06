/* Behavioral checks of the virtual device, including failed/interrupted writes. */
#include "nor_model.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

static void unlock(struct gm5_nor *n) {
    assert(gm5_nor_write(n, 0xaaa, 0xaa, 0));
    assert(gm5_nor_write(n, 0x554, 0x55, 0));
}
static void erase(struct gm5_nor *n, uint32_t at) {
    unlock(n);
    assert(gm5_nor_write(n, 0xaaa, 0x80, 0));
    unlock(n);
    assert(gm5_nor_write(n, at, 0x30, 0));
}
static void program(struct gm5_nor *n, uint32_t at, uint16_t a, uint16_t b) {
    unlock(n);
    assert(gm5_nor_write(n, at, 0x25, 0));
    assert(gm5_nor_write(n, at, 1, 0));
    assert(gm5_nor_write(n, at, a, 0));
    assert(gm5_nor_write(n, at+2, b, 0));
    assert(gm5_nor_write(n, at, 0x29, 0));
}
static uint16_t poll(struct gm5_nor *n, uint32_t at) {
    uint8_t bytes[2];
    assert(gm5_nor_read(n, at, bytes, 2, 0));
    return bytes[0] | (uint16_t)bytes[1]<<8;
}
int main(void) {
    uint8_t *data = malloc(GM5_NOR_SIZE), *before = malloc(GM5_NOR_SIZE);
    assert(data && before);
    struct gm5_nor n;
    /* Erase affects exactly one sector and completion requires status polls. */
    memset(data, 0x12, GM5_NOR_SIZE);
    memcpy(before, data, GM5_NOR_SIZE);
    gm5_nor_init(&n, data);
    erase(&n, GM5_NOR_SECTOR+2);
    assert(!(poll(&n, GM5_NOR_SECTOR+2)&0x80));
    assert(!(poll(&n, GM5_NOR_SECTOR+2)&0x80));
    assert(!memcmp(data, before, GM5_NOR_SIZE));
    assert(poll(&n, GM5_NOR_SECTOR+2)==0xffff);
    memset(before+GM5_NOR_SECTOR, 0xff, GM5_NOR_SECTOR);
    assert(!memcmp(data, before, GM5_NOR_SIZE) && n.erases==1);
    /* Command-looking values in a loaded buffer remain ordinary payload. */
    program(&n, GM5_NOR_SECTOR, 0xf0, 0x55aa);
    poll(&n, GM5_NOR_SECTOR+2); poll(&n, GM5_NOR_SECTOR+2);
    assert(poll(&n, GM5_NOR_SECTOR+2)==0x55aa);
    before[GM5_NOR_SECTOR]=0xf0; before[GM5_NOR_SECTOR+1]=0;
    before[GM5_NOR_SECTOR+2]=0xaa; before[GM5_NOR_SECTOR+3]=0x55;
    assert(!memcmp(data, before, GM5_NOR_SIZE) && n.programs==1);
    /* Programming cannot restore erased bits; the readback exposes masking. */
    gm5_nor_init(&n, data); n.busy_reads=0;
    memset(data, 0, GM5_NOR_SIZE);
    program(&n, 0, 0xffff, 0x007e);
    assert(poll(&n, 2)==0 && n.zero_to_one_words==2);
    /* A malformed command never changes the backing image. */
    gm5_nor_init(&n, data);
    assert(!gm5_nor_write(&n, 0xaaa, 0x55, 0));
    assert(n.halt_reason && !data[0] && !data[GM5_NOR_SIZE-1]);
    /* Buffer count overflow and crossing a 1 KiB page are refused. */
    gm5_nor_init(&n, data); unlock(&n);
    assert(gm5_nor_write(&n, 0, 0x25, 0));
    assert(!gm5_nor_write(&n, 0, 512, 0));
    gm5_nor_init(&n, data); unlock(&n);
    assert(gm5_nor_write(&n, 1022, 0x25, 0));
    assert(gm5_nor_write(&n, 1022, 1, 0));
    assert(!gm5_nor_write(&n, 1022, 0xa5, 0));
    /* Injected program failure reports DQ5 and leaves every byte unchanged. */
    gm5_nor_init(&n, data); n.fail_program=1; n.busy_reads=0;
    memset(data, 0xff, GM5_NOR_SIZE); memcpy(before,data,GM5_NOR_SIZE);
    program(&n, 0, 0x1234, 0x5678);
    assert((poll(&n, 2)&0xa0)==0xa0 && !n.programs);
    assert(!memcmp(data,before,GM5_NOR_SIZE));
    unlock(&n);
    assert(gm5_nor_write(&n, 0xaaa, 0xf0, 0) && n.phase==NOR_READ);
    /* A simulated cut after commit preserves that operation for later loading. */
    gm5_nor_init(&n,data); n.cut_after=1; n.busy_reads=0;
    program(&n,0,0x1234,0x5678);
    uint8_t bytes[2];
    assert(!gm5_nor_read(&n,2,bytes,2,0) && n.programs==1);
    assert(data[0]==0x34 && data[1]==0x12 && data[2]==0x78 && data[3]==0x56);
    assert(data[4]==0xff && !strcmp(n.halt_reason,"nor_power_cut"));
    /* Upper device bounds and the last erase sector remain exact. */
    gm5_nor_init(&n,data); n.busy_reads=0; memset(data,0x12,GM5_NOR_SIZE);
    erase(&n,GM5_NOR_SIZE-2); assert(poll(&n,GM5_NOR_SIZE-2)==0xffff);
    assert(data[GM5_NOR_SIZE-GM5_NOR_SECTOR-1]==0x12);
    assert(!gm5_nor_write(&n,GM5_NOR_SIZE,0xf0,0));
    assert(!gm5_nor_read(&n,GM5_NOR_SIZE-1,bytes,2,0));
    free(before); free(data);
    puts("NOR behavioral controls passed");
    return 0;
}
