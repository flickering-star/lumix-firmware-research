/* Keep the original GM1 formatter and bitmap painter. Only select the owned
 * unsigned number table and scale for the loaded LUT's native Contrast row.
 * Both adapters preserve the caller frame and scratch state before resuming.
 * No global text/widget substitution, allocation, storage or startup hook.
 */
        .text
        .am33_2
        .global lut_gm1_op_number,lut_gm1_op_scale
        .global lut_gm1_op_render_code_end,lut_gm1_op_render_end
        .global lut_gm1_op_number_table
        .extern lut_gm1_opacity_read
        .extern native_number_continue,native_number_call,native_bitmap_paint

lut_gm1_op_number:
        add -28,sp
        mov d0,(4,sp)
        mov d1,(8,sp)
        mov a0,(12,sp)
        mov a1,(16,sp)
        mov mdr,d0
        mov d0,(20,sp)
        mov psw,d0
        mov d0,(24,sp)
        cmp 0,d1
        bne .Lnumber_stock
        movbu (0x702250fa),d0
        call lut_gm1_opacity_read,[d2,d3,a2,a3],20
        cmp -1,d0
        beq .Lnumber_stock
        mov d0,(4,sp)
        mov lut_gm1_op_number_table,a0
        mov a0,(12,sp)
        mov (24,sp),d0
        mov d0,psw
        mov (20,sp),d0
        mov d0,mdr
        mov (8,sp),d1
        mov (12,sp),a0
        mov (16,sp),a1
        mov (4,sp),d0
        add 28,sp
        jmp native_number_call
.Lnumber_stock:
        mov (24,sp),d0
        mov d0,psw
        mov (20,sp),d0
        mov d0,mdr
        mov (8,sp),d1
        mov (12,sp),a0
        mov (16,sp),a1
        mov (4,sp),d0
        add 28,sp
        mov 0x702250fb,a0
        jmp native_number_continue

/* Entered using the original C0/28 bitmap CALL frame. Tail-dispatch the same
 * painter with original coordinates, mode and stack arguments. */
lut_gm1_op_scale:
        add -28,sp
        mov d0,(4,sp)
        mov d1,(8,sp)
        mov a0,(12,sp)
        mov a1,(16,sp)
        mov mdr,d0
        mov d0,(20,sp)
        mov psw,d0
        mov d0,(24,sp)
        movhu (0x702267d8),d0
        cmp 0,d0
        bne .Lscale_finish
        movbu (0x702250fa),d0
        call lut_gm1_opacity_read,[d2,d3,a2,a3],20
        cmp -1,d0
        beq .Lscale_finish
        mov 7011,a0
        mov a0,(12,sp)
.Lscale_finish:
        mov (24,sp),d0
        mov d0,psw
        mov (20,sp),d0
        mov d0,mdr
        mov (8,sp),d1
        mov (12,sp),a0
        mov (16,sp),a1
        mov (4,sp),d0
        add 28,sp
        jmp native_bitmap_paint
lut_gm1_op_render_code_end:
        .balign 4
lut_gm1_op_number_table:
        .hword 0,7000,1,7001,2,7002,3,7003,4,7004,5,7005
        .hword 6,7006,7,7007,8,7008,9,7009,10,7010,65535,65535
lut_gm1_op_render_end:
