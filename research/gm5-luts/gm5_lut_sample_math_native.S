/* LUT import-time numeric primitives. Direct CALL F0/20, no memory I/O.
 * lerp: D0=a,D1=b signedQ16,A0=weight0..65536. D0=result,D1=0/-1status.
 * cube_axis: D0=RGB8,D1=minQ16,A0=maxQ16,A1=gridSize-1(1..32).
 * vlt_axis: D0=RGB8. Both axes return D0=lower index,D1=Q16weight;
 * invalid inputs return-1,-1. Clamp outside domain; endpoints use last interval.
 * Lerp nearest halves away; coordinate weight nearest halves up. Cube axis uses
 * signed domain comparisons but unsigned64-bit ratio math across full int32.
 * VLT uses manufacturer0,256,..3840,4095 input anchors. No LUT/UI/global state.
 */
        .text
        .am33_2
        .global lut_lerp_q16,lut_axis_cube_u8,lut_axis_vlt_u8,lut_sample_math_end

lut_lerp_q16:
        mov a0,d2
        cmp 65536,d2
        bhi .Llerp_invalid
        mov d1,d3
        mov 65536,d1
        sub d2,d1
        /* Default retains the historical image byte for byte. The optional
         * diagnostic uses the stock MUL/MDR idiom, without MDRQ/GETX. This
         * comparison does not establish an ISA/pipeline cause on the camera. */
        .ifdef LUT_BASIC_MULTIPLY
        mul d1,d0
        mov mdr,d1
        .else
        .byte 0xf6,0x04
        .byte 0xf6,0xf1
        .endif
        mov d0,a0
        mov d1,a1
        mov d3,d0
        mov d2,d1
        .ifdef LUT_BASIC_MULTIPLY
        mul d1,d0
        mov mdr,d1
        .else
        .byte 0xf6,0x04
        .byte 0xf6,0xf1
        .endif
        add a0,d0
        bcc .Lsum_no_carry
        inc d1
.Lsum_no_carry:
        add a1,d1
        mov 32768,d2
        cmp 0,d1
        bge .Lround
        mov 32767,d2
.Lround:
        add d2,d0
        bcc .Lround_no_carry
        inc d1
.Lround_no_carry:
        lsr 16,d0
        asl 16,d1
        or d1,d0
        clr d1
        ret [d2,d3,a2,a3],20
.Llerp_invalid:
        mov -1,d1
        ret [d2,d3,a2,a3],20

lut_axis_cube_u8:
        cmp 255,d0
        bhi .Laxis_invalid
        mov a1,d2
        cmp 1,d2
        bcs .Laxis_invalid
        cmp 32,d2
        bhi .Laxis_invalid
        mov a0,d2
        cmp d1,d2
        ble .Laxis_invalid
        asl 16,d0
        add 127,d0
        mov 255,d2
        clr d3
        mov d3,mdr
        divu d2,d0
        cmp d1,d0
        ble .Laxis_low
        cmp a0,d0
        bge .Laxis_high
        mov a0,d2
        sub d1,d2
        sub d1,d0
        mov a1,d3
        mov d3,d1
        asl 16,d1
        /* Unsigned product, retaining both 32-bit words. */
        .ifdef LUT_BASIC_MULTIPLY
        mulu d1,d0
        mov mdr,d1
        .else
        .byte 0xf6,0x14
        .byte 0xf6,0xf1
        .endif
        mov d2,a0
        lsr 1,d2
        add d2,d0
        bcc .Laxis_product_no_carry
        inc d1
.Laxis_product_no_carry:
        mov d1,mdr
        mov a0,d2
        divu d2,d0
        mov d0,d1
        and 65535,d1
        lsr 16,d0
        cmp d3,d0
        bge .Laxis_high
        ret [d2,d3,a2,a3],20
.Laxis_low:
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20
.Laxis_high:
        mov a1,d0
        sub 1,d0
        mov 65536,d1
        ret [d2,d3,a2,a3],20
.Laxis_invalid:
        mov -1,d0
        mov -1,d1
        ret [d2,d3,a2,a3],20

lut_axis_vlt_u8:
        cmp 255,d0
        bhi .Laxis_invalid
        mov 4095,d1
        mul d1,d0
        add 127,d0
        mov 255,d1
        clr d2
        mov d2,mdr
        divu d1,d0
        cmp 3840,d0
        bcc .Lvlt_last
        mov d0,d1
        and 255,d1
        asl 8,d1
        lsr 8,d0
        ret [d2,d3,a2,a3],20
.Lvlt_last:
        sub 3840,d0
        asl 16,d0
        add 127,d0
        mov 255,d1
        clr d2
        mov d2,mdr
        divu d1,d0
        mov d0,d1
        mov 15,d0
        ret [d2,d3,a2,a3],20
lut_sample_math_end:
