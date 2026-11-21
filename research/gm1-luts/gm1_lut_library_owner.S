/* Persistent RAM metadata for the explicit GM1 Library, CALL F0/20.
 * UI336+332 ->CTRL128+80 owns one6144B native kernel-heap object until reset.
 * No fixed image-buffer address, card access, startup or controller Close hook.
 * get ->D0object/0,D1validated CTRL/0, usable by a read-only renderer.
 * ensure is a normal CPU0 worker operation; it allocates at most once.
 * Object:0GML1,4self,8size,12CTRL owner;32..127menu state,
 * 128..447LDS1,448..967rows,968..3015UTF16 short filenames,
 * 3016..3335cell names,3336..4895list descriptors,4896..6143reserved.
 */
        .text
        .am33_2
        .global lut_gm1_library_get,lut_gm1_library_ensure,lut_gm1_library_owner_end
        .extern lut_gm1_control_ensure,native_context,native_cpu_lock,native_cpu_unlock
        .extern native_heap_allocate
        .equ UI_WORD,0x708f47a4
        .equ HEAP_START,0x7078947c
        .equ HEAP_END,0x708e187c
        .equ BYTES,6144
        .equ MAGIC,0x314c4d47

lut_gm1_library_get:
        mov (UI_WORD),a3
        mov a3,d0
        and 3,d0
        bne .Lbad_ui
        mov a3,d0
        cmp HEAP_START+20,d0
        bcs .Lbad_ui
        cmp HEAP_END-336,d0
        bhi .Lbad_ui
        mov (-4,a3),d0
        cmp 356,d0
        bne .Lbad_ui
        mov (-12,a3),d0
        mov (-8,a3),d1
        or d1,d0
        bne .Lbad_ui
        mov (a3),d0
        cmp 0x3149544c,d0
        bne .Lbad_ui
        mov (4,a3),d0
        cmp a3,d0
        bne .Lbad_ui
        mov (8,a3),d0
        cmp 336,d0
        bne .Lbad_ui
        mov (12,a3),d0
        cmp 288,d0
        bne .Lbad_ui
        mov (332,a3),a1
        mov a1,d0
        and 3,d0
        bne .Lbad_ui
        mov a1,d0
        cmp HEAP_START+20,d0
        bcs .Lbad_ui
        cmp HEAP_END-128,d0
        bhi .Lbad_ui
        mov (-4,a1),d0
        cmp 148,d0
        bne .Lbad_ui
        mov (-12,a1),d0
        mov (-8,a1),d1
        or d1,d0
        bne .Lbad_ui
        mov (a1),d0
        cmp 0x31434d47,d0
        bne .Lbad_ui
        mov (4,a1),d0
        cmp a1,d0
        bne .Lbad_ui
        mov (8,a1),d0
        cmp 128,d0
        bne .Lbad_ui
        mov (80,a1),a2
        mov a2,d0
        and 3,d0
        bne .Lmissing
        mov a2,d0
        cmp HEAP_START+20,d0
        bcs .Lmissing
        cmp HEAP_END-BYTES,d0
        bhi .Lmissing
        mov (-4,a2),d0
        cmp BYTES+20,d0
        bne .Lmissing
        mov (-12,a2),d0
        mov (-8,a2),d1
        or d1,d0
        bne .Lmissing
        mov (a2),d0
        cmp MAGIC,d0
        bne .Lmissing
        mov (4,a2),d0
        cmp a2,d0
        bne .Lmissing
        mov (8,a2),d0
        cmp BYTES,d0
        bne .Lmissing
        mov (12,a2),d0
        cmp a1,d0
        bne .Lmissing
        mov a1,d1
        mov a2,d0
        ret [d2,d3,a2,a3],20
.Lmissing:
        mov a1,d1
        clr d0
        ret [d2,d3,a2,a3],20
.Lbad_ui:
        clr d1
        clr d0
        ret [d2,d3,a2,a3],20

lut_gm1_library_ensure:
        mov (0x8050),d0
        cmp 0,d0
        bne .Lzero
        mov (0x708e91b0),d0
        cmp HEAP_START,d0
        bne .Lzero
        mov (0x93f00030),d0
        cmp 0x7be2ce04,d0
        bne .Lzero
        call native_context,[],0
        extbu d0
        cmp 0,d0
        bne .Lzero
        call lut_gm1_control_ensure,[d2,d3,a2,a3],20
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        cmp 0,d1
        beq .Lzero
        mov d1,a3
        mov (80,a3),d0
        cmp 0,d0
        bne .Lzero
        add -12,sp
        mov sp,a0
        inc4 a0
        call native_cpu_lock,[],0
        mov (80,a3),d0
        cmp 0,d0
        bne .Lunlock
        mov BYTES,d0
        call native_heap_allocate,[d2,d3,a2,a3],16
        cmp 0,a0
        beq .Lunlock
        mov a0,a2
        mov BYTES/4,d1
        clr d0
.Lclear:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lclear
        mov a2,(4,a2)
        mov BYTES,d0
        mov d0,(8,a2)
        mov a3,(12,a2)
        mov MAGIC,d0
        mov d0,(a2)
        /* Publish only after every header and payload byte is initialized. */
        mov a2,(80,a3)
.Lunlock:
        mov (4,sp),d0
        call native_cpu_unlock,[],0
        add 12,sp
        call lut_gm1_library_get,[d2,d3,a2,a3],20
.Lreturn:
        ret [d2,d3,a2,a3],20
.Lzero:
        clr d1
        clr d0
        ret [d2,d3,a2,a3],20
lut_gm1_library_owner_end:
