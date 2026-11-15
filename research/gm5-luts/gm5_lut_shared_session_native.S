/* CPU0 read view of an already owned, optionally pinned Library session.
 * CALL F0/20,A0=owner LIL1 ->D0=uncached allocation base,D1=capacity/0,0.
 * Request/capacity must be2560. Caller already owns a reference. This does
 * not permit mutation/release of shared import/table leases: their original
 * exclusive lut_image_view remains unchanged. No allocation, wait or AddRef.
 */
        .text
        .am33_2
        .global lut_session_view_shared,lut_session_view_shared_end
        .global lut_session_view_for_submit,lut_session_views_end
        .extern lut_ram_span,original_exclusive_view
.ifdef LUT_ADJACENT_POOL
        .extern lut_adjacent_pool_validate
.endif
lut_session_view_shared:
        mov a0,a3
        mov (0x8050),d0
        cmp 0,d0
        bne .Lbad
        mov a3,d0
        and 3,d0
        bne .Lbad
        mov a3,d0
        mov 32,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbad
        mov (a3),d0
        cmp 0x314c494c,d0
        bne .Lbad
        mov (4,a3),d0
        cmp 1,d0
        bne .Lbad
        mov (12,a3),d0
.ifdef LUT_ADJACENT_POOL
        mov d0,a0
        call lut_adjacent_pool_validate,[d2,d3,a2,a3],20
        cmp 1,d0
.else
        cmp 0x70394dbc,d0
.endif
        bne .Lbad
        mov (24,a3),d0
        cmp 2560,d0
        bne .Lbad
        mov (20,a3),d0
        cmp 2560,d0
        bne .Lbad
        mov (8,a3),d0
        mov d0,d1
        and 3,d1
        bne .Lbad
        mov 28,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbad
        mov (8,a3),a2
        mov (a2),d0
        cmp 0x7be2e290,d0
        bne .Lbad
        mov (4,a2),d0
        cmp 1,d0
        blt .Lbad
        mov (12,a2),d0
        cmp 1,d0
        bne .Lbad
        mov (24,a2),d0
        mov (12,a3),d1
        cmp d1,d0
        bne .Lbad
        mov (16,a2),d0
        mov (16,a3),d1
        cmp d1,d0
        bne .Lbad
        mov (20,a2),d1
        cmp 2560,d1
        bne .Lbad
.ifdef LUT_ADJACENT_POOL
        mov (12,a3),a0
        mov (12,a0),d2
        cmp d2,d0
        bcs .Lbad
        mov (16,a0),d3
        add d2,d3
        mov d0,d2
        add d1,d2
        bcs .Lbad
        cmp d3,d2
        bhi .Lbad
.else
        cmp 0x13400000,d0
        bcs .Lbad
        mov d0,d2
        add d1,d2
        bcs .Lbad
        cmp 0x18600000,d2
        bhi .Lbad
.endif
        and 0x0fffffff,d0
        or 0xb0000000,d0
        ret [d2,d3,a2,a3],20
.Lbad:
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20
lut_session_view_shared_end:

/* Preserve the generic async adapter's original exclusive-owner contract,
 * including its older1984-byte requests. Only a failed exclusive lookup may
 * use the narrowly checked shared2560-byte manager-session contract. */
lut_session_view_for_submit:
        mov a0,a3
        call original_exclusive_view,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lsubmit_return
        mov a3,a0
        call lut_session_view_shared,[d2,d3,a2,a3],20
.Lsubmit_return:
        ret [d2,d3,a2,a3],20
lut_session_views_end:
