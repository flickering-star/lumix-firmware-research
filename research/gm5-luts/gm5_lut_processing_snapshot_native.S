/* Immutable LUT state for an explicitly captured processing job.
 * All entries CALL F0/20, CPU0. The caller owns an exclusive native LIL1
 * lease with request4568 (32prefix +4504body +32suffix). No allocation,
 * automatic SD access, current-style lookup or actual queue hook is here.
 * capture(A0=controller,A1=lease,D0=cell0..9,D1=captured strength0..100)
 * -> D0status,D1=owned job body on success. Body must initially be zero.
 * bind(A0=lease,A1=original316-byte Standard packed metadata) ->status.
 * The owner retains the lease through the last original table copier use.
 * +0LJS1,+4kind1table/2exactBypass,+8cell,+12percent,+16generation,
 * +20tableptr,+24/+28cache words,+32complete2284table,+2316scratch2188.
 * Capture publishes magic last. Bind never changes the owned job.
 */
        .text
        .am33_2
        .global lut_job_capture,lut_job_bind,lut_job_view,lut_job_snapshot_end
        .extern lut_image_view,lut_ram_span,lut_controller_snapshot
        .extern lut_strength_generate,lut_runtime_check_table,native_memcpy

lut_job_view:
        mov a0,a3
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lview_bad
        cmp 4568,d1
        bcs .Lview_bad
        mov (24,a3),d2
        cmp 4568,d2
        bne .Lview_bad
        add 32,d0
        ret [d2,d3,a2,a3],20
.Lview_bad:
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20

lut_job_capture:
        add -32,sp
        mov a0,(4,sp)
        mov a1,(8,sp)
        mov d0,(12,sp)
        mov d1,(16,sp)
        cmp 10,d0
        bcc .Lcapture_args
        cmp 100,d1
        bhi .Lcapture_args
        mov (0x8050),d0
        cmp 0,d0
        bne .Lcapture_args
        mov a1,a0
        call lut_job_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lcapture_args
        mov d0,a3
        mov d0,(20,sp)
        mov a3,a0
        mov 1126,d1
.Lfresh:
        mov (a0),d0
        cmp 0,d0
        bne .Lcapture_busy
        inc4 a0
        sub 1,d1
        bne .Lfresh
        mov (16,sp),d0
        cmp 0,d0
        beq .Lbypass
        mov (4,sp),a0
        mov a3,a1
        add 32,a1
        mov (12,sp),d0
        call lut_controller_snapshot,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lcapture_error
        mov d1,(24,sp)
        mov (16,sp),d0
        cmp 100,d0
        beq .Lpublish_table
        mov a3,a0
        add 2316,a0
        mov a3,a1
        add 128,a1
        call lut_strength_generate,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lcapture_error
        mov a3,a0
        add 128,a0
        mov a3,a1
        add 2316,a1
        mov 2188,d0
        call native_memcpy,[a2,a3],8
.Lpublish_table:
        mov 1,d0
        mov d0,(4,a3)
        mov (24,sp),d0
        mov d0,(16,a3)
        mov d0,(28,a3)
        mov a3,d0
        add 32,d0
        mov d0,(20,a3)
        mov (16,sp),d0
        asl 16,d0
        or 0x4c000000,d0
        mov (12,sp),d1
        or d1,d0
        mov d0,(24,a3)
        bra .Lpublish_common
.Lbypass:
        mov 2,d0
        mov d0,(4,a3)
.Lpublish_common:
        mov (12,sp),d0
        mov d0,(8,a3)
        mov (16,sp),d0
        mov d0,(12,a3)
        mov 0x31534a4c,d0
        mov d0,(a3)
        mov a3,d1
        clr d0
        ret [d2,d3,a2,a3],52
.Lcapture_busy:
        mov -2,d0
        bra .Lcapture_error
.Lcapture_args:
        mov -1,d0
.Lcapture_error:
        clr d1
        ret [d2,d3,a2,a3],52

lut_job_bind:
        add -16,sp
        mov a0,(12,sp)
        mov a1,a2
        mov (0x8050),d0
        cmp 0,d0
        bne .Lbind_args
        mov a2,d0
        and 3,d0
        bne .Lbind_args
        mov a2,d0
        mov 316,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbind_args
        mov d0,(4,sp)
        mov d1,(8,sp)
        mov (12,sp),a0
        call lut_job_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbind_args
        mov d0,a3
        mov 4504,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        mov (4,sp),d2
        cmp d1,d2
        bcc .Lpacket_disjoint
        mov (8,sp),d2
        cmp d0,d2
        bhi .Lbind_args
.Lpacket_disjoint:
        /* The packed record may not alias its external lease descriptor. */
        mov (12,sp),d0
        mov 32,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        mov (4,sp),d2
        cmp d1,d2
        bcc .Llease_disjoint
        mov (8,sp),d2
        cmp d0,d2
        bhi .Lbind_args
.Llease_disjoint:
        mov (a3),d0
        cmp 0x31534a4c,d0
        bne .Lbind_invalid
        mov (8,a3),d2
        cmp 10,d2
        bcc .Lbind_invalid
        mov (12,a3),d3
        cmp 100,d3
        bhi .Lbind_invalid
        movbu (4,a2),d0
        cmp 1,d0
        bhi .Lbind_args
        movbu (12,a2),d0
        cmp 0,d0
        bne .Lbind_args
        cmp 0,d3
        beq .Lbind_bypass
        mov (4,a3),d0
        cmp 1,d0
        bne .Lbind_invalid
        mov (16,a3),d0
        cmp 0,d0
        beq .Lbind_invalid
        mov (28,a3),d1
        cmp d1,d0
        bne .Lbind_invalid
        mov d3,d0
        asl 16,d0
        or 0x4c000000,d0
        or d2,d0
        mov (24,a3),d1
        cmp d1,d0
        bne .Lbind_invalid
        mov a3,d0
        add 32,d0
        mov (20,a3),d1
        cmp d1,d0
        bne .Lbind_invalid
        mov d0,a0
        call lut_runtime_check_table,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lbind_invalid
        /* Initial integration is deliberately limited to the stock neutral
         * Standard discriminator observed in both original wrappers. */
        movbu (31,a2),d0
        cmp 22,d0
        bne .Lbind_args
        mov 12,d0
        movbu d0,(31,a2)
        mov (20,a3),d0
        mov d0,(300,a2)
        mov (24,a3),d0
        mov d0,(304,a2)
        mov (28,a3),d0
        mov d0,(308,a2)
        clr d0
        ret [d2,d3,a2,a3],36
.Lbind_bypass:
        mov (4,a3),d0
        cmp 2,d0
        bne .Lbind_invalid
        mov a3,a0
        add 16,a0
        mov 4,d1
.Lbypass_zero:
        mov (a0),d0
        cmp 0,d0
        bne .Lbind_invalid
        inc4 a0
        sub 1,d1
        bne .Lbypass_zero
        /* Exact0% endpoint: every packed byte remains original Standard. */
        clr d0
        ret [d2,d3,a2,a3],36
.Lbind_args:
        mov -1,d0
        ret [d2,d3,a2,a3],36
.Lbind_invalid:
        mov -18,d0
        ret [d2,d3,a2,a3],36
lut_job_snapshot_end:
