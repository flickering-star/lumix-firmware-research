/* GM1 native Contrast-row Opacity adapters. Values are ticks0..10 in the
 * owned336-byte UI allocation; processing parameters remain5,5,5,5,0.
 * Original numeric navigation, native setter ABI and parent transaction
 * continue. No SD, persistent-bank writer, capture hook or new boot entry.
 */
        .text
        .am33_2
        .global lut_gm1_op_get,lut_gm1_op_set
        .global lut_gm1_op_decrease,lut_gm1_op_increase
        .global lut_gm1_op_parameters,lut_gm1_op_widgets
        .global lut_gm1_op_backup,lut_gm1_op_cancel,lut_gm1_op_leave
        .global lut_gm1_op_end
        .extern lut_gm1_ui_rows,native_previous,native_next,native_set_entry
        .extern native_pending,native_row_state,native_parameter_mode,native_style_mode
        .extern native_get_continue,native_set_continue
        .extern native_decrease_continue,native_increase_continue
        .extern native_parameters_continue,native_widgets_continue
        .extern native_backup,native_cancel_continue
        .extern native_leave_zero,native_leave_nonzero
        .equ OWNER,0x708f47a4
        .equ SELECTED,0x70101252
        .equ PARAMETER,0x70102930

/* F0/20, D0 preserved; A0=validated owner or0. No allocation or lock. */
.Lowner:
        mov d0,d2
        mov (OWNER),a0
        mov a0,d0
        and 3,d0
        bne .Lno_owner
        mov a0,d0
        cmp 0x70789490,d0
        bcs .Lno_owner
        cmp 0x708e172c,d0
        bhi .Lno_owner
        mov (a0),d0
        cmp 0x3149544c,d0
        bne .Lno_owner
        mov (4,a0),d0
        cmp a0,d0
        bne .Lno_owner
        mov (8,a0),d0
        cmp 336,d0
        bne .Lno_owner
        mov (12,a0),d0
        cmp 288,d0
        beq .Lowner_done
.Lno_owner:
        mov 0,a0
.Lowner_done:
        mov d2,d0
        ret [d2,d3,a2,a3],20

/* F0/20, D0style preserved; A0=owner for matching selected loaded LUT. */
.Lloaded:
        mov d0,d3
        mov d0,d2
        extbu d2
        cmp 7,d2
        bcs .Lnot_loaded
        cmp 16,d2
        bhi .Lnot_loaded
        movbu (SELECTED),d0
        cmp d2,d0
        bne .Lnot_loaded
        call .Lowner,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lnot_loaded
        movhu (304,a0),d1
        sub 7,d2
        lsr d2,d1
        and 1,d1
        bne .Lloaded_done
.Lnot_loaded:
        mov 0,a0
.Lloaded_done:
        mov d3,d0
        ret [d2,d3,a2,a3],20

/* The leaf's RETF uses MDR. Save it as well as the nested outgoing word,
 * so refusal can tail-delegate with the original fast-return state. */
lut_gm1_op_get:
        cmp 0,d0
        bne .Lget_stock
        movbu (SELECTED),d1
        cmp 7,d1
        bcs .Lget_stock
        cmp 16,d1
        bhi .Lget_stock
        add -8,sp
        mov mdr,d0
        mov d0,(4,sp)
        mov d1,d0
        call .Lloaded,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lget_refused
        sub 7,d0
        add d0,a0
        movbu (308,a0),d0
        cmp 10,d0
        bls .Lget_done
        mov 10,d0
.Lget_done:
        ret [d2],12
.Lget_refused:
        mov (4,sp),d0
        mov d0,mdr
        add 8,sp
        clr d0
.Lget_stock:
        mov d0,d2
        mov 255,d0
        mov d2,d1
        jmp native_get_continue

/* Original C0/12 setter, D0style/D1parameter/A0tick. */
lut_gm1_op_set:
        mov a0,d3
        mov d1,d2
        extbu d0
        cmp 7,d0
        bcs .Lset_stock
        cmp 16,d0
        bhi .Lset_stock
        call .Lloaded,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lset_stock
        cmp 0,d2
        bne .Lset_done
        cmp 10,d3
        bhi .Lset_done
        sub 7,d0
        add d0,a0
        movbu d3,(308,a0)
        mov 1,d0
        call native_pending,[],0
.Lset_done:
        ret [d2,d3],12
.Lset_stock:
        mov d2,d1
        mov d3,a0
        cmp 19,d0
        jmp native_set_continue

/* Original D2/8 key-step frames; stock routines remain the fallback. */
lut_gm1_op_decrease:
        movbu (SELECTED),d0
        cmp 7,d0
        bcs .Ldecrease_stock
        cmp 16,d0
        bhi .Ldecrease_stock
        call .Lloaded,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Ldecrease_stock
        movhu (PARAMETER),d1
        cmp 0,d1
        bne .Lstep_done
        mov d0,d1
        clr d0
        call .Lstep,[d2,d3,a2,a3],20
.Lstep_done:
        ret [d2],8
.Ldecrease_stock:
        movhu (PARAMETER),d0
        jmp native_decrease_continue
lut_gm1_op_increase:
        movbu (SELECTED),d0
        cmp 7,d0
        bcs .Lincrease_stock
        cmp 16,d0
        bhi .Lincrease_stock
        call .Lloaded,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lincrease_stock
        movhu (PARAMETER),d1
        cmp 0,d1
        bne .Lstep_done
        mov d0,d1
        mov 1,d0
        call .Lstep,[d2,d3,a2,a3],20
        ret [d2],8
.Lincrease_stock:
        movhu (PARAMETER),d0
        jmp native_increase_continue
.Lstep:
        mov d0,d3
        mov d1,d2
        mov d1,d0
        call .Lloaded,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lstep_return
        sub 7,d2
        add d2,a0
        movbu (308,a0),d2
        cmp 10,d2
        bls .Lstep_tick
        mov 10,d2
.Lstep_tick:
        mov 0x708f47d8,a0
        call lut_gm1_ui_rows,[d2,d3,a2,a3],20
        mov d2,d0
        clr d1
        cmp 0,d3
        bne .Lstep_next
        call native_previous,[d2,d3,a2,a3],20
        bra .Lstep_store
.Lstep_next:
        call native_next,[d2,d3,a2],16
.Lstep_store:
        mov d0,a0
        movbu (SELECTED),d0
        clr d1
        call native_set_entry,[d2,d3],12
.Lstep_return:
        ret [d2,d3,a2,a3],20

/* Same B0/16 frames as the two original capability builders. */
lut_gm1_op_parameters:
        call .Loriginal_parameters,[d2,a2,a3],16
        movbu (SELECTED),d0
        call .Lloaded,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lparameters_done
        add 160,a0
        mov a0,a2
        .irp ident,1,2,3,4
        mov a2,a0
        mov \ident,d0
        mov 1,d1
        call native_row_state,[d2,d3],8
        .endr
.Lparameters_done:
        ret [d2,a2,a3],16
.Loriginal_parameters:
        mov d1,d2
        call native_parameter_mode,[d2],8
        jmp native_parameters_continue
lut_gm1_op_widgets:
        call .Loriginal_widgets,[d2,a2,a3],16
        movbu (SELECTED),d0
        call .Lloaded,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lwidgets_done
        movbu (162,a0),d2
        mov 0x708f8810,a2
        mov 0x708f8878,a3
        .irp ident,0x1605,0x1606,0x1607,0x160f,0x1609
        mov a2,a0
        mov \ident,d0
        mov 1,d1
        call native_row_state,[d2,d3],8
        mov a3,a0
        mov \ident,d0
        mov 1,d1
        call native_row_state,[d2,d3],8
        .endr
        mov a2,a0
        mov 0x1604,d0
        mov d2,d1
        call native_row_state,[d2,d3],8
        mov a3,a0
        mov 0x1604,d0
        mov d2,d1
        call native_row_state,[d2,d3],8
.Lwidgets_done:
        ret [d2,a2,a3],16
.Loriginal_widgets:
        mov d0,d2
        call native_style_mode,[d2],8
        jmp native_widgets_continue

/* Preserve all scratch/loop/MDR state at the original parent boundaries.
 * Native656-byte backup/cancel and existing page restoration still run.
 */
lut_gm1_op_backup:
        movm [other],(sp)
        add -8,sp
        mov psw,d0
        mov d0,(4,sp)
        call .Lowner,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lbackup_done
        .irp offset,0,1,2,3,4,5,6,7,8,9
        movbu (308+\offset,a0),d0
        movbu d0,(320+\offset,a0)
        .endr
        movhu (306,a0),d0
        or 2,d0
        movhu d0,(306,a0)
.Lbackup_done:
        mov (4,sp),d0
        mov d0,psw
        add 8,sp
        movm (sp),[other]
        jmp native_backup
lut_gm1_op_cancel:
        movm [other],(sp)
        add -8,sp
        mov psw,d0
        mov d0,(4,sp)
        call .Lowner,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lcancel_done
        movhu (306,a0),d0
        and 2,d0
        beq .Lcancel_done
        .irp offset,0,1,2,3,4,5,6,7,8,9
        movbu (320+\offset,a0),d0
        movbu d0,(308+\offset,a0)
        .endr
        movhu (306,a0),d0
        and 65533,d0
        movhu d0,(306,a0)
.Lcancel_done:
        mov (4,sp),d0
        mov d0,psw
        add 8,sp
        movm (sp),[other]
        movhu (0x7004de2e),d0
        jmp native_cancel_continue
lut_gm1_op_leave:
        movm [other],(sp)
        add -8,sp
        mov psw,d0
        mov d0,(4,sp)
        call .Lowner,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lleave_done
        movhu (306,a0),d0
        and 65533,d0
        movhu d0,(306,a0)
.Lleave_done:
        mov (4,sp),d0
        mov d0,psw
        add 8,sp
        movm (sp),[other]
        extbu d0
        cmp 0,d0
        bne .Lleave_nonzero
        jmp native_leave_zero
.Lleave_nonzero:
        jmp native_leave_nonzero
lut_gm1_op_end:
