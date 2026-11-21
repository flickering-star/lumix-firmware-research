/* GM1 explicit owned processing snapshots. All public entries CALL F0/20.
 * Caller owns96B metadata: table LIL1[0..31], scratch LIL1[32..63],
 * +64GMJ1,+68phase1ready/2captured/3capture/4close/5apply/6retire,
 * +72cell,+76tick0..10,+80generation,+84key0,+88key1,+92request token.
 * open(A0fresh96B), close(A0job): serialized worker-only allocation APIs.
 * capture(A0job,A1live source lease,D0cell,D1tick,D2generation,D3token).
 * apply(A0job,A1complete original Standard parent,D0token).
 * retire(A0job,D0token): caller invokes only after the final consumer.
 * Capture/Apply/Retire allocate nothing. No UI/registry/queue/boot hook.
 * Native retained children use2348B table/4568B scratch requests; these
 * select the existing adjacent pool. Source may close after Capture.
 * CPU0 masked phase changes are short; no call/loop/copy runs masked.
 */
        .text
        .am33_2
        .global lut_gm1_job_open,lut_gm1_job_close,lut_gm1_job_capture
        .global lut_gm1_job_apply,lut_gm1_job_retire,lut_gm1_job_end
        .extern lut_ram_span,lut_image_lease_open,lut_image_lease_close,lut_image_view
        .extern lut_gm1_record_check_table,lut_gm1_record_apply
        .extern lut_strength_generate,native_memcpy,native_context
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
        mov (24,a3),d0
        cmp 2348,d0
        bne .Lview_bad
        mov (56,a3),d0
        cmp 4568,d0
        bne .Lview_bad
        mov a3,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lview_bad
        mov d0,(4,sp)
        mov a3,a0
        add 32,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lview_bad
        mov d0,(8,sp)
        mov a3,a0
        mov (4,sp),a1
        mov 96,d0
        mov 2284,d1
        call .Ldisjoint,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lview_bad
        mov a3,a0
        mov (8,sp),a1
        mov 96,d0
        mov 2188,d1
        call .Ldisjoint,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lview_bad
        mov (4,sp),a0
        mov (8,sp),a1
        mov 2284,d0
        mov 2188,d1
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

lut_gm1_job_open:
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
        mov 2348,d0
        call lut_image_lease_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_cleanup
        mov a3,a0
        add 32,a0
        mov 4568,d0
        call lut_image_lease_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_cleanup
        mov 1,d0
        mov d0,(68,a3)
        mov JOB_MAGIC,d0
        mov d0,(64,a3)
        clr d0
.Lopen_return:
        ret [d2,d3,a2,a3],20
.Lopen_cleanup:
        mov d0,d2
        mov a3,a0
        call lut_gm1_job_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_return
        mov d2,d0
        ret [d2,d3,a2,a3],20
.Lopen_busy:
        mov -2,d0
        ret [d2,d3,a2,a3],20

lut_gm1_job_close:
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
        beq .Lclose_scratch
        mov a3,a0
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclose_return
.Lclose_scratch:
        mov (32,a3),d0
        cmp 0,d0
        beq .Lclose_zero
        mov a3,a0
        add 32,a0
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

lut_gm1_job_capture:
        add -48,sp
        mov a0,a3
        mov a1,(4,sp)
        mov d0,(8,sp)
        mov d1,(12,sp)
        mov d2,(16,sp)
        mov d3,(20,sp)
        cmp 10,d0
        bcc .Lcapture_bad
        cmp 10,d1
        bhi .Lcapture_bad
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
        mov (12,sp),d0
        cmp 0,d0
        beq .Lcapture_claim
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
        /* The source lease itself must survive scratch/table writes too. */
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
        mov (4,sp),a0
        mov (28,sp),a1
        mov 32,d0
        mov 2188,d1
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
        mov (28,sp),a1
        mov 2284,d0
        mov 2188,d1
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
        mov (12,sp),d0
        cmp 0,d0
        beq .Lpublish_bypass
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
        mov (12,sp),d0
        cmp 10,d0
        beq .Lpublish_table
        mov 10,d1
        mul d1,d0
        mov (28,sp),a0
        mov (24,sp),a1
        add 96,a1
        call lut_strength_generate,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lcapture_abort
        mov (24,sp),a0
        add 96,a0
        mov (28,sp),a1
        mov 2188,d0
        call native_memcpy,[a2,a3],8
.Lpublish_table:
        mov (16,sp),d0
        mov d0,(80,a3)
        mov d0,(88,a3)
        mov (12,sp),d0
        mov 10,d1
        mul d1,d0
        asl 16,d0
        or 0x4c000000,d0
        mov (8,sp),d1
        or d1,d0
        mov d0,(84,a3)
        bra .Lpublish_common
.Lpublish_bypass:
        clr d0
        mov d0,(80,a3)
        mov d0,(84,a3)
        mov d0,(88,a3)
.Lpublish_common:
        mov (8,sp),d0
        mov d0,(72,a3)
        mov (12,sp),d0
        mov d0,(76,a3)
        mov (20,sp),d1
        mov d1,(92,a3)
        mov 2,d0
        mov d0,(68,a3)
        clr d0
        ret [d2,d3,a2,a3],68
.Lcapture_abort:
        mov 1,d0
        mov d0,(68,a3)
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

lut_gm1_job_apply:
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
        bne .Lapply_bad
        mov (2696,a2),d0
        cmp 1,d0
        bhi .Lapply_bad
        mov (2724,a2),d1
        cmp d0,d1
        bne .Lapply_bad
        movhu (2700,a2),d0
        cmp 128,d0
        bne .Lapply_bad
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
        mov (76,a3),d0
        cmp 10,d0
        bhi .Lapply_bad
        cmp 0,d0
        beq .Lapply_zero_key
        mov 10,d1
        mul d1,d0
        asl 16,d0
        or 0x4c000000,d0
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
        bra .Lapply_claim
.Lapply_zero_key:
        mov (80,a3),d0
        mov (84,a3),d1
        or d1,d0
        mov (88,a3),d1
        or d1,d0
        cmp 0,d0
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
        mov (76,a3),d0
        cmp 0,d0
        beq .Lapply_done
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

lut_gm1_job_retire:
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
lut_gm1_job_end:
