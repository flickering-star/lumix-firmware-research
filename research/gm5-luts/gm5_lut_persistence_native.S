/* Explicit native LUT persistence v2 component; no UI/boot/SD hook.
 * CALL F0/20: read/export/save(A0=published owned2496B CORE,A1=exclusive
 * LIL1 workspace request/capacity28672). Workspace view+32 contains22528B
 * padded pointer-free content,1024B commit and2284B snapshot scratch.
 * CORE reserved48 is a CPU0 try gate;52 selected bank0none/1A/2B,
 * 56committed generation,60last status. Each API pins the actual CORE owner
 * until after its final access. Binding manager Close/Load/startup is separate.
 * Bank check(D0=0/1) is read-only and accepts no arbitrary address.
 * Save exports the actual registry, then uses original NOR erase/program
 * routines with their own semaphore12 and interrupt-mask handling. It never
 * nests that semaphore. Native errors and old valid bank survive failures.
 */
        .text
        .am33_2
        .global lut_store_read,lut_store_export,lut_store_save,lut_store_bank_check
        .global lut_store_crc32,lut_store_core_close,lut_store_core_enter,lut_store_core_leave
        .global lut_store_image_check,lut_store_session_enter
        .global lut_store_write_owned
        .global lut_store_code_end,lut_store_end
        .extern lut_ram_span,lut_image_view,lut_session_view_shared
        .extern lut_registry_enter,lut_registry_leave,original_snapshot
        .extern native_memcpy,native_erase,native_program
        .extern original_core_close
        .equ BANK_A,0x807a0000
        .equ BANK_B,0x807c0000
        .equ CONTENT,22264
        .equ BODY,22200
        .equ PADDED,22528
        .equ STAGING,23552
        .equ REQUEST,28672
        .equ MARKER,0x1fc00
        .equ OWNER,0x70a0e9a0
        .equ CORE_GLOBAL,0x70a0e9c0

lut_store_read:
        clr d0
        bra .Loperate
lut_store_export:
        mov 2,d0
        bra .Loperate
lut_store_save:
        mov 1,d0
.Loperate:
        mov a0,a3
        mov a1,a2
        mov d0,d2
        add -40,sp
        call .Lenter,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov a0,(4,sp)
        mov d1,a2
        clr d0
        mov d0,(8,sp)
        cmp 0,d2
        beq .Lread
        mov a3,a0
        mov a2,a1
        call .Lexport,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lfinish
        cmp 2,d2
        beq .Lexported
.Lscan_write:
        call .Lscan,[d2,d3,a2,a3],20
        cmp 0,d0
        blt .Lfinish
        cmp 1,d0
        beq .Lfirst
        mov d1,d3
        mov a0,(12,sp)
        mov (16,a2),d0
        mov (12,sp),d1
        cmp d1,d0
        bcs .Lstale
        bne .Lnewer
        mov a2,a0
        mov d3,a1
        mov CONTENT,d0
        call .Lequal,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lstale
        bra .Lcommitted
.Lnewer:
        cmp BANK_A,d3
        beq .Ltarget_b
.Lfirst:
        mov BANK_A,d3
        bra .Lwrite
.Ltarget_b:
        mov BANK_B,d3
.Lwrite:
        /* Original erase: D0destination,D1timeout,F0/24. */
        mov d3,d0
        mov 0x853590,d1
        call native_erase,[d2,d3,a2,a3],24
        cmp 0,d0
        bne .Lerase_failed
        mov d3,a0
        mov 0x20000,d0
        mov 255,d1
        call .Lfilled,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lverify_failed
        /* Original program: D0source,D1destination,A0bytes,A1timeout. */
        mov a2,d0
        mov d3,d1
        mov PADDED,a0
        mov 440000,a1
        call native_program,[d2,d3,a2,a3],36
        cmp 0,d0
        bne .Lprogram_failed
        mov a2,a0
        mov d3,a1
        mov PADDED,d0
        call .Lequal,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lverify_failed
        mov a2,d0
        add PADDED,d0
        mov d3,d1
        add MARKER,d1
        mov 1024,a0
        mov 440000,a1
        call native_program,[d2,d3,a2,a3],36
        cmp 0,d0
        bne .Lprogram_failed
        mov d3,a0
        mov 1,d0
        call .Lvalidate,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lverify_failed
.Lcommitted:
        mov 1,d0
        cmp BANK_A,d3
        beq .Lrecord
        mov 2,d0
.Lrecord:
        mov d0,(52,a3)
        mov (16,a2),d0
        mov d0,(56,a3)
        mov d0,(8,sp)
        clr d0
        bra .Lfinish
.Lexported:
        mov (16,a2),d0
        mov d0,(8,sp)
        clr d0
        bra .Lfinish
.Lstale:
        mov -7,d0
        bra .Lfinish
.Lerase_failed:
        mov d0,(8,sp)
        xor -1,d0
        inc d0
        add -100,d0
        bra .Lfinish
.Lprogram_failed:
        mov d0,(8,sp)
        xor -1,d0
        inc d0
        add -200,d0
        bra .Lfinish
.Lverify_failed:
        mov -20,d0
        bra .Lfinish
.Lread:
        mov a2,a0
        mov STAGING,d0
        clr d1
        call .Lfill,[d2,d3,a2,a3],20
        call .Lscan,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lempty_read
        mov d1,d3
        mov a2,a0
        mov d3,a1
        mov PADDED,d0
        call .Lcopy,[d2,d3,a2,a3],20
        mov a2,a0
        add PADDED,a0
        mov d3,a1
        add MARKER,a1
        mov 1024,d0
        call .Lcopy,[d2,d3,a2,a3],20
        bra .Lcommitted
.Lempty_read:
        mov d0,d3
        clr d0
        mov d0,(52,a3)
        mov d0,(56,a3)
        mov d3,d0
.Lfinish:
        mov d0,d2
        mov d0,(60,a3)
        mov (8,sp),d3
        mov a3,a0
        mov (4,sp),a1
        cmp 0,a1
        beq .Lowned_return
        call lut_store_core_leave,[d2,d3,a2,a3],20
        /* No CORE access after dropping the last possible owner pin. */
.Lowned_return:
        mov d2,d0
        mov d3,d1
.Lreturn:
        ret [d2,d3,a2,a3],60

/* Low-level transaction API F0/20: A0CORE,A1validated exclusive staging BODY.
 * Caller owns the exact workspace and a successful CORE gate/pin. Does not
 * acquire/release that gate or a registry gate. All destinations remain fixed.
 * It validates complete format2 before erase; data is never read from SD here.
 */
lut_store_write_owned:
        mov a0,a3
        mov a1,a2
        add -40,sp
        clr d0
        mov d0,(4,sp)
        mov d0,(8,sp)
        mov (48,a3),d0
        cmp 1,d0
        bne .Lowned_bad
        mov a2,a0
        clr d0
        call lut_store_image_check,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lfinish
        bra .Lscan_write
.Lowned_bad:
        mov -1,d0
        bra .Lfinish

/* Return status/D1workspace/A0actual pinned CORE descriptor. */
.Lenter:
lut_store_session_enter:
        mov a0,a3
        mov a1,a2
        mov (0x8050),d0
        cmp 0,d0
        bne .Largs
        mov (CORE_GLOBAL),d0
        mov a3,d1
        cmp d1,d0
        bne .Largs
        mov a3,d0
        mov 2496,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov (a3),d0
        cmp 0x324c434c,d0
        bne .Largs
        mov (64,a3),d0
        cmp 0x314c524c,d0
        bne .Largs
        mov (4,a3),d0
        cmp 1,d0
        bcs .Largs
        cmp 4,d0
        bhi .Largs
        mov a2,d0
        mov 32,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov (24,a2),d0
        cmp REQUEST,d0
        bne .Largs
        mov (20,a2),d0
        cmp REQUEST,d0
        bne .Largs
        mov a2,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov d0,d3
        mov d0,a0
        mov REQUEST,a1
        mov a3,d0
        mov 2496,d1
        call .Loverlap,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Largs
        mov d3,a0
        mov REQUEST,a1
        mov a2,d0
        mov 32,d1
        call .Loverlap,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Largs
        mov a3,a0
        mov 2496,a1
        mov a2,d0
        mov 32,d1
        call .Loverlap,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Largs
        mov a3,a0
        call .Lcore_enter,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lenter_end
        mov d3,d1
        add 32,d1
.Lenter_end:
        ret [d2,d3,a2,a3],20

/* Close permits retry of a cleanup-needed controller; ordinary storage APIs
 * require a live phase1..4. Pin protects the final gate clear on every path. */
lut_store_core_close:
        mov a0,a3
        mov (CORE_GLOBAL),d0
        mov a0,d1
        cmp d1,d0
        bne .Lclose_generic
        add -8,sp
        call .Lcore_enter,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lclose_return
        mov a0,(4,sp)
        mov a3,a0
        call original_core_close,[d2,d3,a2,a3],20
        mov d0,d2
        mov a3,a0
        mov (4,sp),a1
        call lut_store_core_leave,[d2,d3,a2,a3],20
        mov d2,d0
.Lclose_return:
        ret [d2,d3,a2,a3],28
.Lclose_generic:
        jmp original_core_close

/* Low-level balanced owner APIs, like registry enter/leave. Only a successful
 * enter owner may leave with that exact CORE and returned descriptor pin. */
lut_store_core_enter:
.Lcore_enter:
        mov a0,a3
        mov (0x8050),d0
        cmp 0,d0
        bne .Largs
        mov (CORE_GLOBAL),d0
        mov a3,d1
        cmp d1,d0
        bne .Largs
        mov a3,d0
        mov 2496,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov (a3),d0
        cmp 0x324c434c,d0
        bne .Largs
        mov OWNER,a0
        call lut_session_view_shared,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        add 32,d0
        mov a3,d1
        cmp d1,d0
        bne .Largs
        mov psw,d2
        and 63487,psw
        mov (48,a3),d0
        cmp 0,d0
        bne .Lheld
        mov 1,d0
        mov d0,(48,a3)
        mov d2,psw
        mov (OWNER+8),a0
        mov a0,a2
        mov (a0),a1
        mov (a1),a1
        calls (a1)
        mov a2,a0
        clr d1
        clr d0
        ret [d2,d3,a2,a3],20
.Lheld:
        mov d2,psw
        mov -2,d0
        clr d1
        ret [d2,d3,a2,a3],20
.Largs:
        mov -1,d0
        clr d1
        ret [d2,d3,a2,a3],20

lut_store_core_leave:
        mov a0,a3
        mov a1,a2
        mov psw,d3
        and 63487,psw
        clr d0
        mov d0,(48,a3)
        mov d3,psw
        mov a2,a0
        mov (a0),a1
        mov (4,a1),a1
        calls (a1)
        /* No CORE access after the pin is dropped. */
        ret [d2,d3,a2,a3],20

/* Snapshot under the registry's existing CPU0 gate; release before NOR I/O. */
.Lexport:
        mov a0,a3
        mov a1,a2
        add -24,sp
        add 64,a0
        call lut_registry_enter,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lexport_return
        mov a2,a0
        mov STAGING,d0
        mov 255,d1
        call .Lfill,[d2,d3,a2,a3],20
        mov a2,a0
        mov CONTENT,d0
        clr d1
        call .Lfill,[d2,d3,a2,a3],20
        mov 0x4c354d47,d0
        mov d0,(a2)
        mov 0x00325455,d0
        mov d0,(4,a2)
        mov 2,d0
        mov d0,(8,a2)
        mov 10,d0
        mov d0,(12,a2)
        mov (76,a3),d0
        cmp 0,d0
        beq .Lbad_export
        cmp -1,d0
        beq .Lbad_export
        mov d0,(16,a2)
        mov (72,a3),d0
        cmp 1023,d0
        bhi .Lbad_export
        mov d0,(20,a2)
        mov BODY,d0
        mov d0,(24,a2)
        clr d2
        mov a2,d3
        add 64,d3
.Lexport_cell:
        mov (20,a2),d0
        lsr d2,d0
        btst 1,d0
        beq .Lexport_empty
        mov a3,a0
        add 64,a0
        mov a2,a1
        add STAGING,a1
        mov d2,d0
        call original_snapshot,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lexport_unlock
        mov d1,(4,sp)
        mov d3,a0
        mov 1,d0
        mov d0,(a0)
        mov (4,sp),d0
        mov d0,(8,a0)
        mov d2,d0
        asl 6,d0
        mov a3,a1
        add 128,a1
        add d0,a1
        mov (56,a1),d0
        mov d0,(4,a0)
        add 40,a1
        add 16,a0
        mov 16,d0
        call .Lcopy,[d2,d3,a2,a3],20
        mov d3,a0
        add 32,a0
        mov a2,a1
        add STAGING+96,a1
        mov 2188,d0
        call .Lcopy,[d2,d3,a2,a3],20
        mov d3,a0
        add 32,a0
        mov 2188,d0
        call lut_store_crc32,[d2,d3,a2,a3],20
        mov d3,a0
        mov d0,(12,a0)
        bra .Lexport_next
.Lexport_empty:
        mov d2,d0
        asl 6,d0
        mov a3,a0
        add 128,a0
        add d0,a0
        mov 64,d0
        clr d1
        call .Lfilled,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lbad_export
.Lexport_next:
        add 2220,d3
        inc d2
        cmp 10,d2
        bcs .Lexport_cell
        mov a2,a0
        add 64,a0
        mov BODY,d0
        call lut_store_crc32,[d2,d3,a2,a3],20
        mov d0,(28,a2)
        mov a2,a0
        mov 32,d0
        call lut_store_crc32,[d2,d3,a2,a3],20
        mov d0,(32,a2)
        mov 0x434c3547,d0
        mov d0,(PADDED,a2)
        mov 0x0032544d,d0
        mov d0,(PADDED+4,a2)
        mov (16,a2),d0
        mov d0,(PADDED+8,a2)
        mov (32,a2),d0
        mov d0,(PADDED+12,a2)
        mov a2,a0
        clr d0
        call .Lvalidate,[d2,d3,a2,a3],20
        bra .Lexport_unlock
.Lbad_export:
        mov -18,d0
.Lexport_unlock:
        mov d0,d3
        mov a3,a0
        add 64,a0
        call lut_registry_leave,[d2,d3,a2,a3],20
        mov d3,d0
.Lexport_return:
        ret [d2,d3,a2,a3],44

lut_store_bank_check:
        cmp 0,d0
        beq .Lcheck_a
        cmp 1,d0
        bne .Largs
        mov BANK_B,a0
        bra .Lcheck_known
.Lcheck_a:
        mov BANK_A,a0
.Lcheck_known:
        mov 1,d0
        jmp .Lvalidate

.Lscan:
        add -24,sp
        mov BANK_A,a0
        mov 1,d0
        call .Lvalidate,[d2,d3,a2,a3],20
        mov d0,(4,sp)
        mov d1,(8,sp)
        mov BANK_B,a0
        mov 1,d0
        call .Lvalidate,[d2,d3,a2,a3],20
        mov d0,(12,sp)
        mov d1,(16,sp)
        mov (4,sp),d0
        cmp 0,d0
        bne .Lscan_no_a
        mov (12,sp),d0
        cmp 0,d0
        bne .Lscan_a
        mov (8,sp),d0
        mov (16,sp),d1
        cmp d1,d0
        bhi .Lscan_a
        bcs .Lscan_b
        mov BANK_A,a0
        mov BANK_B,a1
        mov CONTENT,d0
        call .Lequal,[d2,d3,a2,a3],20
        cmp 1,d0
        beq .Lscan_a
        mov -8,d0
        clr d1
        bra .Lscan_end
.Lscan_no_a:
        mov (12,sp),d0
        cmp 0,d0
        beq .Lscan_b
        mov 1,d0
        clr d1
        mov 0,a0
        bra .Lscan_end
.Lscan_a:
        mov BANK_A,d1
        mov (8,sp),a0
        bra .Lscan_ok
.Lscan_b:
        mov BANK_B,d1
        mov (16,sp),a0
.Lscan_ok:
        clr d0
.Lscan_end:
        ret [d2,d3,a2,a3],44

/* A0known image,D0=0staging/1bank. Full strict v2 checker. */
.Lvalidate:
lut_store_image_check:
        mov a0,a3
        add -20,sp
        mov d0,(4,sp)
        mov (a3),d0
        cmp 0x4c354d47,d0
        bne .Linvalid
        mov (4,a3),d0
        cmp 0x00325455,d0
        bne .Linvalid
        mov (8,a3),d0
        cmp 2,d0
        bne .Linvalid
        mov (12,a3),d0
        cmp 10,d0
        bne .Linvalid
        mov (16,a3),d0
        cmp 0,d0
        beq .Linvalid
        cmp -1,d0
        beq .Linvalid
        mov d0,(8,sp)
        mov (20,a3),d0
        cmp 1023,d0
        bhi .Linvalid
        mov d0,(12,sp)
        mov (24,a3),d0
        cmp BODY,d0
        bne .Linvalid
        mov a3,a0
        mov 32,d0
        call lut_store_crc32,[d2,d3,a2,a3],20
        mov (32,a3),d1
        cmp d1,d0
        bne .Linvalid
        mov a3,a0
        add 36,a0
        mov 28,d0
        clr d1
        call .Lfilled,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Linvalid
        mov a3,a0
        add 64,a0
        mov BODY,d0
        call lut_store_crc32,[d2,d3,a2,a3],20
        mov (28,a3),d1
        cmp d1,d0
        bne .Linvalid
        mov PADDED,d2
        mov (4,sp),d0
        cmp 0,d0
        beq .Lcheck_marker
        mov MARKER,d2
.Lcheck_marker:
        mov a3,a2
        add d2,a2
        mov (a2),d0
        cmp 0x434c3547,d0
        bne .Linvalid
        mov (4,a2),d0
        cmp 0x0032544d,d0
        bne .Linvalid
        mov (8,a2),d0
        mov (8,sp),d1
        cmp d1,d0
        bne .Linvalid
        mov (12,a2),d0
        mov (32,a3),d1
        cmp d1,d0
        bne .Linvalid
        mov a3,a0
        add CONTENT,a0
        mov d2,d0
        add -CONTENT,d0
        mov 255,d1
        call .Lfilled,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Linvalid
        mov a2,a0
        add 16,a0
        mov 1008,d0
        mov 255,d1
        call .Lfilled,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Linvalid
        clr d2
        mov a3,d3
        add 64,d3
.Lvalidate_cell:
        mov (12,sp),d0
        lsr d2,d0
        btst 1,d0
        bne .Lvalidate_full
        mov d3,a0
        mov 2220,d0
        clr d1
        call .Lfilled,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Linvalid
        bra .Lvalidate_next
.Lvalidate_full:
        mov d3,a2
        mov (a2),d0
        cmp 1,d0
        bne .Linvalid
        mov (8,a2),d0
        cmp 0,d0
        beq .Linvalid
        mov (8,sp),d1
        cmp d1,d0
        bhi .Linvalid
        mov (4,a2),d0
        mov a2,a0
        add 16,a0
        call .Lname,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Linvalid
        mov a2,a0
        add 32,a0
        mov 2188,d0
        call lut_store_crc32,[d2,d3,a2,a3],20
        mov (12,a2),d1
        cmp d1,d0
        bne .Linvalid
        mov a2,a0
        add 32,a0
        call .Lpayload,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Linvalid
.Lvalidate_next:
        add 2220,d3
        inc d2
        cmp 10,d2
        bcs .Lvalidate_cell
        mov (8,sp),d1
        clr d0
        ret [d2,d3,a2,a3],40
.Linvalid:
        mov -18,d0
        clr d1
        ret [d2,d3,a2,a3],40

.Lname:
        mov a0,a2
        mov d0,d2
        add -24,sp
        cmp 1,d2
        bcs .Lname_bad
        cmp 2,d2
        bhi .Lname_bad
        mov a2,a0
        mov 16,d3
.Lname_zero:
        movbu (a0),d0
        inc a0
        sub 1,d3
        cmp 0,d0
        beq .Lname_tail
        cmp 0,d3
        bne .Lname_zero
        bra .Lname_bad
.Lname_tail:
        cmp 0,d3
        beq .Lname_path
        movbu (a0),d0
        cmp 0,d0
        bne .Lname_bad
        inc a0
        sub 1,d3
        bra .Lname_tail
.Lname_path:
        /* Persisted names are data, never paths to reopen. The active SD
         * alias validator accepts .CUB while display names may retain .CUBE.
         * Validate both bounded forms here without depending on that mutable
         * import entry, ordinary-RAM path restrictions, or any filesystem API.
         * The complete16-byte field was already checked for zero padding. */
        mov a2,a0
        clr d3
.Lname_stem:
        movbu (a0),d0
        cmp 46,d0
        beq .Lname_extension
        cmp 8,d3
        bcc .Lname_bad
        cmp 95,d0
        beq .Lname_stem_next
        cmp 126,d0
        beq .Lname_stem_next
        cmp 48,d0
        bcs .Lname_bad
        cmp 57,d0
        bls .Lname_stem_next
        or 32,d0
        cmp 97,d0
        bcs .Lname_bad
        cmp 122,d0
        bhi .Lname_bad
.Lname_stem_next:
        inc d3
        inc a0
        bra .Lname_stem
.Lname_extension:
        cmp 0,d3
        beq .Lname_bad
        movbu (1,a0),d0
        or 32,d0
        cmp 118,d0
        beq .Lname_vlt
        cmp 99,d0
        bne .Lname_bad
        movbu (2,a0),d0
        or 32,d0
        cmp 117,d0
        bne .Lname_bad
        movbu (3,a0),d0
        or 32,d0
        cmp 98,d0
        bne .Lname_bad
        movbu (4,a0),d0
        cmp 0,d0
        beq .Lname_cube_kind
        or 32,d0
        cmp 101,d0
        bne .Lname_bad
        movbu (5,a0),d0
        cmp 0,d0
        bne .Lname_bad
.Lname_cube_kind:
        mov 2,d1
        bra .Lname_kind
.Lname_vlt:
        movbu (2,a0),d0
        or 32,d0
        cmp 108,d0
        bne .Lname_bad
        movbu (3,a0),d0
        or 32,d0
        cmp 116,d0
        bne .Lname_bad
        movbu (4,a0),d0
        cmp 0,d0
        bne .Lname_bad
        mov 1,d1
.Lname_kind:
        cmp d2,d1
        bne .Lname_bad
        clr d0
        ret [d2,d3,a2,a3],44
.Lname_bad:
        mov -18,d0
        ret [d2,d3,a2,a3],44

.Lpayload:
        mov a0,a2
        mov .Lcounts,a3
        mov 8,d3
.Lpayload_bank:
        movhu (a3),d2
.Lpayload_y:
        movbu (a2),d0
        cmp 63,d0
        bhi .Lpayload_bad
        inc a2
        sub 1,d2
        bne .Lpayload_y
        movhu (a3),d2
        btst 1,d2
        beq .Lpayload_pairs
        movbu (a2),d0
        cmp 0,d0
        bne .Lpayload_bad
        inc a2
.Lpayload_pairs:
        movhu (a2),d0
        cmp 4095,d0
        bhi .Lpayload_bad
        add 2,a2
        sub 1,d2
        bne .Lpayload_pairs
        add 2,a3
        sub 1,d3
        bne .Lpayload_bank
        clr d0
        ret [d2,d3,a2,a3],20
.Lpayload_bad:
        mov -18,d0
        ret [d2,d3,a2,a3],20

lut_store_crc32:
        mov a0,a2
        mov d0,d2
        mov -1,d3
        cmp 0,d2
        beq .Lcrc_end
.Lcrc_byte:
        movbu (a2),d0
        xor d0,d3
        mov 8,d0
.Lcrc_bit:
        mov d3,d1
        and 1,d1
        lsr 1,d3
        cmp 0,d1
        beq .Lcrc_next_bit
        xor 0xedb88320,d3
.Lcrc_next_bit:
        sub 1,d0
        bne .Lcrc_bit
        inc a2
        sub 1,d2
        bne .Lcrc_byte
.Lcrc_end:
        xor -1,d3
        mov d3,d0
        ret [d2,d3,a2,a3],20

.Lcopy:
        call native_memcpy,[a2,a3],8
        ret [d2,d3,a2,a3],20
.Lfill:
        cmp 0,d0
        beq .Lfill_end
.Lfill_byte:
        movbu d1,(a0)
        inc a0
        sub 1,d0
        bne .Lfill_byte
.Lfill_end:
        ret [d2,d3,a2,a3],20
.Lfilled:
        cmp 0,d0
        beq .Lfilled_yes
        mov d0,d2
.Lfilled_byte:
        movbu (a0),d0
        cmp d1,d0
        bne .Lfilled_no
        inc a0
        sub 1,d2
        bne .Lfilled_byte
.Lfilled_yes:
        mov 1,d0
        ret [d2,d3,a2,a3],20
.Lfilled_no:
        clr d0
        ret [d2,d3,a2,a3],20
.Lequal:
        mov d0,d2
        cmp 0,d2
        beq .Lfilled_yes
.Lequal_byte:
        movbu (a0),d0
        movbu (a1),d1
        cmp d1,d0
        bne .Lfilled_no
        inc a0
        inc a1
        sub 1,d2
        bne .Lequal_byte
        bra .Lfilled_yes
.Loverlap:
        mov d0,d2
        add d1,d0
        mov a0,d1
        cmp d0,d1
        bcc .Lfilled_no
        add a1,d1
        cmp d1,d2
        bcc .Lfilled_no
        bra .Lfilled_yes
lut_store_code_end:
        .balign 2
.Lcounts:
        .hword 125,100,100,80,100,80,80,64
lut_store_end:
