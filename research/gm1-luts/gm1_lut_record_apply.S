/* GM1 owned-table binding after its complete original constructor.
 * CALL F0/20: A0=5856-byte parent, A1=live native table lease,
 * D0/D1=captured eight-byte key. Return D0=0 or-1; no allocation/registry/UI.
 * Validates the complete2284-byte canonical descriptor and six-bit nodes
 * before any destination write. Original bank copier owns the payload copy.
 * Caller must serialize the lease and retain it through this synchronous call.
 * This component has no producer/queue/firmware hook or physical ISP proof.
 */
        .text
        .am33_2
        .global lut_gm1_record_apply,lut_gm1_record_apply_code_end,lut_gm1_record_apply_end
        .global lut_gm1_record_check_table
        .extern lut_image_view,lut_ram_span,native_banked_copy

lut_gm1_record_apply:
        add -28,sp
        mov a0,(4,sp)
        mov a1,(8,sp)
        mov d0,(12,sp)
        mov d1,(16,sp)
        mov (0x8050),d0
        cmp 0,d0
        bne .Lreject
        mov a0,d0
        and 3,d0
        bne .Lreject
        mov a0,d0
        cmp 0x70000000,d0
        bcs .Lreject
        cmp 0x70ffe920,d0
        bhi .Lreject
        mov (2696,a0),d0
        cmp 1,d0
        bhi .Lreject
        mov (2724,a0),d1
        cmp d0,d1
        bne .Lreject
        movhu (2700,a0),d0
        cmp 128,d0
        beq .Lparent_valid
        cmp 131,d0
        bne .Lreject
.Lparent_valid:
        mov a1,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lreject
        cmp 2284,d1
        bcs .Lreject
        mov d0,a3
        mov d0,(20,sp)
        and 3,d0
        bne .Lreject
        /* The external lease descriptor must not overlap the destination. */
        mov (8,sp),d0
        mov (4,sp),d1
        add 5856,d1
        cmp d1,d0
        bcc .Llease_disjoint
        add 32,d0
        mov (4,sp),d1
        cmp d1,d0
        bhi .Lreject
.Llease_disjoint:
        mov a3,a0
        call lut_gm1_record_check_table,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreject
        mov (4,sp),a2
        mov a2,a0
        add 2736,a0
        mov a3,a1
        call native_banked_copy,[d2,d3,a2,a3],124
        /* Working GM5 uses mode7 for imported Y/Cr/Cb tables. GM1's
         * programmer accepts the same bits; physical output is unverified. */
        mov 7,d0
        movbu d0,(2728,a2)
        mov d0,(2732,a2)
        clr d0
        movhu d0,(2730,a2)
        mov 131,d0
        movhu d0,(2700,a2)
        mov (12,sp),d0
        mov d0,(4924,a2)
        mov (16,sp),d0
        mov d0,(4928,a2)
        clr d0
        ret [d2,d3,a2,a3],48
.Lreject:
        mov -1,d0
        ret [d2,d3,a2,a3],48

/* CALL F0/20: A0=complete2284-byte canonical table -> D0=0/-1.
 * This validates bytes/address eligibility only. Callers must independently
 * retain native ownership and serialize mutation while checking/copying. */
lut_gm1_record_check_table:
        mov a0,a3
        mov a0,d0
        and 3,d0
        bne .Ltable_bad
        mov a3,d0
        mov 2284,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Ltable_bad
        movbu (221,a3),d0
        cmp 0,d0
        bne .Ltable_bad
        mov a3,a2
        mov lut_gm1_record_counts,a1
        mov 8,d2
        mov 96,d3
.Ldescriptor:
        mov (a2),d0
        movhu (a1),d1
        cmp d0,d1
        bne .Ltable_bad
        add 2,a1
        mov a3,d1
        add d3,d1
        mov (4,a2),d0
        cmp d0,d1
        bne .Ltable_bad
        movhu (a2),d0
        add d0,d3
        add 1,d3
        and -2,d3
        mov a3,d1
        add d3,d1
        mov (8,a2),d0
        cmp d0,d1
        bne .Ltable_bad
        movhu (a2),d0
        add d0,d0
        add d0,d3
        add 12,a2
        sub 1,d2
        bne .Ldescriptor
        cmp 2284,d3
        bne .Ltable_bad
        mov a3,a2
        mov 8,d2
.Lbank_values:
        movhu (a2),d3
        mov (4,a2),a0
        mov (8,a2),a1
.Lvalue:
        movbu (a0),d0
        cmp 63,d0
        bhi .Ltable_bad
        movhu (a1),d1
        cmp 4095,d1
        bhi .Ltable_bad
        inc a0
        add 2,a1
        sub 1,d3
        bne .Lvalue
        add 12,a2
        sub 1,d2
        bne .Lbank_values
        clr d0
        ret [d2,d3,a2,a3],20
.Ltable_bad:
        mov -1,d0
        ret [d2,d3,a2,a3],20
lut_gm1_record_apply_code_end:
        .balign 2
lut_gm1_record_counts:
        .hword 125,100,100,80,100,80,80,64
lut_gm1_record_apply_end:
