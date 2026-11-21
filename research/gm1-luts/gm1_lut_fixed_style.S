/* Full-strength GM1 LUT diagnostic. LUT tabs have no adjustment rows.
 * No opacity settings, editor, transaction, numeric rendering or blending.
 * These are LUT availability/capability adapters, not numeric-value getters.
 * Existing retained-core ownership remains required before reading its mask.
 */
        .text
        .am33_2
        .global lut_gm1_fixed_loaded,lut_gm1_fixed_parameters,lut_gm1_fixed_widgets
        .global lut_gm1_fixed_values,lut_gm1_fixed_variant_stock,lut_gm1_fixed_class_stock
        .global lut_gm1_fixed_style_end
        .extern lut_gm1_core_ui,native_parameter_mode,native_style_mode,native_row_state
        .extern native_parameters_continue,native_widgets_continue,native_values_continue
        .extern native_variant_continue,native_class_continue
        .equ OWNER,0x708f47a4

/* F0/20,D0style ->1 loaded normal LUT/0 otherwise. No settings lookup. */
lut_gm1_fixed_loaded:
        mov d0,d2
        extbu d2
        cmp 7,d2
        bcs .Lnot_loaded
        cmp 16,d2
        bhi .Lnot_loaded
        mov (0x700fcec8),d0
        cmp 2,d0
        beq .Lnot_loaded
        call lut_gm1_core_ui,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lnot_loaded
        sub 7,d2
        movhu (304,a0),d0
        lsr d2,d0
        and 1,d0
        ret [d2,d3,a2,a3],20
.Lnot_loaded:
        clr d0
        ret [d2,d3,a2,a3],20

.Lselected:
        movbu (0x70101252),d0
        jmp lut_gm1_fixed_loaded

/* Original B0/16 frames. Keep the stock capability builder, then hide all
 * five parameter rows for a loaded LUT; the title remains selectable.
 */
lut_gm1_fixed_parameters:
        movm [other],(sp)
        add -8,sp
        mov psw,d0
        mov d0,(4,sp)
        call .Lselected,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lparameters_stock
        mov (4,sp),d0
        mov d0,psw
        add 8,sp
        movm (sp),[other]
        clr d1
        call .Loriginal_parameters,[d2,a2,a3],16
        mov (OWNER),a2
        add 160,a2
        .irp ident,0,1,2,3,4
        mov a2,a0
        mov \ident,d0
        mov 1,d1
        call native_row_state,[d2,d3],8
        .endr
        ret [d2,a2,a3],16
.Lparameters_stock:
        mov (4,sp),d0
        mov d0,psw
        add 8,sp
        movm (sp),[other]
.Loriginal_parameters:
        mov d1,d2
        call native_parameter_mode,[d2],8
        jmp native_parameters_continue

lut_gm1_fixed_widgets:
        movm [other],(sp)
        add -8,sp
        mov psw,d0
        mov d0,(4,sp)
        call .Lselected,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lwidgets_stock
        mov (4,sp),d0
        mov d0,psw
        add 8,sp
        movm (sp),[other]
        clr d0
        call .Loriginal_widgets,[d2,a2,a3],16
        mov 0x708f8810,a2
        mov 0x708f8878,a3
        .irp ident,0x1604,0x1605,0x1606,0x1607,0x160f,0x1610,0x1609
        mov a2,a0
        mov \ident,d0
        mov 1,d1
        call native_row_state,[d2,d3],8
        mov a3,a0
        mov \ident,d0
        mov 1,d1
        call native_row_state,[d2,d3],8
        .endr
        ret [d2,a2,a3],16
.Lwidgets_stock:
        mov (4,sp),d0
        mov d0,psw
        add 8,sp
        movm (sp),[other]
.Loriginal_widgets:
        mov d0,d2
        call native_style_mode,[d2],8
        jmp native_widgets_continue

/* Loaded LUTs retain neutral native processing parameters, independently
 * of which title is currently selected. No opacity read or write occurs.
 */
lut_gm1_fixed_values:
        mov d0,d3
        mov a0,a2
        mov d1,d2
        extbu d2
        cmp 7,d2
        bcs .Lvalues_native
        cmp 16,d2
        bhi .Lvalues_native
        mov (0x700fcec8),d0
        cmp 2,d0
        beq .Lvalues_native
        add -16,sp
        mov a1,(4,sp)
        mov mdr,d0
        mov d0,(8,sp)
        mov d1,(12,sp)
        mov d2,d0
        call lut_gm1_fixed_loaded,[d2,d3,a2,a3],20
        mov (4,sp),a1
        mov (8,sp),d1
        mov d1,mdr
        mov (12,sp),d1
        add 16,sp
        cmp 0,d0
        beq .Lvalues_standard
        mov 5,d0
        .irp offset,0,1,2,3
        movbu d0,(\offset,a2)
        .endr
        clr d0
        movbu d0,(4,a2)
        mov 5,d0
        ret [d2,d3,a2],16
.Lvalues_standard:
        clr d2
.Lvalues_native:
        mov a2,a0
        mov d3,d0
        cmp 19,d2
        jmp native_values_continue

/* Original native leaf prefixes used by the retained LUT icon extensions. */
lut_gm1_fixed_variant_stock:
        mov d0,d2
        exthu d2
        cmp 6849,d2
        jmp native_variant_continue
lut_gm1_fixed_class_stock:
        exthu d0
        cmp 1975,d0
        jmp native_class_continue
lut_gm1_fixed_style_end:
