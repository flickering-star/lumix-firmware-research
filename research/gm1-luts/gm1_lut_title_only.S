/* Original button/touch routes share this editor entry. Native styles and
 * kind2's internal enums replay their original prefix unchanged. Only LUT
 * tabs use the original native row-state predicate on the actual parameter
 * list: the same eligibility flag used by the native hidden fifth row.
 * No core/settings lookup, polling, per-frame work or opacity operation.
 */
        .text
        .am33_2
        .global lut_gm1_title_only_entry,lut_gm1_title_only_end
        .extern native_row_selectable,native_adjustment_continue

lut_gm1_title_only_entry:
        movm [other],(sp)
        add -24,sp
        mov d0,(4,sp)
        mov d1,(8,sp)
        mov a0,(12,sp)
        mov a1,(16,sp)
        mov psw,d0
        mov d0,(20,sp)
        movbu (0x70101252),d1
        cmp 7,d1
        bcs .Lnative
        cmp 16,d1
        bhi .Lnative
        mov (0x700fcec8),d1
        cmp 2,d1
        beq .Lnative
        mov (4,sp),d0
        extbu d0
        mov (0x708f475c),a0
        call native_row_selectable,[d2,d3],8
        cmp 0,d0
        bne .Lnative
        mov (20,sp),d0
        mov d0,psw
        mov (4,sp),d0
        mov (8,sp),d1
        mov (12,sp),a0
        mov (16,sp),a1
        add 24,sp
        movm (sp),[other]
        ret [],4
.Lnative:
        mov (20,sp),d0
        mov d0,psw
        mov (4,sp),d0
        mov (8,sp),d1
        mov (12,sp),a0
        mov (16,sp),a1
        add 24,sp
        movm (sp),[other]
        extbu d0
        movhu d0,(0x708fc22c)
        jmp native_adjustment_continue
lut_gm1_title_only_end:
