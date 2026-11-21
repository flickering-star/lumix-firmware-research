/* The original constructor may produce a valid native table before the LUT
 * tail runs. Accept exactly the original catalog's modes0/5/7/15 and its two
 * valid parent flags. Every ownership/channel/key/token guard stays in place.
 * JMP adapters use no stack, RAM write, call, allocator or device operation.
 */
        .text
        .am33_2
        .global lut_gm1_native_parent_mode,lut_gm1_native_parent_flags
        .global lut_gm1_native_parent_end
        .extern parent_mode_continue,parent_flags_continue,parent_reject
lut_gm1_native_parent_mode:
        movbu (2728,a2),d0
        cmp 0,d0
        beq .Lmode_ok
        cmp 5,d0
        beq .Lmode_ok
        cmp 7,d0
        beq .Lmode_ok
        cmp 15,d0
        beq .Lmode_ok
        jmp parent_reject
.Lmode_ok:
        jmp parent_mode_continue
lut_gm1_native_parent_flags:
        movhu (2700,a2),d0
        cmp 128,d0
        beq .Lflags_ok
        cmp 131,d0
        beq .Lflags_ok
        jmp parent_reject
.Lflags_ok:
        jmp parent_flags_continue
lut_gm1_native_parent_end:
