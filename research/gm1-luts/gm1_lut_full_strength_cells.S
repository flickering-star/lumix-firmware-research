/* GM1 registered cell ownership and gated selected-request snapshots.
 * Public APIs CALL F0/20; explicit normal-worker cell mutation only.
 * adopt(A0CTRL,D0cell,A1exclusive retained2348B source lease) moves ownership
 * and zeros the caller's32B record on success. Rejected sources stay owned.
 * clear(A0CTRL,D0cell) releases that cell. Both force native Standard before
 * mutation when a LUT style is selected. No file/boot/producer entry hook.
 * begin(A0CTRL,D0preview0/capture1,D1ring index)->D0status,D1slot/0.
 * The source gate spans Claim, source copy, and Publish. Queued jobs
 * own independent tables; callers must Finish only after the last consumer.
 * Cell64: LIL1[0..31],32CPU view,36generation,40..59reserved,60ready1.
 */
        .text
        .am33_2
        .global lut_gm1_packed_cell_adopt,lut_gm1_packed_cell_clear,lut_gm1_packed_request_begin
        .global lut_gm1_packed_cell_requests_end
        .extern lut_gm1_control_get,lut_image_view,lut_image_lease_close,lut_ram_span
        .extern lut_gm1_record_check_table,lut_gm1_job_capture
        .extern lut_gm1_request_claim,lut_gm1_request_publish,lut_gm1_request_finish
        .extern native_context,native_ui_style

/* A0CTRL ->D0status,D1raw. No waiting; mask only the phase/gate claim. */
.Lgate:
        add -8,sp
        mov a0,a3
        call lut_gm1_control_get,[d2,d3,a2,a3],20
        cmp a3,d0
        bne .Lgate_bad
        cmp 0,d0
        beq .Lgate_bad
        mov (12,a3),d0
        cmp 2,d0
        bne .Lgate_bad
        mov (64,a3),d0
        cmp 13,d0
        bne .Lgate_bad
        mov a3,a0
        add 32,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lgate_bad
        cmp 3072,d1
        bne .Lgate_bad
        mov d0,a2
        mov (16,a3),d1
        cmp d1,d0
        bne .Lgate_bad
        mov (32,a2),d0
        cmp 0x31504647,d0
        bne .Lgate_bad
        mov (36,a2),d0
        cmp a3,d0
        bne .Lgate_bad
        mov psw,d3
        and 63487,psw
        mov (12,a3),d0
        cmp 2,d0
        bne .Lgate_busy
        mov (16,a3),d0
        cmp a2,d0
        bne .Lgate_busy
        mov (76,a3),d0
        cmp 0,d0
        bne .Lgate_busy
        mov 1,d0
        mov d0,(76,a3)
        mov d3,psw
        mov a2,d1
        clr d0
        ret [d2,d3,a2,a3],28
.Lgate_busy:
        mov d3,psw
        mov -2,d0
        bra .Lgate_return
.Lgate_bad:
        mov -18,d0
.Lgate_return:
        clr d1
        ret [d2,d3,a2,a3],28

/* Caller A3 retains valid controller/gate. */
.Lungate:
        mov psw,d3
        and 63487,psw
        clr d1
        mov d1,(76,a3)
        mov d3,psw
        ret [d2,d3,a2,a3],20
.Lworker:
        mov (0x93f00030),d0
        cmp 0x7be2ce04,d0
        bne .Linvalid
        call native_context,[],0
        extbu d0
        cmp 0,d0
        bne .Linvalid
        ret [d2,d3,a2,a3],20
.Linvalid:
        mov -18,d0
        ret [d2,d3,a2,a3],20

/* A0/32B source record must be disjoint from A1/D1 range, aliases included. */
.Lexternal:
        add -16,sp
        mov a1,(4,sp)
        mov d1,(8,sp)
        mov a0,d0
        mov 32,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lexternal_bad
        mov d0,d2
        mov d1,d3
        mov (4,sp),d0
        mov (8,sp),d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lexternal_bad
        cmp d3,d0
        bcc .Lexternal_ok
        cmp d2,d1
        bhi .Lexternal_bad
.Lexternal_ok:
        clr d0
        ret [d2,d3,a2,a3],36
