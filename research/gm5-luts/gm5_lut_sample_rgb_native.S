/* Parsed Cube/VLT RGB sampler, import-time only. CALL F0/20.
 * A0=completed owned parser context,A1=RGB8 input3,D0=RGB8 output3.
 * Return0/-1args/-2incomplete or malformed geometry/-3invalid row data.
 * Full input triple copied before output; exact/partial in-place is supported.
 * Source is immutable; output must not alias its complete context in either
 * 0x70 cached or0xb0 uncached RAM view. Default profile is modeled16MiB RAM.
 * LUT_IMAGE_UNCACHED adds only the original region1'suncachedB340..B860 range;
 * its cached view stays refused. This is address eligibility, not ownership.
 * New arithmetic: Q16 trilinear R->G->B, nearest/half-away at each axis;
 * final RGB clips only after interpolation, then nearest to8bits.
 * No metadata applicability/transfer/rendering parity is claimed here.
 */
        .text
        .am33_2
        .global lut_sample_rgb,lut_ram_span,lut_sample_rgb_end
        .extern lut_lerp_q16,lut_axis_cube_u8,lut_axis_vlt_u8

lut_sample_rgb:
        cmp 0,a0
        beq .Lbad_initial
        cmp 0,a1
        beq .Lbad_initial
        cmp 0,d0
        beq .Lbad_initial
        mov a0,d1
        and 3,d1
        bne .Lbad_initial
        add -144,sp
        mov a0,(4,sp)
        mov d0,(8,sp)
        mov a1,(132,sp)
        mov a0,d0
        mov 128,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbad_args
        mov (4,sp),a2
        mov (4,a2),d0
        cmp 2,d0
        bne .Lbad_layout
        mov (a2),d0
        cmp 0x31425543,d0
        beq .Lcube
        cmp 0x31544c56,d0
        bne .Lbad_layout
        mov (16,a2),d0
        cmp 4,d0
        bne .Lbad_layout
        mov (20,a2),d0
        cmp 4913,d0
        bne .Lbad_layout
        mov 1,d0
        mov d0,(12,sp)
        mov 17,d0
        mov d0,(16,sp)
        mov 6,d0
        mov d0,(20,sp)
        mov 1152,d0
        mov d0,(128,sp)
        mov 32768,d1
        bra .Lsource_span
.Lcube:
        mov (16,a2),d0
        cmp 2,d0
        bcs .Lbad_layout
        cmp 33,d0
        bhi .Lbad_layout
        mov d0,(16,sp)
        mov d0,d1
        mul d1,d0
        mul d1,d0
        mov (20,a2),d1
        cmp d1,d0
        bne .Lbad_layout
        mov (24,a2),d1
        cmp d1,d0
        bne .Lbad_layout
        mov 2,d0
        mov d0,(12,sp)
        mov 12,d0
        mov d0,(20,sp)
        mov 4096,d0
        mov d0,(128,sp)
        mov a2,a0
        add 64,a0
        mov 3,d2
.Ldomains:
        mov (a0),d0
        mov (12,a0),d1
        cmp d1,d0
        bge .Lbad_layout
        inc4 a0
        sub 1,d2
        bne .Ldomains
        mov 524288,d1
.Lsource_span:
        mov a2,d0
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbad_args
        mov d0,(116,sp)
        mov d1,(120,sp)
        mov (8,sp),d0
        mov 3,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbad_args
        mov (120,sp),d2
        cmp d2,d0
        bcc .Lno_source_overlap
        mov (116,sp),d2
        cmp d2,d1
        bhi .Lbad_args
.Lno_source_overlap:
        mov (132,sp),d0
        mov 3,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbad_args
        mov (132,sp),a0
        movbu (a0),d0
        mov d0,(32,sp)
        movbu (1,a0),d0
        mov d0,(36,sp)
        movbu (2,a0),d0
        mov d0,(40,sp)
        clr d3
.Laxis:
        mov d3,d0
        asl 2,d0
        mov sp,a1
        add 32,a1
        add d0,a1
        mov (a1),d0
        mov (12,sp),d1
        cmp 1,d1
        beq .Lvlt_axis
        mov d0,(124,sp)
        mov d3,d1
        asl 2,d1
        mov a2,a1
        add d1,a1
        mov (64,a1),d1
        mov (76,a1),d2
        mov d2,a0
        mov (16,sp),d2
        sub 1,d2
        mov d2,a1
        mov (124,sp),d0
        call lut_axis_cube_u8,[d2,d3,a2,a3],20
        bra .Laxis_store
.Lvlt_axis:
        call lut_axis_vlt_u8,[d2,d3,a2,a3],20
.Laxis_store:
        cmp 0,d0
        blt .Lbad_layout
        mov d3,d2
        asl 2,d2
        mov sp,a0
        add 44,a0
        add d2,a0
        mov d0,(a0)
        mov d1,(12,a0)
        inc d3
        cmp 3,d3
        bcs .Laxis
        mov (16,sp),d1
        mov (20,sp),d0
        mul d1,d0
        mov d0,(24,sp)
        mul d1,d0
        mov d0,(28,sp)
        mov (52,sp),d0
        mul d1,d0
        mov (48,sp),d2
        add d2,d0
        mul d1,d0
        mov (44,sp),d2
        add d2,d0
        mov (20,sp),d1
        mul d1,d0
        mov a2,a0
        add d0,a0
        mov (128,sp),d0
        add d0,a0
        mov a0,(140,sp)
        clr d0
        mov d0,(68,sp)
.Lcomponent:
        mov (68,sp),d0
        mov (12,sp),d1
        cmp 1,d1
        beq .Lcomponent_vlt
        asl 2,d0
        bra .Lcomponent_address
.Lcomponent_vlt:
        asl 1,d0
.Lcomponent_address:
        mov (140,sp),a0
        add d0,a0
        mov a0,(72,sp)
        clr d3
.Lcorner:
        mov (72,sp),a0
        mov d3,d0
        and 1,d0
        beq .Lcorner_g
        mov (20,sp),d0
        add d0,a0
.Lcorner_g:
        mov d3,d0
        and 2,d0
        beq .Lcorner_b
        mov (24,sp),d0
        add d0,a0
.Lcorner_b:
        mov d3,d0
        and 4,d0
        beq .Lcorner_load
        mov (28,sp),d0
        add d0,a0
.Lcorner_load:
        mov (12,sp),d0
        cmp 1,d0
        bne .Lcube_value
        movhu (a0),d0
        cmp 4095,d0
        bhi .Lbad_data
        asl 16,d0
        add 2047,d0
        mov 4095,d1
        clr d2
        mov d2,mdr
        divu d1,d0
        bra .Lvalue_store
.Lcube_value:
        mov (a0),d0
.Lvalue_store:
        mov d3,d1
        asl 2,d1
        mov sp,a0
        add 80,a0
        add d1,a0
        mov d0,(a0)
        inc d3
        cmp 8,d3
        bcs .Lcorner
        clr d0
        mov d0,(132,sp)
        mov 4,d3
.Linterpolation_stage:
        clr d2
.Linterpolation_pair:
        mov d2,d0
        asl 3,d0
        mov sp,a1
        add 80,a1
        add d0,a1
        mov (a1),d0
        mov (4,a1),d1
        mov (132,sp),a0
        add a0,a0
        add a0,a0
        mov sp,a1
        add 56,a1
        add a0,a1
        mov (a1),a0
        call lut_lerp_q16,[d2,d3,a2,a3],20
        cmp 0,d1
        bne .Lbad_data
        mov d2,d1
        asl 2,d1
        mov sp,a0
        add 80,a0
        add d1,a0
        mov d0,(a0)
        inc d2
        cmp d3,d2
        bcs .Linterpolation_pair
        mov (132,sp),d0
        inc d0
        mov d0,(132,sp)
        lsr 1,d3
        cmp 0,d3
        bne .Linterpolation_stage
        mov (80,sp),d0
        cmp 0,d0
        ble .Lclip_low
        cmp 65536,d0
        bge .Lclip_high
        mov 255,d1
        mul d1,d0
        add 32768,d0
        lsr 16,d0
        bra .Lbyte_store
.Lclip_low:
        clr d0
        bra .Lbyte_store
.Lclip_high:
        mov 255,d0
.Lbyte_store:
        mov sp,a0
        add 112,a0
        mov (68,sp),d1
        add d1,a0
        movbu d0,(a0)
        inc d1
        mov d1,(68,sp)
        cmp 3,d1
        bcs .Lcomponent
        mov (8,sp),a0
        movbu (112,sp),d0
        movbu d0,(a0)
        movbu (113,sp),d0
        movbu d0,(1,a0)
        movbu (114,sp),d0
        movbu d0,(2,a0)
        clr d0
        ret [d2,d3,a2,a3],164
.Lbad_args:
        mov -1,d0
        ret [d2,d3,a2,a3],164
.Lbad_layout:
        mov -2,d0
        ret [d2,d3,a2,a3],164
.Lbad_data:
        mov -3,d0
        ret [d2,d3,a2,a3],164
.Lbad_initial:
        mov -1,d0
        ret [d2,d3,a2,a3],20

/* D0=RAM ptr,D1=length; return canonical cached start/end or0,0.
 * Address view conversion is subtraction, not masking/xor of a single bit.
 */
lut_ram_span:
        cmp 1,d1
        bcs .Lspan_invalid
        cmp 0x1000000,d1
        bhi .Lspan_invalid
        .ifdef LUT_ADJACENT_UNCACHED
        cmp 0xb8600000,d0
        bcs .Lspan_adjacent_done
        cmp 0xbb400000,d0
        bcc .Lspan_invalid
        add -0x40000000,d0
        add d0,d1
        cmp 0x7b400000,d1
        bhi .Lspan_invalid
        ret [d2,d3,a2,a3],20
.Lspan_adjacent_done:
        .endif
        .ifdef LUT_RESERVED_UNCACHED
        /* Explicit data-only reservation in the loaded secondary image.
         * Cached/direct-bus inputs stay refused. This profile is opt-in and
         * is not part of the existing camera build. */
        cmp 0xbbe50000,d0
        bcs .Lspan_image
        cmp 0xbbe70000,d0
        bcc .Lspan_invalid
        add -0x40000000,d0
        add d0,d1
        cmp 0x7be70000,d1
        bhi .Lspan_invalid
        ret [d2,d3,a2,a3],20
.Lspan_image:
        .endif
        .ifdef LUT_IMAGE_UNCACHED
        cmp 0xb3400000,d0
        bcs .Lspan_legacy
        cmp 0xb8600000,d0
        bcc .Lspan_invalid
        add -0x40000000,d0
        add d0,d1
        cmp 0x78600000,d1
        bhi .Lspan_invalid
        ret [d2,d3,a2,a3],20
.Lspan_legacy:
        .endif
        cmp 0xb0000000,d0
        bcs .Lspan_cached
        cmp 0xb1000000,d0
        bcc .Lspan_invalid
        add -0x40000000,d0
.Lspan_cached:
        cmp 0x70000000,d0
        bcs .Lspan_invalid
        cmp 0x71000000,d0
        bcc .Lspan_invalid
        add d0,d1
        cmp 0x71000000,d1
        bhi .Lspan_invalid
        ret [d2,d3,a2,a3],20
.Lspan_invalid:
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20
lut_sample_rgb_end:
