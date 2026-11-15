/* All Library phases reuse the tested private Language-list painter.
 * Native row/selection/page/event state is kept. Temporary filenames are
 * copied by the existing bounded controller API BEFORE original painting.
 * A render-owned192-byte stack context is published only for this CALLS
 * lifetime and TCB. Its pointer uses three bytes freed by the canonical
 * native-slider backup contract, within the existing16-byte UI reserve.
 * No borrowed directory pointer, allocation, SD read or boot action is added.
 */
        .text
        .am33_2
        .global lut_native_list_draw,lut_native_list_text,lut_native_list_is_text
        .global lut_native_list_bind
        .global lut_native_list_end
        .extern native_library_painter,lut_manager_copy_page
        .extern previous_caption_text,previous_caption_is_text
        .extern cell_descriptors,action_descriptors,file_descriptors
        .extern confirm_descriptors,busy_descriptors
        .extern label_load,label_clear,label_standard,label_cancel
        .extern label_wait,label_error,label_empty,label_file,label_opacity
        .extern contrast_resource
        .extern native_list_bind,empty_rows
        .equ flags,0x70a0dec2
        .equ S,0x70a0e978

/* D0screen,D1selection,A0rows; same original A0/12 CALL frame.
 * An empty file list needs one visible message row for the native painter.
 * The original manager still refuses selecting a file when its count is0.
 */
lut_native_list_bind:
        mov a0,a2
        mov (S+76),d0
        cmp 2,d0
        bne .Lbind_original
        mov (S+72),a0
        cmp 0,a0
        beq .Lbind_original
        mov (2452,a0),d0
        cmp 0,d0
        bne .Lbind_original
        mov empty_rows,a2
.Lbind_original:
        mov 0x10f0,d0
        mov a2,a0
        call native_list_bind,[d2,a2],12
        ret [d2,a2],12

lut_native_list_draw:
        movm [d2,d3,a2,a3],(sp)
        add -224,sp
        movhu (0x702d2316),d0
        cmp 0x10f0,d0
        bne .Ldraw_done
        mov (S+4),d0
        cmp 1,d0
        bne .Ldraw_done
        movbu (flags),d0
        btst 1,d0
        bne .Ldraw_done
        mov (S+76),d2
        cmp 6,d2
        bhi .Ldraw_done
        cmp 5,d2
        beq .Ldraw_done
        mov sp,a3
        add 32,a3
        mov a3,a0
        mov 48,d1
        clr d0
.Lzero_context:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lzero_context
        mov 0x3144524c,d0
        mov d0,(a3)
        mov (0x70a01d48),d0
        mov d0,(4,a3)
        mov d2,(8,a3)
        mov cell_descriptors,a2
        cmp 0,d2
        beq .Lpage_cells
        mov file_descriptors,a2
        cmp 2,d2
        beq .Lpage_files
        mov confirm_descriptors,a2
        cmp 3,d2
        beq .Lpage_chosen
        mov action_descriptors,a2
        cmp 1,d2
        beq .Lpublish
        mov busy_descriptors,a2
        bra .Lpublish
.Lpage_cells:
        clr d1
        bra .Lpage
.Lpage_files:
        mov 1,d1
.Lpage:
        /* Original row loop402af1b3 starts at first-visible byte3. Byte2
         * selects a descriptor for the highlight/geometry, not this range. */
        movbu (0x702d1aa3),d0
        cmp 64,d0
        bcc .Ldraw_done
        mov d0,(12,a3)
        bra .Lcopy_page
.Lpage_chosen:
        clr d0
        mov 2,d1
.Lcopy_page:
        mov a3,a0
        add 32,a0
        call lut_manager_copy_page,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Ldraw_done
        mov d1,(16,a3)
.Lpublish:
        mov psw,d3
        and 63487,psw
        movbu (flags),d0
        btst 1,d0
        bne .Lpublish_busy
        mov a3,d1
        movhu d1,(0x70a0dece)
        lsr 16,d1
        movbu d1,(0x70a0dec3)
        or 1,d0
        movbu d0,(flags)
        mov d3,psw
        mov 64,d0
        mov a2,a0
        call native_library_painter,[d2,d3,a2,a3],68
        mov psw,d3
        and 63487,psw
        movbu (flags),d0
        and 254,d0
        movbu d0,(flags)
        clr d0
        movbu d0,(0x70a0dec3)
        movhu d0,(0x70a0dece)
        mov d3,psw
.Ldraw_done:
        ret [d2,d3,a2,a3],240
.Lpublish_busy:
        mov d3,psw
        bra .Ldraw_done

/* Original leaf text ABI: []/0,D0resource preserved,A0text,D1/A1scratch.
 * Only a live owner TCB may resolve file names from its own stack context.
 */
lut_native_list_text:
        mov d0,a1
        exthu d0
        cmp contrast_resource,d0
        bne .Ltext_scope
        movhu (0x702d2316),d0
        cmp 0x1003,d0
        beq .Lcontrast_style
        cmp 0x1004,d0
        bne .Lprevious
.Lcontrast_style:
        movbu (0x702d23c6),d0
        cmp 7,d0
        blt .Lprevious
        cmp 16,d0
        bgt .Lprevious
        mov label_opacity,a0
        mov a1,d0
        retf [],0
.Ltext_scope:
        cmp 7900,d0
        bcs .Lprevious
        cmp 8094,d0
        bhi .Lprevious
        movbu (flags),d0
        btst 1,d0
        beq .Lstatic
        movbu (0x70a0dec3),d0
        asl 16,d0
        movhu (0x70a0dece),d1
        or d1,d0
        add 0x70000000,d0
        cmp 0x70ffff40,d0
        bhi .Lstatic
        mov d0,a0
        and 3,d0
        bne .Lstatic
        mov (a0),d0
        cmp 0x3144524c,d0
        bne .Lstatic
        mov (4,a0),d0
        mov (0x70a01d48),d1
        cmp d1,d0
        bne .Lstatic
        mov a1,d1
        exthu d1
        cmp 8012,d1
        beq .Lheader
        mov (8,a0),d0
        cmp 0,d0
        beq .Lcell_text
        cmp 2,d0
        bne .Lstatic
        sub 8020,d1
        cmp 64,d1
        bcc .Lstatic
        bra .Lpage_text
.Lcell_text:
        sub 7900,d1
        cmp 10,d1
        bcc .Lprevious
.Lpage_text:
        mov (16,a0),d0
        cmp 0,d0
        beq .Lempty
        cmp d0,d1
        bcc .Lstatic
        mov (12,a0),d0
        sub d0,d1
        cmp 5,d1
        bcc .Lstatic
        asl 5,d1
        add 32,a0
        add d1,a0
        movhu (a0),d0
        cmp 0,d0
        beq .Lprevious
        mov a1,d0
        retf [],0
.Lheader:
        mov (8,a0),d0
        cmp 2,d0
        beq .Lload
        cmp 3,d0
        bne .Lprevious
        add 32,a0
        movhu (a0),d0
        cmp 0,d0
        beq .Lprevious
        mov a1,d0
        retf [],0
.Lstatic:
        mov a1,d0
        exthu d0
        cmp 8090,d0
        beq .Lload
        cmp 8091,d0
        beq .Lclear
        cmp 8092,d0
        beq .Lstandard
        cmp 8093,d0
        beq .Lcancel
        cmp 8094,d0
        beq .Lmessage
        sub 8020,d0
        cmp 64,d0
        bcc .Lprevious
        mov label_file,a0
        bra .Lliteral
.Lload:
        mov label_load,a0
        bra .Lliteral
.Lempty:
        mov label_empty,a0
        bra .Lliteral
.Lclear:
        mov label_clear,a0
        bra .Lliteral
.Lstandard:
        mov label_standard,a0
        bra .Lliteral
.Lcancel:
        mov label_cancel,a0
        bra .Lliteral
.Lmessage:
        mov label_wait,a0
        mov (S+76),d0
        cmp 6,d0
        bne .Lliteral
        mov label_error,a0
.Lliteral:
        mov a1,d0
        retf [],0
.Lprevious:
        mov a1,d0
        jmp previous_caption_text

lut_native_list_is_text:
        exthu d0
        cmp contrast_resource,d0
        bne .Lclass_custom
        movhu (0x702d2316),d1
        cmp 0x1003,d1
        beq .Lclass_opacity_style
        cmp 0x1004,d1
        bne .Lclass_previous
.Lclass_opacity_style:
        movbu (0x702d23c6),d1
        cmp 7,d1
        blt .Lclass_previous
        cmp 16,d1
        bgt .Lclass_previous
        mov 1,d0
        retf [],0
.Lclass_custom:
        mov d0,d1
        sub 8020,d1
        cmp 75,d1
        bcc .Lclass_previous
        mov 1,d0
        retf [],0
.Lclass_previous:
        jmp previous_caption_is_text
lut_native_list_end:
