/* GM1 adapters for the final GM5 table/resource and one-row UI contracts.
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
        .extern lut_gm1_opacity_read,lut_library_texts
        .extern native_values_continue
        .equ OWNER,0x708f47a4
        .equ SELECTED,0x70101252

/* Match the loaded normal UI style without entering an allocator/lock. */
.Lloaded:
        movbu (SELECTED),d0
        call lut_gm1_opacity_read,[d2,d3,a2,a3],20
        cmp -1,d0
        beq .Lnot_loaded
        mov (0x700fcec8),d0
        cmp 2,d0
        beq .Lnot_loaded
        mov 1,d0
        ret [d2,d3,a2,a3],20
.Lnot_loaded:
        clr d0
        ret [d2,d3,a2,a3],20

/* Preserve original inputs for the stock branch. For LUTs, final GM5 first
 * runs Standard capability work, then hides every extra row and widget.
 * Generic native navigation therefore visits the same visible rows it draws.
 */
lut_gm1_parity_parameters:
        movm [other],(sp)
        add -8,sp
        mov psw,d0
        mov d0,(4,sp)
        call .Lloaded,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lparameters_stock
        mov (4,sp),d0
        mov d0,psw
        add 8,sp
        movm (sp),[other]
        clr d1
        call .Loriginal_parameters,[d2,a2,a3],16
        mov (OWNER),a2
        movbu (162,a2),d2
        add 160,a2
        .irp ident,0,1,2,3,4
        mov a2,a0
        mov \ident,d0
        mov 1,d1
        call native_row_state,[d2,d3],8
        .endr
        mov a2,a0
        clr d0
        mov d2,d1
        call native_row_state,[d2,d3],8
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

lut_gm1_parity_widgets:
        movm [other],(sp)
        add -8,sp
        mov psw,d0
        mov d0,(4,sp)
        call .Lloaded,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lwidgets_stock
        mov (4,sp),d0
        mov d0,psw
        add 8,sp
        movm (sp),[other]
        clr d0
        call .Loriginal_widgets,[d2,a2,a3],16
        mov (OWNER),a0
        movbu (162,a0),d2
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
        movbu (0x708f475a),d0
        cmp 4,d0
        beq .Lshow_opacity
        mov 1,d2
.Lshow_opacity:
        mov a2,a0
        mov 0x1604,d0
        mov d2,d1
        call native_row_state,[d2,d3],8
        mov a3,a0
        mov 0x1604,d0
        mov d2,d1
        call native_row_state,[d2,d3],8
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

/* Two appended vector images; all earlier variant paths are untouched. */
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
        add 7273,d2
        mov d2,d0
        retf [d2],4
.Lvariant_zero:
        add d1,d1
        clr d0
        retf [d2],4
.Lvariant_previous:
        jmp previous_variant
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
lut_gm1_parity_values:
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
        call lut_gm1_opacity_read,[d2,d3,a2,a3],20
        mov (4,sp),a1
        mov (8,sp),d1
        mov d1,mdr
        mov (12,sp),d1
        add 16,sp
        cmp -1,d0
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

/* Final GM5 normalizes UI-only LUT enums before original processing/encoder
 * metadata. GM1's offsets differ (46 and146). Keep override kind2 native.
 * PSW and other volatile inputs survive these inline relays.
 */
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
lut_gm1_parity_code_end:
