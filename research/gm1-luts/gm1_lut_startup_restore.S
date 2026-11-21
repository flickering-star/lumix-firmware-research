/* GM1 adapter to the shared GM5 post-UI startup restoration shim.
 * This direct F0/20 helper initializes only the dormant Library header and
 * supplies the native persisted choice to the same restore owner as the menu.
 * No SD scan/file parser, flash writer, native worker/pool initializer here.
 */
        .global lut_gm1_startup_ensure,lut_gm1_startup_restore_end
        .extern lut_gm1_restore_runtime,native_alternate_style
        .equ S,0x708f52c8
lut_gm1_startup_ensure:
        mov (S),d0
        cmp 0x31534d4c,d0
        beq .Lrestore
        mov S,a0
        mov 24,d1
.Lfresh:
        mov (a0),d0
        cmp 0,d0
        bne .Lbad
        inc4 a0
        sub 1,d1
        bne .Lfresh
        mov 0x31534d4c,d0
        mov d0,(S)
.Lrestore:
        mov (S+4),d0
        cmp 0,d0
        bne .Lbad
        /* These are the same source fields/predicate as the original saved
         * style loader at4021b338. Read before temporary Standard changes
         * its persistent mirror; restore publication precedes custom select. */
        movbu (0x70101224),d0
        call native_alternate_style,[],0
        extbu d0
        cmp 0,d0
        beq .Lnormal
        movbu (0x7000d77c),d0
        bra .Lrun
.Lnormal:
        movbu (0x7000d5a2),d0
.Lrun:
        jmp lut_gm1_restore_runtime
.Lbad:
        mov -18,d0
        clr d1
        ret [d2,d3,a2,a3],20
lut_gm1_startup_restore_end:
