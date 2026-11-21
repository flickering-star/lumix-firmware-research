/* GM1 task29 request exposure, original dispatcher and constructor-tail hook.
 * enter(A0CTRL,A1original16B envelope) CALL F0/20 ->D0status,D1slot/0.
 * active() CALL F0/20 ->D0CTRL,D1slot, or0/0, only native CPU0 task29.
 * Worker CALL[]/44 and constructor tail CALLF0/36 become checked JMPs.
 * Original queue tuples, native code/frames, loop state and outputs retained.
 * No allocation, shared native registry, file, boot or persistence operation.
 */
        .text
        .am33_2
        .global lut_gm1_dispatch_enter,lut_gm1_dispatch_active
        .global lut_gm1_dispatch_wrapper,lut_gm1_constructor_tail_wrapper
        .global lut_gm1_dispatch_replay,lut_gm1_dispatch_hooks_end
        .extern lut_gm1_control_get,lut_image_view,lut_ram_span
        .extern lut_gm1_request_finish,lut_gm1_job_apply,native_context
        .extern native_dispatch,native_dispatch_return,native_constructor_tail,native_constructor_tail_return

/* Only the actual CPU0 normal-context camera worker may expose/apply a job.
 * ->D0controller,D1raw session, or0/0. No metadata allocation. */
.Lworker:
        mov (0x8050),d0
        cmp 0,d0
        bne .Lzero
        mov (0x93f00030),d0
        cmp 0x7be2ce04,d0
        bne .Lzero
        call native_context,[],0
        extbu d0
        cmp 0,d0
        bne .Lzero
        mov (0x708e90fc),d0
        cmp 0x708e252c,d0
        bne .Lzero
        call lut_gm1_control_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lzero
        mov d0,a3
        mov (12,a3),d0
        cmp 2,d0
        bne .Lzero
        mov (64,a3),d0
        cmp 13,d0
        bne .Lzero
        mov a3,a0
        add 32,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lzero
        cmp 3072,d1
        bne .Lzero
        mov (16,a3),d1
        cmp d1,d0
        bne .Lzero
        mov d0,a0
        mov (32,a0),d0
        cmp 0x31504647,d0
        bne .Lzero
        mov (36,a0),d0
        cmp a3,d0
        bne .Lzero
        mov a0,d1
        mov a3,d0
        ret [d2,d3,a2,a3],20
.Lzero:
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20

lut_gm1_dispatch_enter:
        add -20,sp
        mov a0,(4,sp)
        mov a1,(8,sp)
        call .Lworker,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lenter_untracked
        mov (4,sp),a3
        cmp a3,d0
        bne .Lenter_invalid
        mov d1,(12,sp)
        mov (8,sp),d0
        and 3,d0
        bne .Lenter_invalid
        mov (8,sp),d0
        mov 16,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lenter_invalid
        mov (8,sp),a0
        movhu (a0),d0
        cmp 0,d0
        bne .Lenter_untracked
        movhu (2,a0),d0
        cmp 28,d0
        bne .Lenter_untracked
        mov (4,a0),d0
        cmp 1,d0
        bhi .Lenter_untracked
        mov d0,(16,sp)
        mov (8,a0),d1
        mov 0x7027b3c0,a1
        mov 3,d3
        clr d2
        cmp 0,d0
        beq .Ltuple
        mov 0x7027b488,a1
        mov 10,d3
        mov 3,d2
.Ltuple:
        cmp a1,d1
        beq .Ltuple_found
        add 12,a1
        inc d2
        sub 1,d3
        bne .Ltuple
        bra .Lenter_invalid
.Ltuple_found:
        mov (12,sp),a2
        mov d2,d0
        asl 7,d0
        add 96,a2
        add d0,a2
        mov psw,d3
        and 63487,psw
        mov (12,a3),d0
        cmp 2,d0
        bne .Lenter_busy
        mov (68,a3),d0
        cmp 0,d0
        bne .Lenter_busy
        mov (20,a3),d0
        cmp 1,d0
        bcs .Lenter_missing_masked
        cmp 13,d0
        bhi .Lenter_invalid_masked
        mov (16,a3),d0
        mov (12,sp),d1
        cmp d1,d0
        bne .Lenter_invalid_masked
        mov (96,a2),d0
        cmp 0,d0
        beq .Lenter_missing_masked
        cmp 2,d0
        bne .Lenter_busy
        mov (100,a2),d0
        cmp 0,d0
        beq .Lenter_invalid_masked
        mov (104,a2),d0
        mov (16,sp),d1
        cmp d1,d0
        bne .Lenter_invalid_masked
        cmp 0,d0
        beq .Lpreview_identity
        sub 3,d2
.Lpreview_identity:
        mov (108,a2),d0
        cmp d2,d0
        bne .Lenter_invalid_masked
        mov (64,a2),d0
        cmp 0x314a4d47,d0
        bne .Lenter_invalid_masked
        mov (112,a2),d0
        cmp 7,d0
        bcs .Lenter_stock
        cmp 16,d0
        bhi .Lenter_invalid_masked
        mov (68,a2),d0
        cmp 2,d0
        bne .Lenter_invalid_masked
        mov (92,a2),d0
        mov (100,a2),d1
        cmp d1,d0
        bne .Lenter_invalid_masked
        bra .Lenter_claim
.Lenter_stock:
        mov (68,a2),d0
        cmp 1,d0
        bne .Lenter_invalid_masked
.Lenter_claim:
        mov 3,d0
        mov d0,(96,a2)
        mov a2,(68,a3)
        mov d3,psw
        mov a2,d1
        clr d0
        ret [d2,d3,a2,a3],40
.Lenter_busy:
        mov d3,psw
        mov -2,d0
        bra .Lenter_return
.Lenter_invalid_masked:
        mov d3,psw
.Lenter_invalid:
        mov -18,d0
        bra .Lenter_return
.Lenter_missing_masked:
        mov d3,psw
.Lenter_untracked:
        mov -3,d0
.Lenter_return:
        clr d1
        ret [d2,d3,a2,a3],40

lut_gm1_dispatch_active:
        call .Lworker,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lzero
        mov d0,a3
        mov d1,a2
        mov (68,a3),a1
        mov a1,d0
        sub d1,d0
        sub 96,d0
        bcs .Lzero
        cmp 1664,d0
        bcc .Lzero
        and 127,d0
        bne .Lzero
        mov (96,a1),d0
        cmp 3,d0
        bne .Lzero
        mov (100,a1),d0
        cmp 0,d0
        beq .Lzero
        mov a1,d1
        mov a3,d0
        ret [d2,d3,a2,a3],20

/* JMP in place of worker's CALL[]/44. Entry is the original worker SP.
 * Allocate locals above the saved registers. Restoring the input registers
 * before the original call must leave the slot and token above SP, where an
 * interrupt frame cannot overwrite them. */
lut_gm1_dispatch_wrapper:
        add -24,sp
        movm [d2,d3,a2,a3,other],(sp)
        mov psw,d3
        mov d3,(52,sp)
        mov a0,(68,sp)
        clr d0
        mov d0,(60,sp)
        call lut_gm1_control_get,[d2,d3,a2,a3],20
        mov d0,(56,sp)
        mov d0,a0
        mov (68,sp),a1
        call lut_gm1_dispatch_enter,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Ldispatch_original
        mov d1,(60,sp)
        mov d1,a0
        mov (100,a0),d0
        mov d0,(64,sp)
.Ldispatch_original:
        mov (52,sp),d3
        mov d3,psw
        movm (sp),[d2,d3,a2,a3,other]
        movm [d2,d3,a2,a3,other],(sp)
        call lut_gm1_dispatch_replay,[],44
        movm [d2,d3,a2,a3,other],(sp)
        mov psw,d3
        mov d3,(100,sp)
        mov (108,sp),d0
        cmp 0,d0
        beq .Ldispatch_return
        mov d0,a1
        mov (104,sp),a0
        mov (112,sp),d0
        call lut_gm1_request_finish,[d2,d3,a2,a3],20
.Ldispatch_return:
        mov (100,sp),d3
        mov d3,psw
        movm (sp),[d2,d3,a2,a3,other]
        add 72,sp
        jmp native_dispatch_return
        /* Keep the linked constructor entry at the existing branch target. */
        .space 6,0xff

lut_gm1_dispatch_replay:
        /* Dispatcher overwrites D0 at its first instruction. Its MDR must
         * start with the old worker link, even for an unhandled code. */
        mov native_dispatch_return,d0
        mov d0,mdr
        jmp native_dispatch

/* JMP replacing the constructor's LAST original F0/36 call. Original
 * A0 is its native64B context; +36 is the actual5856B output parent.
 * First complete the original tail. The only following constructor writes
 * are separate global halfwords; they cannot overwrite the copied table. */
lut_gm1_constructor_tail_wrapper:
        add -24,sp
        movm [d2,d3,a2,a3,other],(sp)
        mov psw,d3
        mov d3,(52,sp)
        mov a0,(56,sp)
        mov (52,sp),d3
        mov d3,psw
        movm (sp),[d2,d3,a2,a3,other]
        movm [d2,d3,a2,a3,other],(sp)
        call native_constructor_tail,[d2,d3,a2,a3],36
        mov psw,d3
        movm [other],(sp)
        mov d3,(84,sp)
        call lut_gm1_dispatch_active,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Ltail_return
        mov d1,a2
        mov (112,a2),d0
        cmp 7,d0
        bcs .Ltail_return
        cmp 16,d0
        bhi .Ltail_return
        mov (88,sp),d0
        mov 64,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Ltail_return
        mov (88,sp),a1
        movbu (a1),d0
        mov (104,a2),d1
        cmp d1,d0
        bne .Ltail_return
        mov (36,a1),a1
        mov a2,a0
        mov (100,a2),d0
        call lut_gm1_job_apply,[d2,d3,a2,a3],20
        mov d0,(120,a2)
.Ltail_return:
        mov (84,sp),d3
        mov d3,psw
        movm (sp),[other]
        add 32,sp
        movm (sp),[d2,d3,a2,a3]
        add 24,sp
        jmp native_constructor_tail_return
lut_gm1_dispatch_hooks_end:
