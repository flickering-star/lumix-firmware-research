/* Explicit owned image-memory lease; no CPU bus mapping or data access.
 * open(A0=fresh zero32-byte record,D0=request1..1MiB),close(A0=record),
 * CALL F0/20. Uses original region1 object and raw descriptor allocation.
 * LIL1:0magic,4state1owned/2closed/3failed,8handle,12pool,16bus,
 * 20actual capacity,24request,28status. No active library/global allocation.
 * Raw child construction AddRefs the pool; its original destructor does not
 * Release it. This lease balances that one parent reference on final close.
 * Close refuses an externally shared child; no guessed owner reference drops.
 */
        .text
        .am33_2
        .global lut_image_lease_open,lut_image_lease_close,lut_image_lease_end
        .extern lut_ram_span,native_image_pool
.ifdef LUT_ADJACENT_POOL
        .extern lut_adjacent_pool_validate,lut_adjacent_pool_collect
.endif
        .equ MAGIC,0x314c494c

lut_image_lease_open:
        mov d0,d3
        cmp 1,d3
        bcs .Largs
        cmp 0x100000,d3
        bhi .Largs
        mov a0,d0
        and 3,d0
        bne .Largs
        mov a0,a3
        mov a0,d0
        mov 32,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov a3,a0
        mov 8,d1
.Lempty:
        mov (a0),d0
        cmp 0,d0
        bne .Lbusy
        inc4 a0
        sub 1,d1
        bne .Lempty
        add -32,sp
        mov MAGIC,d0
        mov d0,(a3)
        mov 3,d0
        mov d0,(4,a3)
        mov d3,(24,a3)
        mov 1,d0
        call native_image_pool,[a2],8
        cmp 0,a0
        beq .Lopen_failed
        mov a0,a2
        mov (a2),d0
        cmp 0x7be2e240,d0
        bne .Lrelease_get_ref
        mov (a2),a1
        mov (16,a1),a1
        mov d3,d0
        clr d1
        calls (a1)
        mov a0,(4,sp)
        /* Drop the reference returned by native_image_pool, retaining only
         * the child's constructor reference until lease close. */
        mov a2,a0
        mov (a2),a1
        mov (4,a1),a1
        calls (a1)
        mov (4,sp),d0
        cmp 0,d0
.ifdef LUT_ADJACENT_POOL
        bne .Lchild_ready
        mov a2,a0
        call lut_adjacent_pool_collect,[d2,d3,a2,a3],20
        bra .Lopen_failed
.Lchild_ready:
.else
        beq .Lopen_failed
.endif
        mov (4,sp),a0
        mov (a0),a1
        mov (12,a1),d2
        mov sp,a1
        add 8,a1
        mov d2,a2
        calls (a2)
        mov (4,sp),a0
        mov (24,a0),a2
        mov (16,sp),d0
        cmp d3,d0
        bcs .Lbad_descriptor
        mov (12,sp),d1
        mov (12,a2),d2
        cmp d2,d1
        bcs .Lbad_descriptor
        add d1,d0
        bcs .Lbad_descriptor
        mov (16,a2),d1
        add d2,d1
        bcs .Lbad_descriptor
        cmp d1,d0
        bhi .Lbad_descriptor
        mov (12,sp),d0
        mov d0,(16,a3)
        mov (16,sp),d0
        mov d0,(20,a3)
        mov (4,sp),d0
        mov d0,(8,a3)
        mov d0,a0
        mov (24,a0),d0
        mov d0,(12,a3)
        mov 1,d0
        mov d0,(4,a3)
.ifdef LUT_ADJACENT_POOL
        cmp 3072,d3
        bne .Lowned_ready
        mov (16,a3),d0
        and 0x0fffffff,d0
        or 0xb0000000,d0
        mov d0,a0
        add 2560,a0
        mov 6,d1
        clr d0
.Lzero_touch:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lzero_touch
.Lowned_ready:
.endif
        clr d0
        ret [d2,d3,a2,a3],52
.Lbad_descriptor:
        mov (4,sp),a0
        mov (a0),a1
        mov (4,a1),a1
        calls (a1)
        mov a2,a0
        mov (a2),a1
        mov (4,a1),a1
        calls (a1)
        mov -5,d0
        mov d0,(28,a3)
        ret [d2,d3,a2,a3],52
.Lrelease_get_ref:
        mov a2,a0
        mov (a2),a1
        mov (4,a1),a1
        calls (a1)
.Lopen_failed:
        mov -3,d0
        mov d0,(28,a3)
        ret [d2,d3,a2,a3],52
.Largs:
        mov -1,d0
        ret [d2,d3,a2,a3],20
.Lbusy:
        mov -2,d0
        ret [d2,d3,a2,a3],20

lut_image_lease_close:
        mov a0,d0
        and 3,d0
        bne .Largs
        mov a0,a3
        mov a0,d0
        mov 32,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov (a3),d0
        cmp MAGIC,d0
        bne .Largs
        mov (4,a3),d0
        cmp 2,d0
        beq .Lclosed
        cmp 3,d0
        beq .Lfailed_close
        cmp 1,d0
        bne .Lbusy
        mov (8,a3),d0
        mov d0,d1
        and 3,d1
        bne .Largs
        mov 28,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov (8,a3),a0
        mov (a0),d0
        cmp 0x7be2e290,d0
        bne .Largs
        mov (4,a0),d0
        cmp 1,d0
        bne .Lshared
        mov (24,a0),d0
        mov (12,a3),d1
        cmp d1,d0
        bne .Largs
        cmp 0x70394dbc,d1
.ifdef LUT_ADJACENT_POOL
        beq .Lknown_parent
        mov d1,a0
        call lut_adjacent_pool_validate,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Largs
        mov (8,a3),a0
.Lknown_parent:
.else
.ifdef LUT_RESERVED_POOL
        beq .Lknown_parent
        cmp 0xbbe50040,d1
        bne .Largs
.Lknown_parent:
.else
        bne .Largs
.endif
.endif
        mov (12,a3),a2
        mov (a2),d0
        cmp 0x7be2e240,d0
        bne .Largs
        mov (4,a2),d0
        cmp 2,d0
        bcs .Largs
        mov (a0),a1
        mov (4,a1),a1
        calls (a1)
        cmp 0,d0
        bne .Lshared
        mov a2,a0
        mov (a2),a1
        mov (4,a1),a1
        calls (a1)
.ifdef LUT_ADJACENT_POOL
        mov a2,a0
        call lut_adjacent_pool_collect,[d2,d3,a2,a3],20
.endif
        clr d0
        mov d0,(8,a3)
        mov d0,(12,a3)
        mov d0,(16,a3)
        mov d0,(20,a3)
        mov d0,(28,a3)
        mov 2,d0
        mov d0,(4,a3)
.Lclosed:
        clr d0
        ret [d2,d3,a2,a3],20
.Lfailed_close:
        mov (8,a3),d0
        cmp 0,d0
        bne .Lbusy
        mov 2,d0
        mov d0,(4,a3)
        bra .Lclosed
.Lshared:
        mov -4,d0
        ret [d2,d3,a2,a3],20
lut_image_lease_end:
