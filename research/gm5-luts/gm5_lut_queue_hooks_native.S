/* CPU0 actual camera queue bindings. No allocation/file access on this path.
 * F0/20 APIs bank_lock/unlock(A0CORE,D0mode),enter(A0CORE,A1envelope),
 * close_guard(A0CORE). Producer entries preserve original B0/16 convention.
 * Dispatcher/constructor entry patches are JMPs: wrappers own their saves,
 * invoke the original CALL frames and jump to exact original continuations.
 * Pool36closing gate,44two producer bank bits; old pool code stays unchanged.
 */
        .text
        .am33_2
        .global lut_queue_bank_lock,lut_queue_bank_unlock,lut_queue_close_guard
        .global lut_queue_enter,lut_queue_preview,lut_queue_capture
        .global lut_queue_dispatch,lut_queue_preview_constructor,lut_queue_capture_constructor
        .global lut_queue_replay_preview,lut_queue_replay_capture,lut_queue_hooks_end
        .extern lut_frame_pool_view,lut_frame_pool_claim,lut_frame_pool_finish
        .extern lut_job_capture,lut_job_bind,lut_ram_span,original_pool_close
        .extern native_dispatch,native_dispatch_return,native_constructor
        .extern native_preview_continue,native_capture_continue
        .extern native_preview_constructor_return,native_capture_constructor_return
        .equ CORE_ANCHOR,0x70a0e9c0

lut_queue_bank_lock:
        mov a0,a3
        mov d0,d2
        cmp 1,d2
        bhi .Lbank_args
        mov (0x8050),d0
        cmp 0,d0
        bne .Lbank_args
        mov psw,d3
        and 63487,psw
        /* Pure validation stays masked: Close must not free the lease
         * between its validation and the first protected bank bit. */
        call lut_frame_pool_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbank_missing
        mov d0,a2
        mov (2460,a3),d0
        mov a2,d1
        cmp d1,d0
        bne .Lbank_busy
        mov (4,a2),d0
        cmp 2,d0
        bne .Lbank_busy
        mov (36,a2),d0
        cmp 0,d0
        bne .Lbank_busy
        mov (44,a2),d0
        cmp 3,d0
        bhi .Lbank_invalid
        mov 1,d1
        asl d2,d1
        mov d0,d2
        and d1,d2
        bne .Lbank_busy
        or d1,d0
        mov d0,(44,a2)
        mov a2,d1
        mov d3,psw
        clr d0
        ret [d2,d3,a2,a3],20
lut_queue_bank_unlock:
        mov a0,a3
        mov d0,d2
        cmp 1,d2
        bhi .Lbank_args
        mov (0x8050),d0
        cmp 0,d0
        bne .Lbank_args
        mov psw,d3
        and 63487,psw
        call lut_frame_pool_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbank_missing
        mov d0,a2
        mov (2460,a3),d0
        mov a2,d1
        cmp d1,d0
        bne .Lbank_invalid
        mov (44,a2),d0
        cmp 3,d0
        bhi .Lbank_invalid
        mov 1,d1
        asl d2,d1
        mov d0,d2
        and d1,d2
        beq .Lbank_invalid
        not d1
        and d1,d0
        mov d0,(44,a2)
        mov d3,psw
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20
.Lbank_busy:
        mov d3,psw
        mov -2,d0
        clr d1
        ret [d2,d3,a2,a3],20
.Lbank_invalid:
        mov d3,psw
        mov -18,d0
        clr d1
        ret [d2,d3,a2,a3],20
.Lbank_missing:
        mov d3,psw
        mov -3,d0
        clr d1
        ret [d2,d3,a2,a3],20
.Lbank_args:
        mov -1,d0
        clr d1
        ret [d2,d3,a2,a3],20

/* Serialize old Close against a producer that may outlive its consumed slot.
 * Existing Open-failure cleanup has no published pool/producers and keeps its
 * old internal Close. All published manager Close calls use this guard.
 */
lut_queue_close_guard:
        mov a0,a3
        mov psw,d3
        and 63487,psw
        call lut_frame_pool_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lclose_delegate
        mov d0,a2
        mov (44,a2),d0
        cmp 0,d0
        bne .Lclose_busy
        mov (36,a2),d0
        cmp 0,d0
        bne .Lclose_busy
        mov 1,d0
        mov d0,(36,a2)
        mov d3,psw
        mov a3,a0
        call original_pool_close,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lclose_return
        /* Any old Close error retains the owned pool; clear our gate for retry.
         * On success it was freed, so do not access A2 again. */
        mov d0,d2
        mov psw,d3
        and 63487,psw
        clr d0
        mov d0,(36,a2)
        mov d3,psw
        mov d2,d0
.Lclose_return:
        ret [d2,d3,a2,a3],20
.Lclose_delegate:
        mov d3,psw
        mov a3,a0
        call original_pool_close,[d2,d3,a2,a3],20
        ret [d2,d3,a2,a3],20
.Lclose_busy:
        mov d3,psw
        mov -2,d0
        ret [d2,d3,a2,a3],20

lut_queue_preview:
        add -32,sp
        mov d0,(4,sp)
        mov a0,(8,sp)
        mov a1,(12,sp)
        clr d2
        bra .Lproduce
lut_queue_capture:
        add -32,sp
        mov d0,(4,sp)
        mov a0,(8,sp)
        mov a1,(12,sp)
        mov 1,d2
.Lproduce:
        mov (CORE_ANCHOR),d0
        mov d0,d1
        and 3,d1
        bne .Lno_pool
        cmp 0xb3400000,d0
        bcs .Lno_pool
        cmp 0xb85ff640,d0
        bhi .Lno_pool
        mov d0,a2
        mov (a2),d0
        cmp 0x324c434c,d0
        bne .Lno_pool
        mov (2460,a2),d0
        cmp 0,d0
        beq .Lno_pool
        mov a2,a0
        mov d2,d0
        call lut_queue_bank_lock,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lproduce_error
        movhu (0x70340160),d1
        cmp 0,d2
        beq .Lclaim_producer
        movhu (0x7034027c),d1
.Lclaim_producer:
        mov a2,a0
        mov d2,d0
        call lut_frame_pool_claim,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lunlock_error
        mov d1,a3
        mov (36,a3),d0
        mov d0,(16,sp)
        mov (52,a3),d0
        cmp 7,d0
        bcs .Lpublish_request
        cmp 16,d0
        bhi .Lpublish_request
        mov (48,a3),a0
        mov 1126,d1
        clr d0
.Lfresh_job:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lfresh_job
        mov a2,a0
        mov a3,a1
        mov (52,a3),d0
        sub 7,d0
        mov (56,a3),d1
        call lut_job_capture,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lretire_error
.Lpublish_request:
        mov 2,d0
        mov d0,(32,a3)
        mov (4,sp),d0
        mov (8,sp),a0
        mov (12,sp),a1
        cmp 0,d2
        bne .Loriginal_capture
        call lut_queue_replay_preview,[d2,a2,a3],16
        bra .Lposted
.Loriginal_capture:
        call lut_queue_replay_capture,[d2,a2,a3],16
.Lposted:
        mov d0,(20,sp)
        cmp 0,d0
        beq .Lunlock_posted
        mov a2,a0
        mov a3,a1
        mov (16,sp),d0
        call lut_frame_pool_finish,[d2,d3,a2,a3],20
.Lunlock_posted:
        /* No successful-post access to the request slot. The independent
         * bank bit keeps the pool alive even if task28 already finished it. */
        mov a2,a0
        mov d2,d0
        call lut_queue_bank_unlock,[d2,d3,a2,a3],20
        mov (20,sp),d0
        ret [d2,a2,a3],48
.Lretire_error:
        mov d0,(60,a3)
        mov a2,a0
        mov a3,a1
        mov (16,sp),d0
        call lut_frame_pool_finish,[d2,d3,a2,a3],20
.Lunlock_error:
        mov a2,a0
        mov d2,d0
        call lut_queue_bank_unlock,[d2,d3,a2,a3],20
.Lproduce_error:
        mov 1,d0
        ret [d2,a2,a3],48
.Lno_pool:
        /* Original callers may already have marked their job busy and do not
         * repair a refused submission. Without an owned runtime pool, keep
         * the stock queue/handler/completion route alive. Slot metadata IDs
         * already map to neutral Standard; no stale table is bound. */
.Lstock_producer:
        mov (4,sp),d0
        mov (8,sp),a0
        mov (12,sp),a1
        cmp 0,d2
        bne .Lstock_capture
        call lut_queue_replay_preview,[d2,a2,a3],16
        ret [d2,a2,a3],48
.Lstock_capture:
        call lut_queue_replay_capture,[d2,a2,a3],16
        ret [d2,a2,a3],48

/* Displaced seven-byte original producer prefixes, under original B0/16.
 * Both original entries receive five-byte JMPs; skip the entire old prefix. */
lut_queue_replay_preview:
        mov d0,d2
        movhu (0x70340160),d0
        jmp native_preview_continue
lut_queue_replay_capture:
        mov d0,d2
        movhu (0x7034027c),d0
        jmp native_capture_continue

/* Actual task28 only. A0CORE,A1original16-byte envelope ->D0status,D1slot.
 * The tuple identity is still available before the original stack copy. */
lut_queue_enter:
        add -16,sp
        mov a0,a3
        mov a1,(4,sp)
        mov (0x70a01d48),d0
        cmp 0x709f8b6c,d0
        bne .Lenter_args
        mov a1,d0
        and 3,d0
        bne .Lenter_args
        mov a1,d0
        mov 16,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lenter_args
        mov (4,sp),a0
        mov (4,a0),d2
        cmp 1,d2
        bhi .Lenter_untracked
        mov (8,a0),d0
        cmp 0,d2
        bne .Lenter_capture
        sub 0x7034013c,d0
        bcs .Lenter_args
        cmp 36,d0
        bcc .Lenter_args
        bra .Lenter_index
.Lenter_capture:
        sub 0x70340204,d0
        bcs .Lenter_args
        cmp 120,d0
        bcc .Lenter_args
.Lenter_index:
        mov 12,d1
        mov d2,(8,sp)
        clr d2
        mov d2,mdr
        divu d1,d0
        mov mdr,d1
        mov (8,sp),d2
        cmp 0,d1
        bne .Lenter_args
        cmp 0,d2
        beq .Lenter_global
        add 3,d0
.Lenter_global:
        mov d0,d2
        mov a3,a0
        mov psw,d3
        and 63487,psw
        call lut_frame_pool_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lenter_pool_missing
        mov d0,a2
        mov (2460,a3),d0
        mov a2,d1
        cmp d1,d0
        bne .Lenter_busy
        mov (4,a2),d0
        cmp 2,d0
        bne .Lenter_busy
        mov (40,a2),d0
        cmp 0,d0
        bne .Lenter_busy
        mov (2456,a3),d0
        cmp 0,d0
        bne .Lenter_busy
        mov d2,d0
        asl 6,d0
        mov a2,a0
        add 64,a0
        add d0,a0
        mov (32,a0),d0
        cmp 2,d0
        bne .Lenter_busy
        mov 3,d0
        mov d0,(32,a0)
        mov a0,(40,a2)
        mov a0,d1
        mov (52,a0),d0
        cmp 7,d0
        bcs .Lenter_success
        cmp 16,d0
        bhi .Lenter_success
        mov a0,(2456,a3)
.Lenter_success:
        mov d3,psw
        clr d0
        ret [d2,d3,a2,a3],36
.Lenter_busy:
        mov d3,psw
        mov -2,d0
        bra .Lenter_error
.Lenter_args:
        mov -1,d0
        bra .Lenter_error
.Lenter_pool_missing:
        mov d3,psw
.Lenter_untracked:
        mov -3,d0
.Lenter_error:
        clr d1
        ret [d2,d3,a2,a3],36

/* JMP at old five-byte CALL. Allocate our own36bytes and the ORIGINAL60-byte
 * dispatcher CALL frame; after return restore exactly and resume its BRA. */
lut_queue_dispatch:
        movm [d2,d3,a2,a3],(sp)
        add -20,sp
        mov a0,(4,sp)
        clr d0
        mov d0,(8,sp)
        mov (CORE_ANCHOR),a0
        mov a0,(16,sp)
        mov (4,sp),a1
        call lut_queue_enter,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Ldispatch_original
        mov d1,(8,sp)
        mov d1,a0
        mov (36,a0),d0
        mov d0,(12,sp)
.Ldispatch_original:
        mov (4,sp),a0
        call native_dispatch,[],60
        mov (8,sp),d0
        cmp 0,d0
        beq .Ldispatch_restore
        mov d0,a1
        mov (16,sp),a0
        mov (12,sp),d0
        call lut_frame_pool_finish,[d2,d3,a2,a3],20
        /* Finish can drop the last inflight claim. No pool/core access follows. */
.Ldispatch_restore:
        add 20,sp
        movm (sp),[d2,d3,a2,a3]
        jmp native_dispatch_return

        .macro constructor_hook name,continuation
\name:
        movm [d2,d3,a2,a3],(sp)
        .ifdef LUT_FULL_COLOR_MODE
        add -28,sp
        clr d2
        mov d2,(20,sp)
        .else
        add -20,sp
        .endif
        mov d0,(4,sp)
        mov a0,(8,sp)
        mov d1,(12,sp)
        mov a1,(16,sp)
        mov (0x70a01d48),d0
        cmp 0x709f8b6c,d0
        bne .Lctor_original_\@
        mov (CORE_ANCHOR),d0
        mov d0,d1
        and 3,d1
        bne .Lctor_original_\@
        cmp 0xb3400000,d0
        bcs .Lctor_original_\@
        cmp 0xb85ff640,d0
        bhi .Lctor_original_\@
        mov d0,a2
        mov (a2),d0
        cmp 0x324c434c,d0
        bne .Lctor_original_\@
        mov (2456,a2),a3
        cmp 0,a3
        beq .Lctor_original_\@
        mov a3,a0
        mov (8,sp),a1
        call lut_job_bind,[d2,d3,a2,a3],20
        mov d0,(60,a3)
        .ifdef LUT_FULL_COLOR_MODE
        cmp 0,d0
        bne .Lctor_original_\@
        mov a3,a0
        call lut_job_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lctor_original_\@
        mov d0,a0
        mov (4,a0),d0
        cmp 1,d0
        bne .Lctor_original_\@
        mov 1,d0
        mov d0,(20,sp)
        .endif
.Lctor_original_\@:
        .ifdef LUT_FULL_COLOR_MODE
        mov (8,sp),d0
        mov d0,(24,sp)
        .endif
        mov (4,sp),d0
        mov (8,sp),a0
        mov (12,sp),d1
        mov (16,sp),a1
        call native_constructor,[d2,d3,a2,a3],164
        .ifdef LUT_FULL_COLOR_MODE
        /* Only a successfully bound, owned LUT snapshot can request this.
         * Keep every original constructor result register, and leave stock,
         * bypass and rejected bindings unchanged. Mode15 is the existing
         * full-color ROM-table mode; its physical interpolation is unproved. */
        mov d0,(4,sp)
        mov a0,(8,sp)
        mov d1,(12,sp)
        mov a1,(16,sp)
        mov (20,sp),d0
        cmp 1,d0
        bne .Lctor_color_done_\@
        mov (24,sp),a0
        mov (a0),a0
        mov (2388,a0),d0
        cmp 7,d0
        bne .Lctor_color_done_\@
        movbu (2384,a0),d0
        cmp 5,d0
        bne .Lctor_color_done_\@
        mov LUT_FULL_COLOR_MODE,d0
        movbu d0,(2384,a0)
.Lctor_color_done_\@:
        mov (4,sp),d0
        mov (8,sp),a0
        mov (12,sp),d1
        mov (16,sp),a1
        add 28,sp
        .else
        add 20,sp
        .endif
        movm (sp),[d2,d3,a2,a3]
        jmp \continuation
        .endm
        constructor_hook lut_queue_preview_constructor,native_preview_constructor_return
        constructor_hook lut_queue_capture_constructor,native_capture_constructor_return
lut_queue_hooks_end:
