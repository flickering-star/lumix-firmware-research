/* GM1 explicit owned processing snapshots. All public entries CALL F0/20.
 * Caller owns96B metadata: single frame LIL1[0..31], reserved zero[32..63],
 * +64GMJ1,+68phase1ready/2captured/3capture/4close/5apply/6retire,
 * +72cell,+76reserved0,+80generation,+84key0,+88key1,+92request token.
 * open(A0fresh96B), close(A0job): serialized worker-only allocation APIs.
 * capture(A0job,A1live source lease,D0cell,D1unused,D2generation,D3token).
 * apply(A0job,A1complete original Standard parent,D0token).
 * retire(A0job,D0token): caller invokes only after the final consumer.
 * Capture/Apply/Retire allocate nothing. No UI/registry/queue/boot hook.
 * One4568B child uses the same32prefix/4504body/32suffix as GM5.
 * Body table+32/2284B, scratch+2316/2188B. Source may close after Capture.
 * CPU0 masked phase changes are short; no call/loop/copy runs masked.
 */
        .text
        .am33_2
        .global lut_gm1_packed_job_open,lut_gm1_packed_job_close,lut_gm1_packed_job_capture
        .global lut_gm1_packed_job_apply,lut_gm1_packed_job_retire,lut_gm1_packed_job_end
        .extern lut_ram_span,lut_image_lease_open,lut_image_lease_close,lut_image_view
        .extern lut_gm1_record_check_table,lut_gm1_record_apply
        .extern native_memcpy,native_context
        .equ JOB_MAGIC,0x314a4d47

.Lrecord:
        mov (0x8050),d0
        cmp 0,d0
        bne .Lbad_leaf
        mov a0,d0
        and 3,d0
        bne .Lbad_leaf
        mov a0,d0
        mov 96,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbad_leaf
        clr d0
        ret [d2,d3,a2,a3],20
.Lbad_leaf:
        mov -1,d0
        ret [d2,d3,a2,a3],20
.Lworker:
        call native_context,[],0
        extbu d0
        cmp 0,d0
        bne .Lbad_leaf
        ret [d2,d3,a2,a3],20

/* Normalize aliases before comparing two eligible RAM intervals.
 * A0/D0 first pointer/size, A1/D1 second pointer/size ->0/-1. */
.Ldisjoint:
        add -24,sp
        mov a1,(4,sp)
        mov d1,(8,sp)
        mov d0,d1
        mov a0,d0
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Loverlap
        mov d0,(12,sp)
        mov d1,(16,sp)
        mov (4,sp),d0
        mov (8,sp),d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Loverlap
        mov (16,sp),d2
        cmp d2,d0
        bcc .Lseparate
        mov (12,sp),d2
        cmp d2,d1
        bhi .Loverlap
.Lseparate:
        clr d0
        ret [d2,d3,a2,a3],44
.Loverlap:
        mov -1,d0
        ret [d2,d3,a2,a3],44

/* Valid metadata and exclusive native children ->D0table,D1scratch. */
.Lviews:
        add -12,sp
        mov a0,a3
        call .Lrecord,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lview_bad
        mov (64,a3),d0
        cmp JOB_MAGIC,d0
        bne .Lview_bad
        mov a3,a0
        add 32,a0
        mov 8,d1
.Lreserved_zero:
        mov (a0),d0
        cmp 0,d0
        bne .Lview_bad
        inc4 a0
        sub 1,d1
        bne .Lreserved_zero
        mov a3,a0
        call lut_gm1_packed_frame_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lview_bad
        add 32,d0
        mov d0,(4,sp)
        add 2284,d0
        mov d0,(8,sp)
        mov a3,a0
        mov (4,sp),a1
        mov 96,d0
        mov 2284,d1
        call .Ldisjoint,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lview_bad
        mov (4,sp),d0
        mov (8,sp),d1
        ret [d2,d3,a2,a3],32
.Lview_bad:
        clr d0
        clr d1
        ret [d2,d3,a2,a3],32

.org 240,0xff
lut_gm1_packed_job_open:
        mov a0,a3
        call .Lrecord,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_return
        call .Lworker,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_return
        mov a3,a0
        mov 24,d1
.Lfresh:
        mov (a0),d0
        cmp 0,d0
        bne .Lopen_busy
        inc4 a0
        sub 1,d1
        bne .Lfresh
        mov a3,a0
        mov 4568,d0
        call lut_image_lease_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_cleanup
        mov a3,a0
        call lut_gm1_packed_child_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lopen_view_bad
        mov d0,a0
        add -32,a0
        mov 8,d1
        mov 0x4c465047,d0
.Lopen_prefix:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lopen_prefix
        mov 1126,d1
        clr d0
.Lopen_body:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lopen_body
        mov 8,d1
        mov 0x4c465047,d0
.Lopen_suffix:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lopen_suffix
        mov 1,d0
        mov d0,(68,a3)
        mov JOB_MAGIC,d0
        mov d0,(64,a3)
        clr d0
.Lopen_return:
        ret [d2,d3,a2,a3],20
.Lopen_view_bad:
        mov -18,d0
.Lopen_cleanup:
        mov d0,d2
        mov a3,a0
        call lut_gm1_packed_job_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_return
        mov d2,d0
        ret [d2,d3,a2,a3],20
.Lopen_busy:
        mov -2,d0
        ret [d2,d3,a2,a3],20

.org 395,0xff
lut_gm1_packed_job_close:
        mov a0,a3
        call .Lrecord,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclose_return
        call .Lworker,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclose_return
        mov (64,a3),d0
        cmp 0,d0
        beq .Lclose_children
        cmp JOB_MAGIC,d0
        bne .Lclose_bad
        mov psw,d3
        and 63487,psw
        mov (68,a3),d0
        cmp 1,d0
        beq .Lclose_claim
        cmp 4,d0
        bne .Lclose_busy_masked
.Lclose_claim:
        mov 4,d0
        mov d0,(68,a3)
        mov d3,psw
.Lclose_children:
        mov (a3),d0
        cmp 0,d0
        beq .Lclose_zero
        mov a3,a0
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclose_return
.Lclose_zero:
        mov a3,a0
        mov 24,d1
        clr d0
.Lclose_words:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lclose_words
.Lclose_return:
        ret [d2,d3,a2,a3],20
.Lclose_busy_masked:
        mov d3,psw
        mov -2,d0
        ret [d2,d3,a2,a3],20
.Lclose_bad:
        mov -1,d0
        ret [d2,d3,a2,a3],20

.org 499,0xff
lut_gm1_packed_job_capture:
        add -48,sp
        mov a0,a3
        mov a1,(4,sp)
        mov d0,(8,sp)
        mov d2,(16,sp)
        mov d3,(20,sp)
        cmp 10,d0
        bcc .Lcapture_bad
        cmp 0,d3
        beq .Lcapture_bad
        call .Lviews,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lcapture_bad
        mov d0,(24,sp)
        mov d1,(28,sp)
        mov (68,a3),d0
        cmp 1,d0
        bne .Lcapture_busy
        mov (16,sp),d0
        cmp 0,d0
        beq .Lcapture_bad
        mov (4,sp),a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lcapture_bad
        cmp 2284,d1
        bcs .Lcapture_bad
        mov d0,(32,sp)
        mov d0,a0
        call lut_gm1_record_check_table,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lcapture_bad
        /* The source lease must survive the table copy. */
        mov (4,sp),a0
        mov a3,a1
        mov 32,d0
        mov 96,d1
        call .Ldisjoint,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lcapture_bad
        mov (4,sp),a0
        mov (24,sp),a1
        mov 32,d0
        mov 2284,d1
        call .Ldisjoint,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lcapture_bad
        mov (32,sp),a0
        mov (24,sp),a1
        mov 2284,d0
        mov 2284,d1
        call .Ldisjoint,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lcapture_bad
        mov (32,sp),a0
        mov a3,a1
        mov 2284,d0
        mov 96,d1
        call .Ldisjoint,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lcapture_bad
.Lcapture_claim:
        mov psw,d3
        and 63487,psw
        mov (68,a3),d0
        cmp 1,d0
        bne .Lcapture_busy_masked
        mov 3,d0
        mov d0,(68,a3)
        mov d3,psw
        mov (24,sp),a0
        mov (32,sp),a1
        mov 2284,d0
        call native_memcpy,[a2,a3],8
        mov (24,sp),a2
        mov 8,d2
.Lrelocate:
        .irp offset,4,8
        mov (\offset,a2),d0
        mov (32,sp),d1
        sub d1,d0
        mov (24,sp),d1
        add d1,d0
        mov d0,(\offset,a2)
        .endr
        add 12,a2
        sub 1,d2
        bne .Lrelocate
.Lpublish_table:
        mov (16,sp),d0
        mov d0,(80,a3)
        mov d0,(88,a3)
        mov 0x4c640000,d0
        mov (8,sp),d1
        or d1,d0
        mov d0,(84,a3)
.Lpublish_common:
        mov (8,sp),d0
        mov d0,(72,a3)
        clr d0
        mov d0,(76,a3)
        mov (20,sp),d1
        mov d1,(92,a3)
        mov 2,d0
        mov d0,(68,a3)
        clr d0
        ret [d2,d3,a2,a3],68
.Lcapture_bad:
        mov -1,d0
        clr d1
        ret [d2,d3,a2,a3],68
.Lcapture_busy_masked:
        mov d3,psw
.Lcapture_busy:
        mov -2,d0
        clr d1
        ret [d2,d3,a2,a3],68

.org 960,0xff
lut_gm1_packed_job_apply:
        add -16,sp
        mov a0,a3
        mov a1,a2
        mov d0,(4,sp)
        call .Lviews,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lapply_bad
        mov a2,d0
        and 3,d0
        bne .Lapply_bad
        mov a2,d0
        cmp 0x70000000,d0
        bcs .Lapply_bad
        cmp 0x70ffe920,d0
        bhi .Lapply_bad
        movbu (2728,a2),d0
        cmp 0,d0
        beq .Lfixed_parent_mode
        cmp 5,d0
        beq .Lfixed_parent_mode
        cmp 7,d0
        beq .Lfixed_parent_mode
        cmp 15,d0
        bne .Lapply_bad
.Lfixed_parent_mode:
        mov (2696,a2),d0
        cmp 1,d0
        bhi .Lapply_bad
        mov (2724,a2),d1
        cmp d0,d1
        bne .Lapply_bad
        movhu (2700,a2),d0
        cmp 128,d0
        beq .Lfixed_parent_flags
        cmp 131,d0
        bne .Lapply_bad
.Lfixed_parent_flags:
        mov a3,a0
        mov a2,a1
        mov 96,d0
        mov 5856,d1
        call .Ldisjoint,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lapply_bad
        mov (72,a3),d2
        cmp 10,d2
        bcc .Lapply_bad
        mov 0x4c640000,d0
        or d2,d0
        mov (84,a3),d1
        cmp d1,d0
        bne .Lapply_bad
        mov (80,a3),d0
        cmp 0,d0
        beq .Lapply_bad
        mov (88,a3),d1
        cmp d1,d0
        bne .Lapply_bad
.Lapply_claim:
        mov psw,d3
        and 63487,psw
        mov (68,a3),d0
        cmp 2,d0
        bne .Lapply_stale_masked
        mov (4,sp),d0
        cmp 0,d0
        beq .Lapply_stale_masked
        mov (92,a3),d1
        cmp d1,d0
        bne .Lapply_stale_masked
        mov 5,d0
        mov d0,(68,a3)
        mov d3,psw
        mov a2,a0
        mov a3,a1
        mov (84,a3),d0
        mov (88,a3),d1
        call lut_gm1_record_apply,[d2,d3,a2,a3],20
.Lapply_done:
        mov 2,d1
        mov d1,(68,a3)
        ret [d2,d3,a2,a3],36
.Lapply_stale_masked:
        mov d3,psw
        mov -11,d0
        ret [d2,d3,a2,a3],36
.Lapply_bad:
        mov -1,d0
        ret [d2,d3,a2,a3],36

.org 1228,0xff
lut_gm1_packed_job_retire:
        mov a0,a3
        mov d0,d2
        call .Lviews,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lretire_bad
        mov psw,d3
        and 63487,psw
        mov (68,a3),d0
        cmp 2,d0
        bne .Lretire_stale_masked
        cmp 0,d2
        beq .Lretire_stale_masked
        mov (92,a3),d0
        cmp d2,d0
        bne .Lretire_stale_masked
        mov 6,d0
        mov d0,(68,a3)
        mov d3,psw
        clr d0
        .irp offset,72,76,80,84,88,92
        mov d0,(\offset,a3)
        .endr
        mov 1,d0
        mov d0,(68,a3)
        clr d0
        ret [d2,d3,a2,a3],20
.Lretire_stale_masked:
        mov d3,psw
        mov -11,d0
        ret [d2,d3,a2,a3],20
.Lretire_bad:
        mov -1,d0
        ret [d2,d3,a2,a3],20
.org 1309,0xff
lut_gm1_packed_job_end:


        .global lut_gm1_packed_child_view,lut_gm1_packed_frame_view
        .global lut_gm1_packed_table_view,lut_gm1_packed_module_end
.org 1309,0xff
lut_gm1_packed_child_view:
        mov a0,a3
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lpacked_child_bad
        cmp 4568,d1
        bcs .Lpacked_child_bad
        mov (24,a3),d2
        cmp 4568,d2
        bne .Lpacked_child_bad
        add 32,d0
        ret [d2,d3,a2,a3],20
.Lpacked_child_bad:
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20


/* Validate the same LFPG prefix/suffix used by GM5's frame pool. */
.org 1346,0xff
lut_gm1_packed_frame_view:
        call lut_gm1_packed_child_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lpacked_child_bad
        mov d0,a2
        mov d0,a0
        add -32,a0
        call .Lpacked_guard,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lpacked_child_bad
        mov a2,a0
        add 4504,a0
        call .Lpacked_guard,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lpacked_child_bad
        mov a2,d0
        mov 4504,d1
        ret [d2,d3,a2,a3],20
.Lpacked_guard:
        mov 8,d1
.Lpacked_guard_word:
        mov (a0),d0
        cmp 0x4c465047,d0
        bne .Lpacked_guard_bad
        inc4 a0
        sub 1,d1
        bne .Lpacked_guard_word
        clr d0
        ret [d2,d3,a2,a3],20
.Lpacked_guard_bad:
        mov -18,d0
        ret [d2,d3,a2,a3],20

/* Record upload still accepts ordinary2348B cell leases. A packed frame
 * supplies its table subrange from the same retained4568B owner as GM5. */
.org 1421,0xff
lut_gm1_packed_table_view:
        mov a0,a3
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lpacked_child_bad
        mov (24,a3),d2
        cmp 4568,d2
        bne .Lpacked_plain_table
        mov a3,a0
        call lut_gm1_packed_frame_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lpacked_child_bad
        add 32,d0
        mov 2284,d1
        ret [d2,d3,a2,a3],20
.Lpacked_plain_table:
        ret [d2,d3,a2,a3],20
.org 1463,0xff
lut_gm1_packed_module_end:
