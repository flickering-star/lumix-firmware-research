/* Replacement producer bodies. Bank APIs and original producer replays use
 * their existing stock-tracking definitions. Allocate locals first so a
 * pop of the input registers leaves all request bookkeeping above SP.
 * Entry: 32 local bytes, then 36 saved register bytes below those locals.
 */
        .equ PRODUCER_SAVED,36
        .equ PRODUCER_PSW,PRODUCER_SAVED+4
        .equ PRODUCER_MODE,PRODUCER_SAVED+8
        .equ PRODUCER_CTRL,PRODUCER_SAVED+12
        .equ PRODUCER_SLOT,PRODUCER_SAVED+16
        .equ PRODUCER_TOKEN,PRODUCER_SAVED+20
        .equ POST_SAVED,32

lut_gm1_producer_preview:
        add -32,sp
        movm [d3,other],(sp)
        mov psw,d3
        mov d3,(PRODUCER_PSW,sp)
        clr d0
        mov d0,(PRODUCER_MODE,sp)
        bra .Lproduce
lut_gm1_producer_capture:
        add -32,sp
        movm [d3,other],(sp)
        mov psw,d3
        mov d3,(PRODUCER_PSW,sp)
        mov 1,d0
        mov d0,(PRODUCER_MODE,sp)
.Lproduce:
        clr d0
        mov d0,(PRODUCER_CTRL,sp)
        call lut_gm1_control_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lstock
        mov d0,a0
        mov (PRODUCER_MODE,sp),d0
        call lut_gm1_producer_bank_lock,[d2,d3,a2,a3],20
        cmp -3,d0
        beq .Lstock
        cmp 0,d0
        bne .Lrefuse
        mov d1,(PRODUCER_CTRL,sp)
        mov d1,a0
        mov (PRODUCER_MODE,sp),d0
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
        mov d1,(PRODUCER_SLOT,sp)
        mov d1,a0
        mov (100,a0),d0
        mov d0,(PRODUCER_TOKEN,sp)
.Lstock:
        mov (PRODUCER_MODE,sp),d0
        cmp 0,d0
        bne .Lcall_capture
        mov (PRODUCER_PSW,sp),d3
        mov d3,psw
        movm (sp),[d3,other]
        movm [d3,other],(sp)
        call lut_gm1_producer_replay_preview,[d2,a2,a3],16
        bra .Lposted
.Lcall_capture:
        mov (PRODUCER_PSW,sp),d3
        mov d3,psw
        movm (sp),[d3,other]
        movm [d3,other],(sp)
        call lut_gm1_producer_replay_capture,[d2,a2,a3],16
.Lposted:
        mov psw,d3
        movm [other],(sp)
        mov d3,(PRODUCER_PSW+POST_SAVED,sp)
        mov (PRODUCER_CTRL+POST_SAVED,sp),a0
        cmp 0,a0
        beq .Lreturn_original
        cmp 0,d0
        beq .Lunlock_posted
        mov (PRODUCER_SLOT+POST_SAVED,sp),a1
        mov (PRODUCER_TOKEN+POST_SAVED,sp),d0
        call lut_gm1_request_finish,[d2,d3,a2,a3],20
.Lunlock_posted:
        /* Post may already have scheduled the consumer and retired its slot. */
        mov (PRODUCER_CTRL+POST_SAVED,sp),a0
        mov (PRODUCER_MODE+POST_SAVED,sp),d0
        call lut_gm1_producer_bank_unlock,[d2,d3,a2,a3],20
.Lreturn_original:
        mov (PRODUCER_PSW+POST_SAVED,sp),d3
        mov d3,psw
        movm (sp),[other]
        mov (32,sp),d3
        add 68,sp
        ret [d2,a2,a3],16
.Lrefuse_unlock:
        mov (PRODUCER_CTRL,sp),a0
        mov (PRODUCER_MODE,sp),d0
        call lut_gm1_producer_bank_unlock,[d2,d3,a2,a3],20
.Lrefuse:
        /* The original caller still needs completion after a clean refusal. */
        clr d0
        mov d0,(PRODUCER_CTRL,sp)
        jmp .Lstock

        /* Preserve the already bound replay entry addresses. */
        .space 15,0xff
