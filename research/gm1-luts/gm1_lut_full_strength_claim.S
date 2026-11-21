.text
.am33_2
.equ UI_WORD,0x708f47a4
.global lut_gm1_request_claim
.org 0,0xff
lut_gm1_request_claim:
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
        call fixed_owned_ready,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lclaim_invalid
        mov d0,a2
        mov d2,d0
        asl 7,d0
        mov a2,a0
        add 96,a0
        add d0,a0
        mov a0,(12,sp)
        mov psw,d3
        and 63487,psw
        mov (12,a3),d0
        cmp 2,d0
        bne .Lclaim_busy_masked
        mov (16,a3),d0
        cmp a2,d0
        bne .Lclaim_busy_masked
        mov (20,a3),d0
        cmp 13,d0
        bcc .Lclaim_busy_masked
        mov (96,a0),d0
        cmp 0,d0
        bne .Lclaim_busy_masked
        mov (68,a0),d0
        cmp 1,d0
        bne .Lclaim_busy_masked
        mov (24,a3),d0
        cmp -1,d0
        beq .Lclaim_token_masked
        inc d0
        mov d0,(24,a3)
        mov d0,(100,a0)
        mov 1,d0
        mov d0,(96,a0)
        mov (20,a3),d0
        inc d0
        mov d0,(20,a3)
        movbu (0x70101252),d0
        cmp 16,d0
        bhi .Lfixed_stock_style
        cmp 7,d0
        bcs .Lclaim_style
        mov (0x700fcec8),d1
        cmp 2,d1
        bne .Lclaim_style
.Lfixed_stock_style:
        clr d0
.Lclaim_style:
        mov d0,(112,a0)
        cmp 7,d0
        bcs .Lclaim_success
        sub 7,d0
        mov (UI_WORD),a1
        movhu (304,a1),d1
        lsr d0,d1
        and 1,d1
        beq .Lclaim_stock
        bra .Lclaim_success
.Lclaim_stock:
        clr d0
        mov d0,(112,a0)
.Lclaim_success:
        mov (12,sp),d1
        mov d3,psw
        clr d0
        ret [d2,d3,a2,a3],36
.Lclaim_token_masked:
        mov d3,psw
        mov -17,d0
        bra .Lclaim_return
.Lclaim_busy_masked:
        mov d3,psw
        mov -2,d0
        bra .Lclaim_return
.Lclaim_invalid:
        mov -18,d0
        bra .Lclaim_return
.Lclaim_args:
        mov -1,d0
.Lclaim_return:
        clr d1
        ret [d2,d3,a2,a3],36