.Lexternal_bad:
        mov -1,d0
        ret [d2,d3,a2,a3],36

/* Source A0 must not duplicate any session/job/cell child or place its lease
 * inside any owned metadata/payload. A3CTRL; gate held; returns0/-1. */
.Lsource:
        add -16,sp
        mov a0,a2
        mov (16,a3),d0
        mov d0,(4,sp)
        mov a2,a0
        mov a3,a1
        mov 128,d1
        call .Lexternal,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lsource_bad
        mov a2,a0
        mov (0x708f47a4),a1
        mov 336,d1
        call .Lexternal,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lsource_bad
        mov a2,a0
        mov (4,sp),a1
        mov 3072,d1
        call .Lexternal,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lsource_bad
        mov a2,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lsource_bad
        mov d0,a1
        mov a2,a0
        call .Lexternal,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lsource_bad
        mov (8,a2),d2
        mov (40,a3),d0
        cmp d2,d0
        beq .Lsource_bad
        clr d3
.Lsource_job:
        mov d3,d0
        asl 7,d0
        mov (4,sp),a0
        add 96,a0
        add d0,a0
        mov (8,a0),d0
        cmp d2,d0
        beq .Lsource_bad
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lsource_bad
        mov d0,a1
        mov a2,a0
        call .Lexternal,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lsource_bad
        inc d3
        cmp 13,d3
        bcs .Lsource_job
        clr d3
.Lsource_cell:
        mov d3,d0
        asl 6,d0
        mov (4,sp),a0
        add 1792,a0
        add d0,a0
        mov (a0),d0
        cmp 0,d0
        beq .Lsource_next
        mov (8,a0),d0
        cmp d2,d0
        beq .Lsource_bad
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lsource_bad
        mov d0,a1
        mov a2,a0
        call .Lexternal,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lsource_bad
.Lsource_next:
        inc d3
        cmp 10,d3
        bcs .Lsource_cell
        clr d0
        ret [d2,d3,a2,a3],36
.Lsource_bad:
        mov -1,d0
        ret [d2,d3,a2,a3],36

.Lstandard:
        movbu (0x70101252),d0
        cmp 7,d0
        bcs .Lstandard_return
        cmp 16,d0
        bhi .Lstandard_return
        clr d0
        call native_ui_style,[d2,d3],12
.Lstandard_return:
        ret [d2,d3,a2,a3],20

lut_gm1_packed_cell_adopt:
        add -28,sp
        mov a0,a3
        mov d0,(4,sp)
        mov a1,(8,sp)
        cmp 10,d0
        bcc .Ladopt_args
        call .Lgate,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Ladopt_return
        mov d1,(12,sp)
        call .Lworker,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Ladopt_release
        mov (8,sp),a0
        mov a0,d0
        and 3,d0
        bne .Ladopt_invalid
        mov a0,d0
        mov 32,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Ladopt_invalid
        mov (8,sp),a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Ladopt_invalid
        cmp 2284,d1
        bcs .Ladopt_invalid
        mov d0,(16,sp)
        mov (8,sp),a0
        mov (24,a0),d0
        cmp 2348,d0
        bne .Ladopt_invalid
        mov (12,a0),d0
        mov (44,a3),d1
        cmp d1,d0
        bne .Ladopt_invalid
        call .Lsource,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Ladopt_release
        mov (16,sp),a0
        call lut_gm1_record_check_table,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Ladopt_release
        mov (72,a3),d0
        cmp -1,d0
        beq .Ladopt_epoch
        inc d0
        mov d0,(20,sp)
        mov (4,sp),d0
        asl 6,d0
        mov (12,sp),a2
        add 1792,a2
        add d0,a2
        call .Lstandard,[d2,d3,a2,a3],20
        mov (a2),d0
        cmp 0,d0
        beq .Ladopt_copy
        mov a2,a0
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Ladopt_release
.Ladopt_copy:
        mov (8,sp),a1
        mov a2,a0
        mov 8,d1
.Lmove_lease:
        mov (a1),d0
        mov d0,(a0)
        clr d0
        mov d0,(a1)
        inc4 a1
        inc4 a0
        sub 1,d1
        bne .Lmove_lease
        mov 8,d1
.Lcell_tail:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lcell_tail
        mov (16,sp),d0
        mov d0,(32,a2)
        mov (20,sp),d0
        mov d0,(36,a2)
        mov d0,(72,a3)
        mov 1,d0
        mov d0,(60,a2)
        mov (4,sp),d1
        asl d1,d0
        mov (0x708f47a4),a0
        movhu (304,a0),d1
        or d1,d0
        movhu d0,(304,a0)
        clr d0
        bra .Ladopt_release
.Ladopt_epoch:
        mov -17,d0
        bra .Ladopt_release
.Ladopt_invalid:
        mov -1,d0
.Ladopt_release:
        mov d0,(24,sp)
        call .Lungate,[d2,d3,a2,a3],20
        mov (24,sp),d0
.Ladopt_return:
        ret [d2,d3,a2,a3],48
.Ladopt_args:
        mov -1,d0
        bra .Ladopt_return

lut_gm1_packed_cell_clear:
        add -16,sp
        mov a0,a3
        mov d0,(4,sp)
        cmp 10,d0
        bcc .Lclear_args
        call .Lgate,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclear_return
        mov d1,(8,sp)
        call .Lworker,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclear_release
        mov (4,sp),d0
        asl 6,d0
        mov (8,sp),a2
        add 1792,a2
        add d0,a2
        call .Lstandard,[d2,d3,a2,a3],20
        mov (a2),d0
        cmp 0,d0
        beq .Lclear_words
        mov a2,a0
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclear_release
.Lclear_words:
        mov a2,a0
        mov 16,d1
        clr d0
.Lclear_loop:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lclear_loop
        mov (4,sp),d1
        mov 1,d0
        asl d1,d0
        not d0
        mov (0x708f47a4),a0
        movhu (304,a0),d1
        and d1,d0
        movhu d0,(304,a0)
        clr d0
.Lclear_release:
        mov d0,(12,sp)
        call .Lungate,[d2,d3,a2,a3],20
        mov (12,sp),d0
.Lclear_return:
        ret [d2,d3,a2,a3],36
.Lclear_args:
        mov -1,d0
        bra .Lclear_return

lut_gm1_packed_request_begin:
        add -24,sp
        mov a0,a3
        mov d0,(4,sp)
        mov d1,(8,sp)
        call .Lgate,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lbegin_no_slot
        mov d1,(12,sp)
        mov a3,a0
        mov (4,sp),d0
        mov (8,sp),d1
        call lut_gm1_request_claim,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lbegin_failed_claim
        mov d1,a2
        mov (112,a2),d0
        cmp 7,d0
        bcs .Lbegin_publish
        cmp 16,d0
        bhi .Lbegin_invalid
        sub 7,d0
        mov d0,(16,sp)
        asl 6,d0
        mov (12,sp),a1
        add 1792,a1
        add d0,a1
        mov (60,a1),d0
        cmp 1,d0
        bne .Lbegin_invalid
        mov (36,a1),d2
        cmp 0,d2
        beq .Lbegin_invalid
        mov a2,a0
        mov (16,sp),d0
        clr d1
        nop
        nop
        mov (100,a2),d3
        call lut_gm1_job_capture,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lbegin_undo
.Lbegin_publish:
        mov a3,a0
        mov a2,a1
        mov (100,a2),d0
        call lut_gm1_request_publish,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lbegin_undo
        call .Lungate,[d2,d3,a2,a3],20
        mov a2,d1
        clr d0
        ret [d2,d3,a2,a3],44
.Lbegin_invalid:
        mov -18,d0
.Lbegin_undo:
        mov d0,(20,sp)
        mov a3,a0
        mov a2,a1
        mov (100,a2),d0
        call lut_gm1_request_finish,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lbegin_cleanup_failed
        mov (20,sp),d0
.Lbegin_failed_claim:
        mov d0,(20,sp)
        call .Lungate,[d2,d3,a2,a3],20
        mov (20,sp),d0
.Lbegin_no_slot:
        clr d1
        ret [d2,d3,a2,a3],44
.Lbegin_cleanup_failed:
        mov d0,(20,sp)
        call .Lungate,[d2,d3,a2,a3],20
        mov (20,sp),d0
        mov a2,d1
        ret [d2,d3,a2,a3],44
lut_gm1_packed_cell_requests_end:
