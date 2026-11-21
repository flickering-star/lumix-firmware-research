/* GM1 interfaces for the shared GM5 LAJ1 worker state machine, F0/20.
 * Operations keep the existing GM1 parser, durable mutation and cleanup code.
 * The UI owner has selected Standard before submission. No drawing or native
 * pool initialization runs here. Close releases the transient list, retaining
 * GM1's shared processing session and its loaded Photo Style cells.
 */
        .text
        .am33_2
        .global lut_gm1_async_scan,lut_gm1_async_load,lut_gm1_async_clear
        .global lut_gm1_async_dismiss,lut_gm1_async_release,lut_gm1_async_close_list
        .global lut_gm1_async_cancel,lut_gm1_async_mask,lut_gm1_async_operations_end
        .extern lut_gm1_library_scan,lut_gm1_library_commit,lut_gm1_library_dismiss
        .extern lut_gm1_library_get,lut_gm1_control_get,lut_gm1_durable_clear
        .extern lut_gm1_durable_resolve,lut_load_dialog_cancel
        .equ S,0x708f52c8
lut_gm1_async_scan:
        call lut_gm1_library_scan,[d2,d3,a2,a3],20
        ret [d2,d3,a2,a3],20
lut_gm1_async_load:
        cmp 1,d1
        bne .Largs
        cmp 64,d0
        bcc .Largs
        mov d0,(S+84)
        call lut_gm1_library_commit,[d2,d3,a2,a3],20
        ret [d2,d3,a2,a3],20
lut_gm1_async_clear:
        mov d0,d2
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov d1,a0
        mov d2,d0
        call lut_gm1_durable_clear,[d2,d3,a2,a3],20
        ret [d2,d3,a2,a3],20
lut_gm1_async_dismiss:
lut_gm1_async_close_list:
        mov a0,a3
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov d0,a2
        mov d1,a0
        mov (16,a0),d0
        add 32,d0
        cmp a3,d0
        bne .Largs
        add 2400,a3
        mov (112,a3),d0
        cmp 0,d0
        beq .Lresolve
        cmp 0x31525444,d0
        bne .Largs
        mov (124,a3),d0
        mov (36,a3),d1
        cmp d1,d0
        bne .Largs
        mov (24,a3),d0
        cmp 4,d0
        bne .Largs
        mov (116,a3),d0
        cmp 2,d0
        beq .Lretry_epoch
        cmp 3,d0
        bne .Largs
.Lretry_epoch:
        mov (4928,a2),d0
        cmp 0x31544744,d0
        bne .Largs
        mov (4952,a2),d0
        mov (120,a3),d1
        cmp d1,d0
        bne .Largs
        mov (4932,a2),d0
        cmp 4,d0
        bcs .Largs
        cmp 6,d0
        bhi .Largs
.Lresolve:
        mov a2,a0
        call lut_gm1_durable_resolve,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
lut_gm1_async_release:
        call lut_gm1_library_dismiss,[d2,d3,a2,a3],20
.Lreturn:
        ret [d2,d3,a2,a3],20
lut_gm1_async_cancel:
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov d0,a0
        add 128,a0
        call lut_load_dialog_cancel,[d2,d3,a2,a3],20
        ret [d2,d3,a2,a3],20
lut_gm1_async_mask:
        call lut_gm1_control_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lmask_error
        mov d1,a0
        movhu (304,a0),d0
        clr d1
        ret [d2,d3,a2,a3],20
.Lmask_error:
        clr d0
        mov -18,d1
        ret [d2,d3,a2,a3],20
.Largs:
        mov -18,d0
        ret [d2,d3,a2,a3],20
lut_gm1_async_operations_end:
