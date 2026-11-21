/* Read committed storage into an EMPTY ready GM1 registry, F0/20 A0Library.
 * D0status(1no valid bank),D1loaded mask/0. Standard stays selected.
 * Common owner/workspace helpers are linked verbatim from the export source;
 * the descriptor builder is reused verbatim from working GM5 restore code.
 * All new exclusive table leases precede one gated publication of the mask.
 * Candidate leases640B, UTF16 names320B and GMR1state64B live AFTER the23552B
 * image inside the same owned28672B workspace. No pointer comes from flash.
 * Lib+104=0idle/1preparing/2cleanup pending/3restored. If cleanup returns-15,
 * the logical store gate remains owned; Export/Commit/Release refuse entry.
 * Only explicit Restore Cleanup may retry it. No kernel lock remains held.
 * No SD, NOR write, menu, startup or full-device restore caller is connected.
 */
        .global lut_gm1_store_restore,lut_gm1_store_restore_cleanup
        .global lut_gm1_restore_prepared,lut_gm1_store_restore_end
        .extern lut_gm1_store_capture_enter,lut_gm1_store_capture_leave
        .extern lut_store_bank_scan,lut_store_image_check,lut_convert_banks
        .extern lut_image_lease_open,lut_image_lease_close,lut_image_view
        .extern lut_gm1_record_check_table,native_memcpy
        .equ CANDIDATE,23552
        .equ NAMES,24192
        .equ RSTATE,24512

lut_gm1_store_restore:
        add -40,sp
        mov a0,a3
        clr d0
        mov d0,(4,sp)
        mov d0,(8,sp)
        call .Lenter,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rreturn
        mov (104,a3),d0
        cmp 2,d0
        beq .Rinvalid
        call .Lworkspace,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rfinish
        mov d1,a2
        mov (12,a3),a0
        mov a0,(12,sp)
        call .Rempty,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rfinish
        call lut_store_bank_scan,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rfinish
        mov d1,(16,sp)
        mov a0,(20,sp)
        mov d1,a1
        mov a2,a0
        mov PADDED,d0
        call native_memcpy,[a2,a3],8
        mov a2,a0
        add PADDED,a0
        mov (16,sp),a1
        add 0x1fc00,a1
        mov 1024,d0
        call native_memcpy,[a2,a3],8
        mov a2,a0
        clr d0
        call lut_store_image_check,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rfinish
        mov a2,a0
        add CANDIDATE,a0
        mov 1024,d0
        call .Rzero,[d2,d3,a2,a3],20
        mov 0x31524d47,d0
        mov d0,(RSTATE,a2)
        mov a3,(RSTATE+4,a2)
        mov 1,d0
        mov d0,(104,a3)
        clr d2
.Rcell:
        mov (20,a2),d0
        lsr d2,d0
        and 1,d0
        beq .Rnext
        mov d2,d0
        asl 6,d0
        mov a2,d3
        add CANDIDATE,d3
        add d0,d3
        mov d3,a0
        mov 2348,d0
        call lut_image_lease_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rprepare_failed
        mov d3,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Rbad_view
        cmp 2348,d1
        bcs .Rbad_view
        mov d0,(24,sp)
        mov d3,a0
        mov d0,(32,a0)
        mov d2,d0
        mov 2220,d1
        mul d1,d0
        mov a2,a0
        add 64,a0
        add d0,a0
        mov a0,(28,sp)
        mov (24,sp),a0
        call .Ldescriptors,[d2,d3,a2,a3],20
        mov (24,sp),a0
        add 96,a0
        mov (28,sp),a1
        add 32,a1
        mov 2188,d0
        call native_memcpy,[a2,a3],8
        mov (24,sp),a0
        add 2284,a0
        mov 64,d0
        mov 214,d1
        call .Lfill,[d2,d3,a2,a3],20
        mov (24,sp),a0
        call lut_gm1_record_check_table,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rprepare_failed
        mov (28,sp),a1
        mov (8,a1),d0
        mov d3,a0
        mov d0,(36,a0)
        mov 1,d0
        mov d0,(60,a0)
        mov d2,d0
        asl 5,d0
        mov a2,a0
        add NAMES,a0
        add d0,a0
        add 16,a1
        mov 16,d1
.Rname:
        movbu (a1),d0
        movhu d0,(a0)
        inc a1
        add 2,a0
        sub 1,d1
        bne .Rname
.Rnext:
        inc d2
        cmp 10,d2
        bcs .Rcell
lut_gm1_restore_prepared:
        mov a3,a0
        call lut_gm1_store_capture_enter,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rprepare_failed
        mov d1,(4,sp)
        mov 1,d0
        mov d0,(8,sp)
        call .Rempty,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rprepare_failed
        mov (4,sp),a0
        add 1792,a0
        mov a2,a1
        add CANDIDATE,a1
        mov 640,d0
        call native_memcpy,[a2,a3],8
        mov a3,a0
        add 3016,a0
        mov a2,a1
        add NAMES,a1
        mov 320,d0
        call native_memcpy,[a2,a3],8
        /* Exact native leases are moved, then the candidate copies zeroed.
         * No allocation or fallible operation occurs before mask publication. */
        mov a2,a0
        add CANDIDATE,a0
        mov 640,d0
        call .Rzero,[d2,d3,a2,a3],20
        mov (12,sp),a0
        mov (72,a0),d1
        mov (20,sp),d0
        cmp d1,d0
        bcc .Repoch
        mov d1,d0
.Repoch:
        mov d0,(72,a0)
        mov psw,d3
        and 63487,psw
        mov (0x708f47a4),a0
        mov (20,a2),d1
        movhu d1,(304,a0)
        mov d3,psw
        mov d1,(32,sp)
        mov 3,d0
        mov d0,(104,a3)
        mov (16,sp),d0
        mov 1,d1
        cmp 0x80880000,d0
        beq .Rbank
        mov 2,d1
.Rbank:
        mov d1,(96,a3)
        mov (20,sp),d0
        mov d0,(100,a3)
        mov d0,(48,a3)
        mov (20,a2),d0
        mov d0,(52,a3)
        mov 2,d0
        mov d0,(40,a3)
        mov a3,a0
        call lut_gm1_store_capture_leave,[d2,d3,a2,a3],20
        clr d1
        mov d1,(8,sp)
        bra .Rfinish
.Rbad_view:
        mov -18,d0
.Rprepare_failed:
        mov d0,(RSTATE+8,a2)
        mov (8,sp),d0
        cmp 0,d0
        beq .Rrelease_candidates
        mov a3,a0
        call lut_gm1_store_capture_leave,[d2,d3,a2,a3],20
        clr d0
        mov d0,(8,sp)
.Rrelease_candidates:
        call .Rrelease,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rpending
        mov (RSTATE+8,a2),d0
        bra .Rfinish
.Rpending:
        mov 2,d0
        mov d0,(104,a3)
        mov -15,d0
        mov d0,(44,a3)
        clr d1
        ret [d2,d3,a2,a3],60
.Rinvalid:
        mov -18,d0
.Rfinish:
        mov d0,(36,sp)
        mov d0,(44,a3)
        call .Lleave,[d2,d3,a2,a3],20
        mov (36,sp),d0
.Rreturn:
        clr d1
        cmp 0,d0
        bne .Rdone
        mov (32,sp),d1
.Rdone:
        ret [d2,d3,a2,a3],60

/* Normal worker only. Capture gate is checked/claimed by the caller when
 * publishing; preflight is read-only and repeated after that actual claim. */
.Rempty:
        mov (0x708f47a4),a0
        movhu (304,a0),d0
        movbu (0x70101252),d1
        or d1,d0
        cmp 0,d0
        bne .Rnot_empty
        mov (12,a3),a0
        mov (12,a0),d0
        cmp 2,d0
        bne .Rnot_empty
        mov (20,a0),d0
        mov (68,a0),d1
        or d1,d0
        cmp 0,d0
        bne .Rnot_empty
        mov (64,a0),d0
        cmp 13,d0
        bne .Rnot_empty
        add 32,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Rnot_empty
        cmp 3072,d1
        bne .Rnot_empty
        mov (12,a3),a0
        mov (16,a0),d1
        cmp d1,d0
        bne .Rnot_empty
        mov d0,a0
        mov (32,a0),d0
        cmp 0x31504647,d0
        bne .Rnot_empty
        mov (36,a0),d0
        mov (12,a3),d1
        cmp d1,d0
        bne .Rnot_empty
        add 1792,a0
        mov 160,d1
.Rempty_cell:
        mov (a0),d0
        cmp 0,d0
        bne .Rnot_empty
        inc4 a0
        sub 1,d1
        bne .Rempty_cell
        clr d0
        ret [d2,d3,a2,a3],20
.Rnot_empty:
        mov -2,d0
        ret [d2,d3,a2,a3],20

.Rrelease:
        clr d2
.Rrelease_cell:
        mov d2,d0
        asl 6,d0
        mov a2,d3
        add CANDIDATE,d3
        add d0,d3
        mov d3,a0
        mov (a0),d0
        cmp 0,d0
        beq .Rrelease_next
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rrelease_return
        mov d3,a0
        mov 64,d0
        call .Rzero,[d2,d3,a2,a3],20
.Rrelease_next:
        inc d2
        cmp 10,d2
        bcs .Rrelease_cell
        clr d0
        mov d0,(104,a3)
.Rrelease_return:
        ret [d2,d3,a2,a3],20

lut_gm1_store_restore_cleanup:
        add -40,sp
        mov a0,a3
        clr d0
        mov d0,(32,sp)
        call .Lowner,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rreturn
        mov (32,a3),d0
        cmp 0x31545347,d0
        bne .Rcleanup_bad
        mov (36,a3),d0
        cmp 1,d0
        bne .Rcleanup_bad
        mov (104,a3),d0
        cmp 2,d0
        bne .Rcleanup_bad
        call .Lworkspace,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rpending
        mov d1,a2
        mov (RSTATE,a2),d0
        cmp 0x31524d47,d0
        bne .Rpending
        mov (RSTATE+4,a2),d0
        cmp a3,d0
        bne .Rpending
        call .Rrelease,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Rpending
        bra .Rfinish
.Rcleanup_bad:
        mov -18,d0
        bra .Rreturn
.Rzero:
        clr d1
        call .Lfill,[d2,d3,a2,a3],20
        ret [d2,d3,a2,a3],20
