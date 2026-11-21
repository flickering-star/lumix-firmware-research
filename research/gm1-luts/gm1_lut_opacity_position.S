/* Replace only the native slider's eight-byte parameter read. D0parameter
 * selects the original published array; LUT parameter0 reads its owned tick.
 * All other registers, flags, MDR and current SETLB state remain unchanged
 * relative to the original MOV/MOVBU. No loop instruction or writer occurs.
 * This is cursor positioning, not unsigned labels or complete LCD output.
 */
        .text
        .am33_2
        .global lut_gm1_op_position,lut_gm1_op_position_end
        .global lut_gm1_opacity_read
        .extern native_position_continue
lut_gm1_op_position:
        add -24,sp
        mov d0,(4,sp)
        mov d1,(8,sp)
        mov a0,(12,sp)
        mov mdr,d0
        mov d0,(16,sp)
        mov psw,d0
        mov d0,(20,sp)
        mov (4,sp),d0
        cmp 0,d0
        bne .Lstock
        movbu (0x702250fa),d0
        call .Lread,[d2,d3,a2,a3],20
        cmp -1,d0
        beq .Lstock
        mov d0,(4,sp)
        bra .Lfinish
.Lstock:
        mov (4,sp),d0
        mov 0x702250fb,a1
        movbu (d0,a1),d0
        mov d0,(4,sp)
.Lfinish:
        mov (20,sp),d0
        mov d0,psw
        mov (16,sp),d0
        mov d0,mdr
        mov (8,sp),d1
        mov (12,sp),a0
        mov (4,sp),d0
        mov 0x702250fb,a1
        add 24,sp
        jmp native_position_continue

/* F0/20 read-only lookup by the published style, independently of a newer
 * UI selection. Only the valid owner and loaded bit authorize a cell read. */
lut_gm1_opacity_read:
.Lread:
        mov d0,d2
        cmp 7,d2
        bcs .Lmissing
        cmp 16,d2
        bhi .Lmissing
        mov (0x708f47a4),a0
        mov a0,d0
        and 3,d0
        bne .Lmissing
        mov a0,d0
        cmp 0x70789490,d0
        bcs .Lmissing
        cmp 0x708e172c,d0
        bhi .Lmissing
        mov (a0),d0
        cmp 0x3149544c,d0
        bne .Lmissing
        mov (4,a0),d0
        cmp a0,d0
        bne .Lmissing
        mov (8,a0),d0
        cmp 336,d0
        bne .Lmissing
        mov (12,a0),d0
        cmp 288,d0
        bne .Lmissing
        movhu (304,a0),d1
        sub 7,d2
        lsr d2,d1
        and 1,d1
        beq .Lmissing
        add d2,a0
        movbu (308,a0),d0
        cmp 10,d0
        bls .Lread_done
        mov 10,d0
.Lread_done:
        ret [d2,d3,a2,a3],20
.Lmissing:
        mov -1,d0
        ret [d2,d3,a2,a3],20
lut_gm1_op_position_end:
