/* Commit a validated native-exported GM1 Library snapshot, CALL F0/20.
 * A0=actual6144B Library; D0status,D1committed sequence/0. No UI/boot hook.
 * Lib+36 is a try gate; +96selected bank0none/1A/2B,+100committed sequence.
 * Uses the real exclusive REGULAR lease at+64, never an arbitrary source.
 * Exports are point-in-time snapshots. This API does not claim the live
 * registry still matches or publish any cell; UI mutation binding is separate.
 * The inactive bank is erased, body verified, then commit written/validated.
 * Equal bodies cause no write. Changed bodies get a nonwrapping fresh sequence.
 */
        .text
        .am33_2
        .global lut_gm1_store_commit,lut_gm1_store_commit_end
        .extern lut_gm1_library_get,lut_import_image_view,native_context
        .extern lut_store_image_check,lut_store_bank_scan,lut_store_crc32
        .extern lut_gm1_nor_erase,lut_gm1_nor_program
        .equ A,0x80880000
        .equ B,0x808a0000
        .equ PADDED,22528
        .equ CONTENT,22264
        .equ MARKER,0x1fc00
        .equ REQUEST,28672

lut_gm1_store_commit:
        add -20,sp
        mov a0,a3
        mov (0x8050),d0
        cmp 0,d0
        bne .Largs
        mov (0x93f00030),d0
        cmp 0x7be2ce04,d0
        bne .Largs
        call native_context,[],0
        extbu d0
        cmp 0,d0
        bne .Largs
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp a3,d0
        bne .Largs
        cmp 0,d0
        beq .Largs
        mov (32,a3),d0
        cmp 0x31545347,d0
        bne .Largs
        mov psw,d2
        and 63487,psw
        mov (36,a3),d0
        cmp 0,d0
        bne .Lbusy
        mov 1,d0
        mov d0,(36,a3)
        mov d2,psw
        mov (40,a3),d0
        cmp 2,d0
        bne .Linvalid
        mov (88,a3),d0
        cmp REQUEST,d0
        bne .Linvalid
        mov a3,a0
        add 64,a0
        call lut_import_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Linvalid
        cmp REQUEST,d1
        bne .Linvalid
        mov d0,a2
        mov d0,a0
        mov 32,d0
        mov 214,d1
        call .Lfilled,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Linvalid
        mov a2,a0
        add REQUEST-32,a0
        mov 32,d0
        mov 214,d1
        call .Lfilled,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Linvalid
        add 32,a2
        mov (56,a3),d0
        cmp a2,d0
        bne .Linvalid
        mov a2,a0
        clr d0
        call lut_store_image_check,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lfinish
        call lut_store_bank_scan,[d2,d3,a2,a3],20
        cmp 0,d0
        blt .Lfinish
        cmp 1,d0
        beq .Lfirst
        mov d1,d3
        mov a0,(4,sp)
        /* Compare all cells and the mask, excluding only header sequence/CRC.
         * The full strict checker has already validated both images. */
        mov d3,a0
        mov (20,a0),d0
        mov (20,a2),d1
        cmp d1,d0
        bne .Lchanged
        mov a2,a0
        add 64,a0
        mov d3,a1
        add 64,a1
        mov CONTENT-64,d0
        call .Lequal,[d2,d3,a2,a3],20
        cmp 1,d0
        beq .Lsame
.Lchanged:
        mov (4,sp),d0
        inc d0
        cmp -1,d0
        beq .Lepoch
        mov (16,a2),d1
        cmp d1,d0
        bcc .Lsequence
        mov d1,d0
.Lsequence:
        mov d0,(16,a2)
        mov d0,(PADDED+8,a2)
        mov a2,a0
        mov 32,d0
        call lut_store_crc32,[d2,d3,a2,a3],20
        mov d0,(32,a2)
        mov d0,(PADDED+12,a2)
        cmp A,d3
        beq .Ltarget_b
.Lfirst:
        mov A,d3
        bra .Lwrite
.Ltarget_b:
        mov B,d3
.Lwrite:
        mov d3,d0
        mov 0x853590,d1
        call lut_gm1_nor_erase,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lerase_error
        mov d3,a0
        mov 0x20000,d0
        mov 255,d1
        call .Lfilled,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lverify_error
        mov a2,d0
        mov d3,d1
        mov PADDED,a0
        mov 440000,a1
        call lut_gm1_nor_program,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lprogram_error
        mov a2,a0
        mov d3,a1
        mov PADDED,d0
        call .Lequal,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lverify_error
        mov a2,d0
        add PADDED,d0
        mov d3,d1
        add MARKER,d1
        mov 1024,a0
        mov 440000,a1
        call lut_gm1_nor_program,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lprogram_error
        mov d3,a0
        mov 1,d0
        call lut_store_image_check,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lverify_error
        mov a2,a0
        mov d3,a1
        mov PADDED,d0
        call .Lequal,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lverify_error
        mov (16,a2),d0
        mov d0,(4,sp)
.Lsame:
        mov 1,d0
        cmp A,d3
        beq .Lrecord
        mov 2,d0
.Lrecord:
        mov d0,(96,a3)
        mov (4,sp),d0
        mov d0,(100,a3)
        mov d0,(8,sp)
        clr d0
        bra .Lfinish
.Lepoch:
        mov -7,d0
        bra .Lfinish
.Lerase_error:
        xor -1,d0
        inc d0
        add -100,d0
        bra .Lfinish
.Lprogram_error:
        xor -1,d0
        inc d0
        add -200,d0
        bra .Lfinish
.Lverify_error:
        mov -20,d0
        bra .Lfinish
.Linvalid:
        mov -18,d0
.Lfinish:
        mov d0,(44,a3)
        mov d0,d2
        mov psw,d3
        and 63487,psw
        clr d0
        mov d0,(36,a3)
        mov d3,psw
        mov d2,d0
        clr d1
        cmp 0,d0
        bne .Lreturn
        mov (8,sp),d1
.Lreturn:
        ret [d2,d3,a2,a3],40
.Lbusy:
        mov d2,psw
        mov -2,d0
        clr d1
        bra .Lreturn
.Largs:
        mov -18,d0
        clr d1
        bra .Lreturn

.Lequal:
        cmp 0,d0
        beq .Lequal_yes
.Lequal_byte:
        movbu (a0),d1
        movbu (a1),d2
        cmp d1,d2
        bne .Lfalse
        inc a0
        inc a1
        sub 1,d0
        bne .Lequal_byte
.Lequal_yes:
        mov 1,d0
        ret [d2,d3,a2,a3],20
.Lfilled:
        cmp 0,d0
        beq .Lequal_yes
.Lfilled_byte:
        movbu (a0),d2
        cmp d1,d2
        bne .Lfalse
        inc a0
        sub 1,d0
        bne .Lfilled_byte
        bra .Lequal_yes
.Lfalse:
        clr d0
        ret [d2,d3,a2,a3],20
lut_gm1_store_commit_end:
