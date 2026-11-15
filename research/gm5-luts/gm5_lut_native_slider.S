/* Reuse the original Contrast row, native event handler, slider drawing and
 * bounded option-list helpers. Only LUT storage/value adapters are new.
 * Native slider ticks0..10 map to Strength0..100 in10-point intervals.
 * Image parameter bytes stay neutral; strength belongs to its own record.
 * Existing16-byte reserve:0mask:u16,2flags(bit0list draw,bit1backup),
 * 3draw pointer high byte,4..13canonical strength backup,14..15pointer low.
 * Parent entry canonicalizes an invalid record before taking its backup.
 */
        .text
        .am33_2
        .global lut_native_parameters,lut_native_widgets,lut_native_get
        .global lut_native_decrease,lut_native_increase,lut_native_set
        .global lut_native_parent_backup,lut_native_parent_cancel
        .global lut_native_draw_value,lut_native_draw_ticks
        .global lut_native_slider_end
        .extern previous_parameters,previous_widgets,native_row_state
        .extern native_previous,native_next,native_numeric_options
        .extern native_style_pending,native_memcpy
        .extern lut_percent_init,lut_percent_get
        .extern native_get_continue,native_set_continue
        .extern native_decrease_continue,native_increase_continue
        .extern native_backup_continue,native_cancel_continue
        .extern native_draw_value_continue,native_draw_ticks_continue
        .extern native_draw_value_stock
        .equ record,0x7bfb263c
        .equ flags,0x70a0dec2

/* Same original B0/16 frames, including all original stock capability work. */
lut_native_parameters:
        call previous_parameters,[d2,a2,a3],16
        movbu (0x701ad636),d0
        cmp 7,d0
        blt .Lparameters_done
        cmp 16,d0
        bgt .Lparameters_done
        movbu (0x70a0deb2),d2
        mov 0x70a0de90,a0
        mov 4,d0
        mov 1,d1
        call native_row_state,[d2,d3],8
        mov 0x70a0de90,a0
        clr d0
        mov d2,d1
        call native_row_state,[d2,d3],8
.Lparameters_done:
        ret [d2,a2,a3],16

lut_native_widgets:
        call previous_widgets,[d2,a2,a3],16
        movbu (0x701ad636),d0
        cmp 7,d0
        blt .Lwidgets_done
        cmp 16,d0
        bgt .Lwidgets_done
        movbu (0x70a0de92),d2
        mov 0x70a12630,a0
        mov 0x160f,d0
        mov 1,d1
        call native_row_state,[d2,d3],8
        mov 0x70a12698,a0
        mov 0x160f,d0
        mov 1,d1
        call native_row_state,[d2,d3],8
        mov 0x70a12630,a0
        mov 0x1604,d0
        mov d2,d1
        call native_row_state,[d2,d3],8
        mov 0x70a12698,a0
        mov 0x1604,d0
        mov d2,d1
        call native_row_state,[d2,d3],8
.Lwidgets_done:
        ret [d2,a2,a3],16

/* Getter's original D2/4 frame. Stock prefix is replayed exactly. */
lut_native_get:
        cmp 0,d0
        bne .Lget_stock
        movbu (0x701ad636),d1
        cmp 7,d1
        blt .Lget_stock
        cmp 16,d1
        bgt .Lget_stock
        mov d1,d0
        sub 7,d0
        /* The original leaf saves D2 in its entire four-byte frame. A
         * nested CALL needs its own outgoing slot, as in the stock ABI. */
        add -4,sp
        call .Ltick,[d2,d3,a2,a3],20
        ret [d2],8
.Lget_stock:
        mov d0,d2
        mov 255,d0
        mov d2,d1
        jmp native_get_continue

/* Original D2/8 increment/decrement frames. Generic native list navigation
 * retains the original clamp behavior; the full stock event handler calls us.
 */
lut_native_decrease:
        movhu (0x701aeec0),d0
        movbu (0x701ad636),d1
        cmp 7,d1
        blt .Ldecrease_stock
        cmp 16,d1
        bgt .Ldecrease_stock
        cmp 0,d0
        bne .Lstep_done
        clr d0
        call .Lstep,[d2,d3,a2,a3],20
.Lstep_done:
        ret [d2],8
.Ldecrease_stock:
        jmp native_decrease_continue
lut_native_increase:
        movhu (0x701aeec0),d0
        movbu (0x701ad636),d1
        cmp 7,d1
        blt .Lincrease_stock
        cmp 16,d1
        bgt .Lincrease_stock
        cmp 0,d0
        bne .Lstep_done
        mov 1,d0
        call .Lstep,[d2,d3,a2,a3],20
        ret [d2],8
.Lincrease_stock:
        jmp native_increase_continue
.Lstep:
        mov d0,d3
        mov d1,d2
        sub 7,d2
        mov d2,d0
        call .Ltick,[d2,d3,a2,a3],20
        mov native_numeric_options,a0
        clr d1
        cmp 0,d3
        bne .Lstep_next
        call native_previous,[d2,d3,a2,a3],20
        bra .Lstep_store
.Lstep_next:
        call native_next,[d2,d3,a2],16
.Lstep_store:
        mov d0,d1
        mov d2,d0
        call .Lstore,[d2,d3,a2,a3],20
        ret [d2,d3,a2,a3],20

/* Native direct/touch setter: D0style,D1parameter,A0tick; C0/12. */
lut_native_set:
        cmp 7,d0
        blt .Lset_stock
        cmp 16,d0
        bgt .Lset_stock
        cmp 0,d1
        bne .Lset_done
        sub 7,d0
        mov a0,d1
        cmp 10,d1
        bhi .Lset_done
        call .Lstore,[d2,d3,a2,a3],20
.Lset_done:
        ret [d2,d3],12
.Lset_stock:
        mov a0,d3
        extbu d0
        cmp 22,d0
        jmp native_set_continue

/* F0/20 helpers. Getter is pure; accepted writes canonicalize all ten cells. */
.Ltick:
        mov record,a0
        call lut_percent_get,[d2,d3,a2,a3],20
        add 5,d0
        clr d1
        mov d1,mdr
        mov 10,d1
        divu d1,d0
        ret [d2,d3,a2,a3],20
.Lstore:
        mov d0,d2
        mov d1,d3
        mov record,a0
        call lut_percent_init,[d2,d3,a2,a3],20
        mov 10,d1
        mul d1,d3
        mov record,a0
        add d2,a0
        movbu d3,(a0)
        call native_style_pending,[],0
        ret [d2,d3,a2,a3],20

/* Parent entry/cancel retain the native frames and stock60-byte transaction.
 * Ten canonical values need ten backup bytes; the LS tag is fixed by init.
 * Three formerly custom-child bytes can hold a renderer-owned stack pointer.
 */
lut_native_parent_backup:
        mov record,a0
        call lut_percent_init,[d2,d3,a2,a3],20
        mov 0x70a0dec4,a0
        mov record,a1
        mov 10,d0
        call native_memcpy,[a2,a3],8
        movbu (flags),d0
        or 2,d0
        movbu d0,(flags)
        movhu (0x70a1fc48),d0
        jmp native_backup_continue
lut_native_parent_cancel:
        movbu (flags),d0
        btst 2,d0
        beq .Lcancel_done
        mov record,a0
        mov 0x70a0dec4,a1
        mov 10,d0
        call native_memcpy,[a2,a3],8
        mov 0x4c53,d0
        movhu d0,(record+10)
        movbu (flags),d0
        and 253,d0
        movbu d0,(flags)
        call native_style_pending,[],0
.Lcancel_done:
        movhu (0x7001e10a),d0
        jmp native_cancel_continue

/* Read-only drawing adapters use the published style, without changing the
 * live or published neutral image-parameter arrays. Original geometry, bar,
 * cursor, widgets and text painting continue after the single value read.
 */
lut_native_draw_value:
        cmp 0,d1
        bne .Ldraw_value_stock
        movbu (0x702d23c6),d0
        cmp 7,d0
        blt .Ldraw_value_stock
        cmp 16,d0
        bgt .Ldraw_value_stock
        sub 7,d0
        call .Ltick,[d2,d3,a2,a3],20
        mov 10,d1
        mul d1,d0
        add 7911,d0
        jmp native_draw_value_continue
.Ldraw_value_stock:
        mov 0x702d23c7,a0
        jmp native_draw_value_stock
lut_native_draw_ticks:
        cmp 0,d0
        bne .Ldraw_ticks_stock
        movbu (0x702d23c6),d1
        cmp 7,d1
        blt .Ldraw_ticks_stock
        cmp 16,d1
        bgt .Ldraw_ticks_stock
        mov d1,d0
        sub 7,d0
        call .Ltick,[d2,d3,a2,a3],20
        mov d0,d1
        jmp native_draw_ticks_continue
.Ldraw_ticks_stock:
        mov 0x702d23c7,a0
        movbu (d0,a0),d1
        jmp native_draw_ticks_continue
lut_native_slider_end:
