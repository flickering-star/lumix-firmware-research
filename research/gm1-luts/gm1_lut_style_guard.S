/* GM1 selected custom-style availability and native override isolation.
 * normalize(D0style) CALL F0/20 -> originalD0 or Standard0. Pure reads;
 * no allocation, native context/kernel call, file, flash or startup hook.
 * Kind2 at native descriptor700fcec8 owns internal override parameters.
 * Preserve that kind even when its numeric style overlaps custom IDs7..16.
 */
        .text
        .am33_2
        .global lut_gm1_style_normalize,lut_gm1_style_setter,lut_gm1_style_restore
        .global lut_gm1_style_effective
        .global lut_gm1_ui_values,lut_gm1_ui_values_end
        .global lut_gm1_style_guard_end
        .extern native_mode_descriptor,native_setter_continue,native_restore_continue
        .extern native_effective_continue,native_values_continue

.org 0,0xff
lut_gm1_style_normalize:
        mov d0,d3
        mov d0,d2
        extbu d2
        cmp 7,d2
        bcs .Lkeep
        cmp 16,d2
        bhi .Lkeep
        mov (0x700fcec8),d1
        cmp 2,d1
        beq .Lkeep
        call lut_gm1_core_ui,[d2,d3,a2,a3],20
        cmp 0,a0
        beq .Lmissing
        movhu (304,a0),d1
        sub 7,d2
        lsr d2,d1
        and 1,d1
        beq .Lmissing
.Lkeep:
        mov d3,d0
        ret [d2,d3,a2,a3],20
.Lmissing:
        clr d0
        ret [d2,d3,a2,a3],20

/* Preserve all original volatile/loop/MDR/PSW state except normalized D0.
 * The original public setter's C0/12 frame remains on entry. */
.org 57,0xff
lut_gm1_style_setter:
        movm [other],(sp)
        add -8,sp
        mov psw,d1
        mov d1,(4,sp)
        call lut_gm1_style_normalize,[d2,d3,a2,a3],20
        mov d0,(36,sp)
        mov (4,sp),d1
        mov d1,psw
        add 8,sp
        movm (sp),[other]
        mov d0,d3
        movbu d3,(0x70102b4e)
        jmp native_setter_continue

/* Saved-choice resolver C0/12. Replay first two MOVs and original context
 * accessor, then its untouched body. Only the returned choice is normalized. */
.org 94,0xff
lut_gm1_style_restore:
        call .Lrestore_replay,[d2,d3],12
        movm [other],(sp)
        add -8,sp
        mov psw,d1
        mov d1,(4,sp)
        call lut_gm1_style_normalize,[d2,d3,a2,a3],20
        mov d0,(36,sp)
        mov (4,sp),d1
        mov d1,psw
        add 8,sp
        movm (sp),[other]
        ret [d2,d3],12
.Lrestore_replay:
        mov d0,d2
        mov d1,d3
        call native_mode_descriptor,[],0
        jmp native_restore_continue

/* Internal IDs stay native unless they refer to the actual UI selection. */
.org 141,0xff
lut_gm1_style_effective:
        movm [other],(sp)
        add -8,sp
        mov psw,d1
        mov d1,(4,sp)
        mov d0,d1
        extbu d1
        movbu (0x70101252),d0
        cmp d1,d0
        bne .Leffective_keep
        mov (36,sp),d0
        call lut_gm1_style_normalize,[d2,d3,a2,a3],20
        mov d0,(36,sp)
.Leffective_keep:
        mov (4,sp),d1
        mov d1,psw
        add 8,sp
        movm (sp),[other]
        mov d0,d2
        call native_mode_descriptor,[],0
        /* The normal branch can return without another call. Recreate the
         * original accessor's MDR link before entering its old continuation. */
        mov native_effective_continue,d0
        mov d0,mdr
        mov d2,d0
        jmp native_effective_continue

/* Replacement E0/16 getter. Loaded matching normal LUTs get neutral values;
 * unavailable matching selections use original Standard parameters. Kind2,
 * unrelated internal IDs and all stock cases keep the original getter. */
.org 286,0xff
lut_gm1_ui_values:
        jmp lut_gm1_parity_values
.org 291,0xff
lut_gm1_ui_values_end:
.org 291,0xff
lut_gm1_style_guard_end:

.extern lut_gm1_core_ui,lut_gm1_parity_values
