/* Private Library bind adapter. Native Setup's touch plane retains its
 * former child list unless explicitly rebound, independently of list drawing.
 * Use the stock child-pointer setter for row targets100e/100f at every Library
 * phase transition; restore the parent's list before its original exit code.
 * No coordinate constants, renderer replacement, allocation or startup hook.
 */
        .text
        .am33_2
        .global lut_touch_rows_bind,lut_touch_rows_restore_parent
        .global lut_touch_rows_end
        .extern native_list_bind,native_child_bind,previous_parent_restore
        .equ S,0x70a0e978
        .equ PLANE,0x70a12cb8

lut_touch_rows_bind:
        add -20,sp
        call native_list_bind,[d2,a2],12
        mov d0,(4,sp)
        mov d1,(8,sp)
        mov a0,(12,sp)
        mov a1,(16,sp)
        mov (S),d0
        cmp 0x31534d4c,d0
        bne .Lreturn
        mov (0x701aeec8),a1
        call .Lchildren,[d2,d3,a2,a3],20
.Lreturn:
        mov (4,sp),d0
        mov (8,sp),d1
        mov (12,sp),a0
        mov (16,sp),a1
        ret [d2,a2],32

lut_touch_rows_restore_parent:
        mov (S+20),a1
        call .Lchildren,[d2,d3,a2,a3],20
        jmp previous_parent_restore

.Lchildren:
        cmp 0,a1
        beq .Ldone
        mov a1,a3
        mov PLANE,a0
        mov 0x100e,d0
        call native_child_bind,[d2,a2],8
        mov PLANE,a0
        mov a3,a1
        mov 0x100f,d0
        call native_child_bind,[d2,a2],8
.Ldone:
        ret [d2,d3,a2,a3],20
lut_touch_rows_end:
