/* One retained native lease owns GM1 UI, controller and durable metadata.
 * Mirrors GM5's S+40 lease / retained core lifetime. Larger native records
 * require8192B: root32, UI336@32, controller128@384, Library6144@544.
 * Frame slots/cells keep their original separately guarded3072B session.
 * No kernel-heap owner, native allocator change, boot or filesystem hook.
 */
        .text
        .am33_2
        .global lut_gm1_core_get,lut_gm1_core_ensure,lut_gm1_core_ui
        .global lut_gm1_core_control_owner,lut_gm1_core_control_get,lut_gm1_core_control_ensure
        .global lut_gm1_core_library_get,lut_gm1_core_library_ensure,lut_gm1_core_rows
        .global lut_gm1_core_supported,lut_gm1_core_end
        .extern core_exclusive_view,lut_image_lease_open,lut_image_lease_close
        .extern native_context,native_style_supported_continue
        .equ S,0x708f52c8
        .equ UI_WORD,0x708f47a4
        .equ OLD,0x708f4768
        .equ MAGIC,0x31434c4c
        .equ BYTES,8192

/* Original shared-pool provider ABI, pure and valid during construction. */
.org 0,0xff
lut_gm1_core_control_owner:
        mov S+40,d0
        ret [d2,d3,a2,a3],20

/* Registered original descriptor validates the whole lease before any owned
 * object is read. It is retained at refcount1, independently of frame jobs.
 */
.org 9,0xff
lut_gm1_core_get:
        mov (0x8050),d0
        cmp 0,d0
        bne .Lnone
        mov (S),d0
        cmp 0x31534d4c,d0
        bne .Lnone
        mov S+40,a0
        call core_exclusive_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lnone
        cmp BYTES,d1
        bne .Lnone
        mov d0,a2
        mov (a2),d0
        cmp MAGIC,d0
        bne .Lnone
        mov (4,a2),d0
        cmp a2,d0
        bne .Lnone
        mov (8,a2),d0
        cmp BYTES,d0
        bne .Lnone
        mov (12,a2),d0
        cmp 1,d0
        bne .Lnone
        mov (BYTES-4,a2),d0
        cmp MAGIC,d0
        bne .Lnone
        mov a2,d1
        add 32,d1
        mov (UI_WORD),d0
        cmp d1,d0
        bne .Lnone
        mov (32,a2),d0
        cmp 0x3149544c,d0
        bne .Lnone
        mov (36,a2),d0
        cmp d1,d0
        bne .Lnone
        mov (40,a2),d0
        cmp 336,d0
        bne .Lnone
        mov (44,a2),d0
        cmp 288,d0
        bne .Lnone
        mov a2,d1
        add 384,d1
        mov (364,a2),d0
        cmp d1,d0
        bne .Lnone
        mov (384,a2),d0
        cmp 0x31434d47,d0
        bne .Lnone
        mov (388,a2),d0
        cmp d1,d0
        bne .Lnone
        mov (392,a2),d0
        cmp 128,d0
        bne .Lnone
        mov (556,a2),d0
        cmp d1,d0
        bne .Lnone
        mov a2,d1
        add 544,d1
        mov (464,a2),d0
        cmp d1,d0
        bne .Lnone
        mov (544,a2),d0
        cmp 0x314c4d47,d0
        bne .Lnone
        mov (548,a2),d0
        cmp d1,d0
        bne .Lnone
        mov (552,a2),d0
        cmp 6144,d0
        bne .Lnone
        mov a2,d0
        ret [d2,d3,a2,a3],20
.Lnone:
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20

.org 278,0xff
lut_gm1_core_ui:
        call lut_gm1_core_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lui_none
        add 32,d0
.Lui_none:
        mov d0,a0
        ret [d2,d3,a2,a3],20
.org 294,0xff
lut_gm1_core_control_get:
        call lut_gm1_core_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lnone
        mov d0,d1
        add 32,d1
        add 384,d0
        ret [d2,d3,a2,a3],20
.org 313,0xff
lut_gm1_core_control_ensure:
        call lut_gm1_core_ensure,[d2,d3,a2,a3],20
        jmp lut_gm1_core_control_get
.org 320,0xff
lut_gm1_core_library_get:
        call lut_gm1_core_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lnone
        mov d0,d1
        add 384,d1
        add 544,d0
        ret [d2,d3,a2,a3],20
.org 341,0xff
lut_gm1_core_library_ensure:
        call lut_gm1_core_ensure,[d2,d3,a2,a3],20
        jmp lut_gm1_core_library_get

/* Sole normal-context construction path. Native LIL1 claims its record before
 * allocation; other entries refuse an in-progress/foreign record. Unwind uses
 * the unchanged original lease close rather than fabricating native state.
 */
.org 348,0xff
lut_gm1_core_ensure:
        call lut_gm1_core_get,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lensure_return
        mov (UI_WORD),d0
        cmp 0,d0
        bne .Lnone
        mov (0x8050),d0
        cmp 0,d0
        bne .Lnone
        mov (0x93f00030),d0
        cmp 0x7be2ce04,d0
        bne .Lnone
        call native_context,[],0
        extbu d0
        cmp 0,d0
        bne .Lnone
        .irp address,0x702d23d4,0x702d23d8,0x702d23dc
        mov (\address),d0
        cmp 0,d0
        beq .Lnone
        .endr
        mov (0x702d25d8),d0
        cmp 0x7be2015c,d0
        bne .Lnone
        mov (S),d0
        cmp 0x31534d4c,d0
        beq .Lheader_ready
        mov S,a0
        mov 24,d1
.Lheader_empty:
        mov (a0),d0
        cmp 0,d0
        bne .Lnone
        inc4 a0
        sub 1,d1
        bne .Lheader_empty
        mov 0x31534d4c,d0
        mov d0,(S)
.Lheader_ready:
        .irp address,0x708f4754,0x708f6294,0x708f63dc,0x708f64f4
        mov (\address),d0
        cmp OLD,d0
        bne .Lnone
        .endr
        mov (0x708f475c),d0
        cmp OLD+64,d0
        bne .Lnone
        mov S+40,a0
        mov 8,d1
.Lrecord_empty:
        mov (a0),d0
        cmp 0,d0
        bne .Lnone
        inc4 a0
        sub 1,d1
        bne .Lrecord_empty
        mov S+40,a0
        mov BYTES,d0
        call lut_image_lease_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lcleanup
        mov S+40,a0
        call core_exclusive_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lcleanup
        cmp BYTES,d1
        bne .Lcleanup
        mov d0,a3
        mov d0,a0
        mov BYTES/4,d1
        clr d0
.Lzero:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lzero
        mov MAGIC,d0
        mov d0,(a3)
        mov d0,(BYTES-4,a3)
        mov a3,(4,a3)
        mov BYTES,d0
        mov d0,(8,a3)
        mov 1,d0
        mov d0,(12,a3)
        mov a3,a2
        add 32,a2
        mov 0x3149544c,d0
        mov d0,(a2)
        mov a2,(4,a2)
        mov 336,d0
        mov d0,(8,a2)
        mov 288,d0
        mov d0,(12,a2)
        mov OLD,a0
        mov a2,a1
        add 16,a1
        mov 14,d1
.Lstyles_copy:
        mov (a0),d0
        mov d0,(a1)
        inc4 a0
        inc4 a1
        sub 1,d1
        bne .Lstyles_copy
        mov 7,d2
.Lstyles_add:
        movhu d2,(a1)
        mov 1,d0
        movbu d0,(2,a1)
        movbu d0,(3,a1)
        clr d0
        mov d0,(4,a1)
        add 8,a1
        inc d2
        cmp 17,d2
        blt .Lstyles_add
        mov 65535,d0
        mov d0,(a1)
        clr d0
        mov d0,(4,a1)
        mov OLD+64,a0
        mov a2,a1
        add 160,a1
        mov 36,d1
.Lcontrols_copy:
        mov (a0),d0
        mov d0,(a1)
        inc4 a0
        inc4 a1
        sub 1,d1
        bne .Lcontrols_copy
        mov a3,a1
        add 384,a1
        mov a1,(332,a2)
        mov 0x31434d47,d0
        mov d0,(a1)
        mov a1,(4,a1)
        mov 128,d0
        mov d0,(8,a1)
        mov a1,(556,a3)
        mov a3,a0
        add 544,a0
        mov a0,(80,a1)
        mov a0,(S+72)
        mov 0x314c4d47,d0
        mov d0,(a0)
        mov a0,(4,a0)
        mov 6144,d0
        mov d0,(8,a0)
        /* Publish after the entire owned graph and both guards exist. */
        mov a2,(UI_WORD)
        mov a2,d0
        add 16,d0
        .irp address,0x708f4754,0x708f6294,0x708f63dc,0x708f64f4
        mov d0,(\address)
        .endr
        mov a2,d0
        add 160,d0
        mov d0,(0x708f475c)
        call lut_gm1_core_get,[d2,d3,a2,a3],20
.Lensure_return:
        ret [d2,d3,a2,a3],20
.Lcleanup:
        mov S+40,a0
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lnone
        mov S+40,a0
        mov 8,d1
        clr d0
.Lcleanup_record:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lcleanup_record
        jmp .Lnone

/* Same literal-adapter contract as the earlier UI root, now one retained
 * owner. Any native pre-service caller gets its unchanged original table.
 */
.org 977,0xff
lut_gm1_core_rows:
        movm [other],(sp)
        mov a0,a3
        mov 16,d3
        cmp OLD,a3
        beq .Lrows_known
        mov 160,d3
        cmp OLD+64,a3
        beq .Lrows_known
        bra .Lrows_return
.Lrows_known:
        call lut_gm1_core_ensure,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lrows_return
        add 32,d0
        add d3,d0
        mov d0,a3
.Lrows_return:
        movm (sp),[other]
        mov a3,a0
        ret [d2,d3,a2,a3],20

/* CALLS callback preserves original four-byte frame and MDR on delegation. */
.org 1032,0xff
lut_gm1_core_supported:
        add -12,sp
        mov mdr,d1
        mov d1,(4,sp)
        mov d0,(8,sp)
        cmp 7,d0
        bcs .Lsupported_stock
        cmp 16,d0
        bhi .Lsupported_stock
        call lut_gm1_core_ui,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lunsupported
        movhu (304,a0),d1
        mov (8,sp),d0
        sub 7,d0
        lsr d0,d1
        and 1,d1
        beq .Lunsupported
        clr d0
        bra .Lsupported_delegate
.Lsupported_stock:
        mov (8,sp),d0
.Lsupported_delegate:
        mov (4,sp),d1
        mov d1,mdr
        add 8,sp
        mov 0x700fd4cc,a0
        jmp native_style_supported_continue
.Lunsupported:
        clr d0
        ret [],12
.org 1104,0xff
lut_gm1_core_end:
