/* GM1 adapters for the final GM5 table/resource and title-only UI contracts.
 * No boot/card/filesystem/allocator or flash-writer hooks. Original native
 * CALL frames and leaf resource ABI remain model-specific.
 */
        .text
        .am33_2
        .global lut_gm1_parity_parameters,lut_gm1_parity_widgets
        .global lut_gm1_parity_variant,lut_gm1_parity_class,lut_gm1_parity_text
        .global lut_gm1_parity_selected_metadata,lut_gm1_parity_effective_metadata
        .global lut_gm1_parity_code_end
        .global lut_gm1_parity_parameters,lut_gm1_parity_widgets
        .global lut_gm1_parity_variant,lut_gm1_parity_class,lut_gm1_parity_text
        .global lut_gm1_parity_selected_metadata,lut_gm1_parity_effective_metadata
        .global lut_gm1_parity_code_end
        .extern previous_variant,previous_class,previous_text
        .extern native_parameter_mode,native_style_mode,native_row_state
        .extern native_parameters_continue,native_widgets_continue
        .extern selected_metadata_continue,effective_metadata_continue
        .extern lut_library_texts
        .extern native_values_continue
        .equ OWNER,0x708f47a4
        .equ SELECTED,0x70101252

.org 36,0xff
lut_gm1_parity_parameters:
        jmp lut_gm1_fixed_parameters
.org 178,0xff
lut_gm1_parity_widgets:
        jmp lut_gm1_fixed_widgets
/* Two appended vector images; all earlier variant paths are untouched. */
.org 479,0xff
lut_gm1_parity_variant:
        mov d0,d2
        exthu d2
        cmp 7120,d2
        bcs .Lvariant_previous
        cmp 7121,d2
        bhi .Lvariant_previous
        extbu d1
        cmp 0,d1
        bne .Lvariant_zero
        sub 7120,d2
        add 7261,d2
        mov d2,d0
        retf [d2],4
.Lvariant_zero:
        add d1,d1
        clr d0
        retf [d2],4
.Lvariant_previous:
        jmp previous_variant
.org 522,0xff
lut_gm1_parity_class:
        exthu d0
        cmp 7120,d0
        beq .Lbitmap
        cmp 7121,d0
        bne .Lclass_previous
.Lbitmap:
        clr d0
        retf [],0
.Lclass_previous:
        jmp previous_class

/* The same native message row means waiting until phase6 marks an error. */
.org 544,0xff
lut_gm1_parity_text:
        mov d0,d1
        exthu d1
        cmp 7036,d1
        bne .Ltext_previous
        mov (0x708f5314),d1
        cmp 4,d1
        bne .Ltext_previous
        mov (lut_library_texts+20),a0
        retf [],0
.Ltext_previous:
        jmp previous_text

/* Like final GM5, a loaded LUT passed to the parameter getter is a LUT even
 * while another style is active. Keep GM1 kind2's internal enums native. */
.global lut_gm1_parity_values
.org 576,0xff
lut_gm1_parity_values:
        jmp lut_gm1_fixed_values
/* Final GM5 normalizes UI-only LUT enums before original processing/encoder
 * metadata. GM1's offsets differ (46 and146). Keep override kind2 native.
 * PSW and other volatile inputs survive these inline relays.
 */
.org 665,0xff
lut_gm1_parity_selected_metadata:
        add -12,sp
        mov d1,(4,sp)
        mov psw,d1
        mov d1,(8,sp)
        movbu (46,a2),d0
        cmp 7,d0
        bcs .Lselected_done
        cmp 16,d0
        bhi .Lselected_done
        mov (0x700fcec8),d1
        cmp 2,d1
        beq .Lselected_done
        clr d0
.Lselected_done:
        mov (8,sp),d1
        mov d1,psw
        mov (4,sp),d1
        add 12,sp
        mov 31,a2
        movbu d0,(30,a0)
        jmp selected_metadata_continue
.org 715,0xff
lut_gm1_parity_effective_metadata:
        add -8,sp
        mov psw,d1
        mov d1,(4,sp)
        movbu (146,a2),d0
        cmp 7,d0
        bcs .Leffective_done
        cmp 16,d0
        bhi .Leffective_done
        mov (0x700fcec8),d1
        cmp 2,d1
        beq .Leffective_done
        clr d0
.Leffective_done:
        mov (4,sp),d1
        mov d1,psw
        add 8,sp
        mov -4,d1
        movbu d0,(37,a0)
        jmp effective_metadata_continue
.org 762,0xff
lut_gm1_parity_code_end:

.balign 4
.global lut_gm1_parity_names
.org 764,0xff
lut_gm1_parity_names:
.hword 0,907
.hword 1,908
.hword 2,909
.hword 3,910
.hword 4,911
.hword 5,912
.hword 6,913
.hword 7,7040
.hword 8,7041
.hword 9,7042
.hword 10,7043
.hword 11,7044
.hword 12,7045
.hword 13,7046
.hword 14,7047
.hword 15,7048
.hword 16,7049
.hword 65535,0
.balign 4
.global lut_gm1_parity_icons
.org 836,0xff
lut_gm1_parity_icons:
.hword 0,2250
.hword 1,2252
.hword 2,5145
.hword 3,5144
.hword 4,2251
.hword 5,5146
.hword 6,2249
.hword 7,7120
.hword 8,7120
.hword 9,7120
.hword 10,7120
.hword 11,7120
.hword 12,7120
.hword 13,7120
.hword 14,7120
.hword 15,7120
.hword 16,7120
.hword 65535,0
.balign 4
.global lut_gm1_parity_small
.org 908,0xff
lut_gm1_parity_small:
.hword 0,2254
.hword 1,2256
.hword 2,5149
.hword 3,5148
.hword 4,2255
.hword 5,5150
.hword 6,2253
.hword 7,7121
.hword 8,7121
.hword 9,7121
.hword 10,7121
.hword 11,7121
.hword 12,7121
.hword 13,7121
.hword 14,7121
.hword 15,7121
.hword 16,7121
.hword 65535,0
.balign 4
.global lut_gm1_parity_quick
.org 980,0xff
lut_gm1_parity_quick:
.hword 0,2254
.hword 1,2256
.hword 2,5149
.hword 3,5148
.hword 4,2255
.hword 5,5150
.hword 6,2253
.hword 7,7121
.hword 8,7121
.hword 9,7121
.hword 10,7121
.hword 11,7121
.hword 12,7121
.hword 13,7121
.hword 14,7121
.hword 15,7121
.hword 16,7121
.hword 65535,0
.balign 4
.global lut_gm1_parity_quick_status
.org 1052,0xff
lut_gm1_parity_quick_status:
.hword 0,2254
.hword 1,2256
.hword 2,5149
.hword 3,5148
.hword 4,2255
.hword 5,5150
.hword 6,2253
.hword 7,7121
.hword 8,7121
.hword 9,7121
.hword 10,7121
.hword 11,7121
.hword 12,7121
.hword 13,7121
.hword 14,7121
.hword 15,7121
.hword 16,7121
.hword 65535,0
.balign 4
.global lut_gm1_parity_quick_names
.org 1124,0xff
lut_gm1_parity_quick_names:
.hword 0,907
.hword 1,908
.hword 2,909
.hword 3,910
.hword 4,911
.hword 5,912
.hword 6,913
.hword 7,7040
.hword 8,7041
.hword 9,7042
.hword 10,7043
.hword 11,7044
.hword 12,7045
.hword 13,7046
.hword 14,7047
.hword 15,7048
.hword 16,7049
.hword 65535,0
