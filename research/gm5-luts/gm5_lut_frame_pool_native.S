/* Preallocated13-frame LUT storage, created only by explicit Library work.
 * CALL F0/20. Open(A0=2496-byte manager CORE,A1=its2560-byte owner LIL1),
 * Close(A0=CORE),View(A0=CORE)->D0=body/0,D1=0 on failure.
 * CORE2456activeLease,2460publishedPool,2464external32-byte pool lease.
 * Pool request960 ->1024capacity,896-byte body at uncachedview+32:
 * 0LFP1,4phase1preparing/2ready/3closing/4cleanup,8core,12ownerLIL1,
 * 16heldCoreChild,20inflight,24generation,28error,32initializedChildren,
 * 36reserved,40activeSlot,44..63reserved;13slots64B at64.
 * Slot0..31owned4568-byte LIL1,32state,36token,40mode,44index,
 * 48jobView,52capturedStyle,56capturedPercent,60error.
 * Open/Close are serialized worker-context APIs; frame use will be separate.
 * Pin owner once, keep all13children exclusive. Failed cleanup retains owner
 * and unpublished leases for retry. No card/file/flash or boot call occurs.
 */
        .text
        .am33_2
        .global lut_frame_pool_open,lut_frame_pool_close,lut_frame_pool_view
        .global lut_frame_pool_claim,lut_frame_pool_finish
        .global lut_frame_pool_end
        .extern lut_ram_span,lut_session_view_shared,lut_image_view
        .extern lut_image_lease_open,lut_image_lease_close,lut_job_view
        .extern native_context

lut_frame_pool_open:
        add -24,sp
        mov a0,a3
        mov a1,(8,sp)
        call .Lworker,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_return
        call .Lcore,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_return
        mov (8,sp),a0
        call lut_session_view_shared,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lopen_owner
        add 32,d0
        mov a3,d1
        cmp d1,d0
        bne .Lopen_owner
        mov (2460,a3),d0
        cmp 0,d0
        beq .Lopen_fresh
        mov a3,a0
        call lut_frame_pool_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lopen_owner
        mov d0,a0
        mov (4,a0),d0
        cmp 2,d0
        bne .Lopen_pending
        clr d0
        ret [d2,d3,a2,a3],44
.Lopen_fresh:
        mov a3,a0
        add 2456,a0
        mov 10,d1
.Lfresh_words:
        mov (a0),d0
        cmp 0,d0
        bne .Lopen_pending
        inc4 a0
        sub 1,d1
        bne .Lfresh_words
        mov a3,a0
        add 2464,a0
        mov 960,d0
        call lut_image_lease_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_fail
        mov a3,a0
        add 2464,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lopen_owner_fail
        cmp 1024,d1
        bne .Lopen_owner_fail
        mov d0,a2
        mov a2,a0
        call .Lguard,[d2,d3,a2,a3],20
        add 32,a2
        mov a2,a0
        mov 224,d1
        call .Lzero,[d2,d3,a2,a3],20
        mov a2,a0
        add 896,a0
        call .Lguard,[d2,d3,a2,a3],20
        mov 0x3150464c,d0
        mov d0,(a2)
        mov 1,d0
        mov d0,(4,a2)
        mov a3,(8,a2)
        mov (8,sp),a0
        mov a0,(12,a2)
        mov (8,a0),a0
        mov a0,(12,sp)
        mov (a0),a1
        mov (a1),a1
        calls (a1)
        mov (12,sp),d0
        mov d0,(16,a2)
        clr d2
.Lopen_child:
        mov d2,d0
        asl 6,d0
        mov a2,a0
        add 64,a0
        add d0,a0
        mov a0,d3
        mov 4568,d0
        call lut_image_lease_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_children_fail
        mov d3,a0
        call lut_job_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lopen_child_owner
        mov d3,a0
        mov d0,(48,a0)
        mov d2,d1
        clr d0
        cmp 3,d2
        bcs .Lpreview_slot
        mov 1,d0
        sub 3,d1
.Lpreview_slot:
        mov d0,(40,a0)
        mov d1,(44,a0)
        mov (48,a0),a0
        add -32,a0
        call .Lguard,[d2,d3,a2,a3],20
        mov d3,a0
        mov (48,a0),a0
        mov 1126,d1
        call .Lzero,[d2,d3,a2,a3],20
        mov d3,a0
        mov (48,a0),a0
        add 4504,a0
        call .Lguard,[d2,d3,a2,a3],20
        inc d2
        mov d2,(32,a2)
        cmp 13,d2
        bcs .Lopen_child
        mov 2,d0
        mov d0,(4,a2)
        /* Publication is last. No producer has seen a partial allocation. */
        mov a2,(2460,a3)
        clr d0
        ret [d2,d3,a2,a3],44
.Lopen_child_owner:
        mov -18,d0
.Lopen_children_fail:
        mov d0,(28,a2)
        mov 4,d1
        mov d1,(4,a2)
.Lopen_fail:
        mov d0,(4,sp)
        mov a3,a0
        call lut_frame_pool_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lopen_pending
        mov (4,sp),d0
        bra .Lopen_return
.Lopen_owner_fail:
        /* Valid lease but unreadable allocation: retain it for diagnosis. */
        mov -15,d0
        bra .Lopen_return
.Lopen_owner:
        mov -18,d0
        bra .Lopen_return
.Lopen_pending:
        mov -15,d0
.Lopen_return:
        ret [d2,d3,a2,a3],44

/* View accepts preparing/cleanup for serialized owner cleanup, even when its
 * pointer is unpublished. Frame acquisition must additionally require ready. */
lut_frame_pool_view:
        mov a0,a3
        call .Lcore,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lview_bad
        mov a3,a0
        add 2464,a0
        mov (24,a0),d0
        cmp 960,d0
        bne .Lview_bad
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lview_bad
        cmp 1024,d1
        bne .Lview_bad
        add 32,d0
        mov d0,a2
        mov (a2),d0
        cmp 0x3150464c,d0
        bne .Lview_bad
        mov (8,a2),d0
        mov a3,d1
        cmp d1,d0
        bne .Lview_bad
        mov (12,a2),a0
        call lut_session_view_shared,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lview_bad
        add 32,d0
        mov a3,d1
        cmp d1,d0
        bne .Lview_bad
        mov (12,a2),a0
        mov (8,a0),d0
        mov (16,a2),d1
        cmp d1,d0
        bne .Lview_bad
        mov d0,a0
        mov (4,a0),d0
        cmp 2,d0
        blt .Lview_bad
        mov a2,d0
        mov 896,d1
        ret [d2,d3,a2,a3],20
.Lview_bad:
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20

lut_frame_pool_close:
        add -16,sp
        mov a0,a3
        call .Lworker,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclose_return
        call .Lcore,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclose_return
        mov (2464,a3),d0
        cmp 0,d0
        beq .Lclose_empty
        cmp 0x314c494c,d0
        bne .Lclose_invalid
        mov (2468,a3),d0
        cmp 3,d0
        beq .Lclose_failed_lease
        mov a3,a0
        call lut_frame_pool_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lclose_invalid
        mov d0,a2
        mov psw,d3
        and 63487,psw
        mov (4,a2),d0
        cmp 2,d0
        beq .Lclose_check
        cmp 4,d0
        bne .Lclose_masked_busy
.Lclose_check:
        mov (20,a2),d0
        cmp 0,d0
        bne .Lclose_masked_busy
        mov (40,a2),d0
        cmp 0,d0
        bne .Lclose_masked_busy
        mov (2456,a3),d0
        cmp 0,d0
        bne .Lclose_masked_busy
        mov a2,a0
        add 96,a0
        mov 13,d1
.Lclose_slots_idle:
        mov (a0),d0
        cmp 0,d0
        bne .Lclose_masked_busy
        add 64,a0
        sub 1,d1
        bne .Lclose_slots_idle
        mov 3,d0
        mov d0,(4,a2)
        clr d0
        mov d0,(2460,a3)
        mov d3,psw
        clr d2
.Lclose_child:
        mov d2,d0
        asl 6,d0
        mov a2,a0
        add 64,a0
        add d0,a0
        mov (a0),d0
        cmp 0,d0
        beq .Lclose_next
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclose_cleanup
.Lclose_next:
        inc d2
        cmp 13,d2
        bcs .Lclose_child
        mov (16,a2),d0
        mov d0,(8,sp)
        mov a3,a0
        add 2464,a0
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclose_cleanup
        /* Pool allocation is gone: never dereference A2 again. CORE is pinned. */
        mov a3,a0
        add 2456,a0
        mov 10,d1
        call .Lzero,[d2,d3,a2,a3],20
        mov (8,sp),a0
        mov (a0),a1
        mov (4,a1),a1
        calls (a1)
        clr d0
        ret [d2,d3,a2,a3],36
.Lclose_cleanup:
        mov d0,(28,a2)
        mov 4,d1
        mov d1,(4,a2)
        mov -15,d0
        bra .Lclose_return
.Lclose_masked_busy:
        mov d3,psw
        mov -2,d0
        bra .Lclose_return
.Lclose_failed_lease:
        mov (2472,a3),d0
        cmp 0,d0
        bne .Lclose_invalid
        mov a3,a0
        add 2464,a0
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclose_return
        mov a3,a0
        add 2456,a0
        mov 10,d1
        call .Lzero,[d2,d3,a2,a3],20
        clr d0
        bra .Lclose_return
.Lclose_empty:
        mov a3,a0
        add 2456,a0
        mov 10,d1
.Lempty_words:
        mov (a0),d0
        cmp 0,d0
        bne .Lclose_invalid
        inc4 a0
        sub 1,d1
        bne .Lempty_words
        clr d0
        bra .Lclose_return
.Lclose_invalid:
        mov -18,d0
.Lclose_return:
        ret [d2,d3,a2,a3],36

.Lworker:
        mov (0x8050),d0
        cmp 0,d0
        bne .Largs
        call native_context,[],0
        extbu d0
        cmp 0,d0
        bne .Largs
        clr d0
        ret [d2,d3,a2,a3],20
.Lcore:
        mov a3,d0
        and 3,d0
        bne .Largs
        mov a3,d0
        mov 2496,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov (a3),d0
        cmp 0x324c434c,d0
        bne .Largs
        clr d0
        ret [d2,d3,a2,a3],20
.Largs:
        mov -1,d0
        ret [d2,d3,a2,a3],20
.Lzero:
        clr d0
.Lzero_words:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lzero_words
        ret [d2,d3,a2,a3],20
.Lguard:
        mov 0x4c465047,d0
        mov 8,d1
.Lguard_words:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lguard_words
        ret [d2,d3,a2,a3],20

/* CPU0 nonblocking reserve BEFORE any original producer writes its ring.
 * A0CORE,D0mode0/1,D1index ->D0status,D1slot pointer. Caller already owns
 * its CORE. Close cannot free the pool after inflight is incremented.
 * Captured style/percentage come from one bounded, call-free masked section.
 */
lut_frame_pool_claim:
        add -16,sp
        mov a0,a3
        cmp 1,d0
        bhi .Lclaim_args
        cmp 0,d0
        bne .Lclaim_capture
        cmp 3,d1
        bcc .Lclaim_args
        bra .Lclaim_index
.Lclaim_capture:
        cmp 10,d1
        bcc .Lclaim_args
        add 3,d1
.Lclaim_index:
        mov d1,d2
        mov (0x8050),d0
        cmp 0,d0
        bne .Lclaim_args
        mov a3,a0
        call lut_frame_pool_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lclaim_invalid
        mov d0,a2
        mov psw,d3
        and 63487,psw
        mov (2460,a3),d0
        mov a2,d1
        cmp d1,d0
        bne .Lclaim_busy
        mov (4,a2),d0
        cmp 2,d0
        bne .Lclaim_busy
        mov (20,a2),d0
        cmp 13,d0
        bcc .Lclaim_busy
        mov (24,a2),d0
        cmp -1,d0
        beq .Lclaim_generation
        mov d2,d0
        asl 6,d0
        mov a2,a0
        add 64,a0
        add d0,a0
        mov a0,(12,sp)
        mov (32,a0),d0
        cmp 0,d0
        bne .Lclaim_busy
        mov (24,a2),d0
        inc d0
        mov d0,(24,a2)
        mov d0,(36,a0)
        mov 1,d0
        mov d0,(32,a0)
        mov (20,a2),d0
        inc d0
        mov d0,(20,a2)
        movbu (0x701ad636),d0
        mov d0,(52,a0)
        mov 100,d1
        mov d1,(56,a0)
        clr d1
        mov d1,(60,a0)
        cmp 7,d0
        bcs .Lclaim_success
        cmp 16,d0
        bhi .Lclaim_success
        movhu (0x7bfb2646),d0
        cmp 0x4c53,d0
        bne .Lclaim_success
        mov 0x7bfb263c,a0
        mov 10,d1
.Lclaim_percent_valid:
        movbu (a0),d0
        cmp 100,d0
        bhi .Lclaim_success
        inc a0
        sub 1,d1
        bne .Lclaim_percent_valid
        mov (12,sp),a0
        mov (52,a0),d0
        sub 7,d0
        add 0x7bfb263c,d0
        mov d0,a0
        movbu (a0),d0
        mov (12,sp),a0
        mov d0,(56,a0)
.Lclaim_success:
        mov (12,sp),d1
        mov d3,psw
        clr d0
        ret [d2,d3,a2,a3],36
.Lclaim_generation:
        mov d3,psw
        mov -17,d0
        bra .Lclaim_error
.Lclaim_busy:
        mov d3,psw
        mov -2,d0
        bra .Lclaim_error
.Lclaim_args:
        mov -1,d0
        bra .Lclaim_error
.Lclaim_invalid:
        mov -18,d0
.Lclaim_error:
        clr d1
        ret [d2,d3,a2,a3],36

/* A0CORE,A1owned slot,D0captured token. Never frees memory or waits.
 * Used after producer failure or final processing use, not receive cleanup.
 */
lut_frame_pool_finish:
        add -16,sp
        mov a0,a3
        mov a1,(4,sp)
        mov d0,d2
        mov (0x8050),d0
        cmp 0,d0
        bne .Lfinish_args
        mov a3,a0
        call lut_frame_pool_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lfinish_invalid
        mov d0,a2
        mov (4,sp),d0
        sub a2,d0
        sub 64,d0
        bcs .Lfinish_args
        cmp 832,d0
        bcc .Lfinish_args
        and 63,d0
        bne .Lfinish_args
        mov psw,d3
        and 63487,psw
        mov (2460,a3),d0
        mov a2,d1
        cmp d1,d0
        bne .Lfinish_masked_invalid
        mov (4,sp),a0
        cmp 0,d2
        beq .Lfinish_stale
        mov (36,a0),d0
        cmp d2,d0
        bne .Lfinish_stale
        mov (32,a0),d0
        cmp 1,d0
        bcs .Lfinish_stale
        cmp 3,d0
        bhi .Lfinish_stale
        mov (20,a2),d0
        cmp 1,d0
        bcs .Lfinish_masked_invalid
        cmp 13,d0
        bhi .Lfinish_masked_invalid
        mov (40,a2),d0
        mov a0,d1
        cmp d1,d0
        bne .Lfinish_release
        clr d0
        mov d0,(40,a2)
        mov d0,(2456,a3)
.Lfinish_release:
        mov (20,a2),d0
        sub 1,d0
        mov d0,(20,a2)
        clr d0
        mov d0,(32,a0)
        mov d3,psw
        ret [d2,d3,a2,a3],36
.Lfinish_stale:
        mov d3,psw
        mov -11,d0
        ret [d2,d3,a2,a3],36
.Lfinish_masked_invalid:
        mov d3,psw
.Lfinish_invalid:
        mov -18,d0
        ret [d2,d3,a2,a3],36
.Lfinish_args:
        mov -1,d0
        ret [d2,d3,a2,a3],36
lut_frame_pool_end:
