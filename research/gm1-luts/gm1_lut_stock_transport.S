/* GM1 original preview/capture entry hooks. Original CALL B0/16 preserved.
 * Producer bank bits hold the controller/session through native post return,
 * even if the consumer already finishes its snapshot. Missing/closed runtime
 * delegates to stock completion. Busy/failed snapshots refuse before ring
 * writes. No allocation, filesystem, dispatcher or constructor code here.
 * Public bank APIs CALL F0/20, A0CTRL,D0mode0/1 ->D0status,D1CTRL/0.
 */
        .text
        .am33_2
        .global lut_gm1_producer_bank_lock,lut_gm1_producer_bank_unlock
        .global lut_gm1_producer_preview,lut_gm1_producer_capture
        .global lut_gm1_producer_replay_preview,lut_gm1_producer_replay_capture
        .global lut_gm1_producer_hooks_end
        .extern lut_gm1_control_get,lut_gm1_request_begin,lut_gm1_request_finish
        .extern native_preview_continue,native_capture_continue

lut_gm1_producer_bank_lock:
        mov a0,a3
        mov d0,d2
        cmp 1,d2
        bhi .Lbank_invalid
        call lut_gm1_control_get,[d2,d3,a2,a3],20
        cmp a3,d0
        bne .Lbank_missing
        cmp 0,d0
        beq .Lbank_missing
        mov psw,d3
        and 63487,psw
        mov (12,a3),d0
        cmp 0,d0
        beq .Lbank_missing_masked
        cmp 2,d0
        bne .Lbank_busy
        mov (28,a3),d0
        cmp 3,d0
        bhi .Lbank_invalid_masked
        mov 1,d1
        asl d2,d1
        mov d0,d2
        and d1,d2
        bne .Lbank_busy
        or d1,d0
        mov d0,(28,a3)
        mov d3,psw
        mov a3,d1
        clr d0
        ret [d2,d3,a2,a3],20
lut_gm1_producer_bank_unlock:
        mov a0,a3
        mov d0,d2
        cmp 1,d2
        bhi .Lbank_invalid
        call lut_gm1_control_get,[d2,d3,a2,a3],20
        cmp a3,d0
        bne .Lbank_invalid
        cmp 0,d0
        beq .Lbank_invalid
        mov psw,d3
        and 63487,psw
        mov (28,a3),d0
        cmp 3,d0
        bhi .Lbank_invalid_masked
        mov 1,d1
        asl d2,d1
        mov d0,d2
        and d1,d2
        beq .Lbank_invalid_masked
        not d1
        and d1,d0
        mov d0,(28,a3)
        mov d3,psw
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20
.Lbank_missing_masked:
        mov d3,psw
.Lbank_missing:
        mov -3,d0
        clr d1
        ret [d2,d3,a2,a3],20
.Lbank_busy:
        mov d3,psw
        mov -2,d0
        clr d1
        ret [d2,d3,a2,a3],20
.Lbank_invalid_masked:
        mov d3,psw
.Lbank_invalid:
        mov -18,d0
        clr d1
        ret [d2,d3,a2,a3],20

/* Save original volatile/loop state plus unsaved D3 above32B locals.
 * Locals4entry/outputPSW,8mode,12CTRL,16slot,20token,24..31reserved. */
lut_gm1_producer_preview:
        movm [d3,other],(sp)
        mov psw,d3
        add -32,sp
        mov d3,(4,sp)
        clr d0
        mov d0,(8,sp)
        bra .Lproduce
lut_gm1_producer_capture:
        movm [d3,other],(sp)
        mov psw,d3
        add -32,sp
        mov d3,(4,sp)
        mov 1,d0
        mov d0,(8,sp)
.Lproduce:
        clr d0
        mov d0,(12,sp)
        /* Stock styles do not own LUT snapshots. Never let initialization,
         * a source gate or LUT slot refusal suppress their native completion.
         * The native preview caller waits even if our old hook returns1. */
        movbu (0x70101252),d0
        cmp 7,d0
        bcs .Lstock
        cmp 16,d0
        bhi .Lstock
        call lut_gm1_control_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lstock
        mov d0,a0
        mov (8,sp),d0
        call lut_gm1_producer_bank_lock,[d2,d3,a2,a3],20
        cmp -3,d0
        beq .Lstock
        cmp 0,d0
        bne .Lrefuse
        mov d1,(12,sp)
        mov d1,a0
        mov (8,sp),d0
        cmp 0,d0
        bne .Lcapture_index
        movhu (0x7027b3e4),d1
        bra .Lbegin
.Lcapture_index:
        movhu (0x7027b500),d1
.Lbegin:
        call lut_gm1_request_begin,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lrefuse_unlock
        mov d1,(16,sp)
        mov d1,a0
        mov (100,a0),d0
        mov d0,(20,sp)
.Lstock:
        mov (8,sp),d0
        cmp 0,d0
        bne .Lcall_capture
        /* Peek/replace the saved entry block so LIR/LAR/MDR/inputs are
         * original at the replay. SP-local ADD instructions keep PSW. */
        add 32,sp
        movm (sp),[d3,other]
        movm [d3,other],(sp)
        add -32,sp
        mov (4,sp),d1
        mov d1,psw
        call lut_gm1_producer_replay_preview,[d2,a2,a3],16
        bra .Lposted
.Lcall_capture:
        add 32,sp
        movm (sp),[d3,other]
        movm [d3,other],(sp)
        add -32,sp
        mov (4,sp),d1
        mov d1,psw
        call lut_gm1_producer_replay_capture,[d2,a2,a3],16
.Lposted:
        /* Preserve the entire original volatile/loop result across cleanup.
         * After this push, locals are shifted32bytes. */
        mov psw,d3
        movm [other],(sp)
        mov d3,(36,sp)
        mov (44,sp),a0
        cmp 0,a0
        beq .Lreturn_original
        cmp 0,d0
        beq .Lunlock_posted
        mov (48,sp),a1
        mov (52,sp),d0
        call lut_gm1_request_finish,[d2,d3,a2,a3],20
.Lunlock_posted:
        /* No successful-post slot dereference: task29 may have retired it. */
        mov (44,sp),a0
        mov (40,sp),d0
        call lut_gm1_producer_bank_unlock,[d2,d3,a2,a3],20
.Lreturn_original:
        mov (36,sp),d3
        mov d3,psw
        movm (sp),[other]
        add 32,sp
        mov (32,sp),d3
        add 36,sp
        ret [d2,a2,a3],16
.Lrefuse_unlock:
        mov (12,sp),a0
        mov (8,sp),d0
        call lut_gm1_producer_bank_unlock,[d2,d3,a2,a3],20
.Lrefuse:
        mov (4,sp),d3
        mov d3,psw
        add 32,sp
        movm (sp),[d3,other]
        mov 1,d0
        ret [d2,a2,a3],16

/* Exact displaced seven-byte prefixes under the original B0/16 frame. */
lut_gm1_producer_replay_preview:
        mov d0,d2
        movhu (0x7027b3e4),d0
        jmp native_preview_continue
lut_gm1_producer_replay_capture:
        mov d0,d2
        movhu (0x7027b500),d0
        jmp native_capture_continue
lut_gm1_producer_hooks_end:
