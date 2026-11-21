.text
.am33_2
.global lut_gm1_request_publish
.org 0,0xff
lut_gm1_request_publish:
        add -12,sp
        mov a0,a3
        mov a1,(4,sp)
        mov d0,(8,sp)
        call fixed_owned_member,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lpublish_bad
        mov d0,d2
        mov (4,sp),a2
        mov psw,d3
        and 63487,psw
        mov (12,a3),d0
        cmp 2,d0
        bne .Lpublish_invalid_masked
        mov (16,a3),d0
        cmp d2,d0
        bne .Lpublish_invalid_masked
        mov (96,a2),d0
        cmp 1,d0
        bne .Lpublish_stale
        mov (8,sp),d0
        cmp 0,d0
        beq .Lpublish_stale
        mov (100,a2),d1
        cmp d1,d0
        bne .Lpublish_stale
        mov (112,a2),d0
        cmp 7,d0
        bcs .Lpublish_stock
        cmp 16,d0
        bhi .Lpublish_invalid_masked
        mov (68,a2),d1
        cmp 2,d1
        bne .Lpublish_invalid_masked
        sub 7,d0
        mov (72,a2),d1
        cmp d1,d0
        bne .Lpublish_invalid_masked
        mov (92,a2),d0
        mov (100,a2),d1
        cmp d1,d0
        bne .Lpublish_invalid_masked
        bra .Lpublish_ready
.Lpublish_stock:
        mov (68,a2),d0
        cmp 1,d0
        bne .Lpublish_invalid_masked
.Lpublish_ready:
        mov 2,d0
        mov d0,(96,a2)
        mov d3,psw
        clr d0
        ret [d2,d3,a2,a3],32
.Lpublish_stale:
        mov d3,psw
        mov -11,d0
        ret [d2,d3,a2,a3],32
.Lpublish_invalid_masked:
        mov d3,psw
.Lpublish_bad:
        mov -18,d0
        ret [d2,d3,a2,a3],32
