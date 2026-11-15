/* Internal-bank restore into a fresh published Library session. F0/20,
 * A0CORE,A1exclusive28672B workspace. No boot/UI/SD hook. Calls original
 * native store Read, then reconstructs ten independent allocator-owned tables.
 * Only fresh idle registry(gen1,mask0), Standard selected, UI mask0 accepted.
 * Candidate1024 at workspaceBody+25836; UTF16names320 at+26860;
 * LRS1state64 at+27180. No runtime pointers are accepted from durable data.
 * All tables and a complete frame pool precede last mask publication. Pending
 * leases remain in the caller-owned workspace if cleanup needs retry(-15);
 * caller MUST retain workspace and CORE until cleanup succeeds. Cleanup API
 * uses the same arguments. It never erases flash or reads the SD card.
 */
        .text
        .am33_2
        .global lut_restore_run,lut_restore_cleanup,lut_restore_code_end,lut_restore_end
        .global lut_restore_prepare_failed
        .extern lut_store_read,lut_store_session_enter,lut_store_core_leave
        .extern lut_store_image_check,lut_registry_enter,lut_registry_leave
        .extern lut_image_lease_open,lut_image_lease_close,lut_image_view
        .extern lut_frame_pool_open,lut_queue_close_guard,lut_runtime_check_table
        .extern native_memcpy,lut_convert_banks
        .equ CANDIDATE,25836
        .equ NAMES,26860
        .equ STATE,27180
        .equ OWNER,0x70a0e9a0

lut_restore_run:
        mov a0,a3
        mov a1,a2
        add -40,sp
        call lut_store_read,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        clr d2
        bra .Lbegin
lut_restore_cleanup:
        mov a0,a3
        mov a1,a2
        add -40,sp
        mov 1,d2
.Lbegin:
        mov a3,a0
        mov a2,a1
        call lut_store_session_enter,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov a0,(4,sp)
        mov d1,a2
        clr d0
        mov d0,(8,sp)
        mov d0,(12,sp)
        mov a3,a0
        add 64,a0
        call lut_registry_enter,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lfinish
        mov 1,d0
        mov d0,(8,sp)
        cmp 0,d2
        bne .Lcleanup_entry
        mov (4,a3),d0
        cmp 1,d0
        bne .Lbusy
        movbu (0x701ad636),d0
        cmp 0,d0
        bne .Lbusy
        movhu (0x70a0dec0),d0
        cmp 0,d0
        bne .Lbusy
        mov (68,a3),d0
        cmp 0,d0
        bne .Lbusy
        mov (72,a3),d0
        cmp 0,d0
        bne .Lbusy
        mov (76,a3),d0
        cmp 1,d0
        bne .Lbusy
        mov (36,a3),d0
        cmp 0,d0
        bne .Lbusy
        mov (1796,a3),d0
        cmp 0,d0
        bne .Lbusy
        mov (1864,a3),d0
        cmp 0,d0
        bne .Lbusy
        mov a3,a0
        add 128,a0
        mov 960,d0
        call .Lzeroed,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lbusy
        mov a2,a0
        add STATE,a0
        mov (a0),d0
        cmp 0,d0
        beq .Lstate_fresh
        cmp 0x3153524c,d0
        bne .Largs
        mov (4,a0),d0
        cmp 4,d0
        bne .Lretry_required
        mov (8,a0),d0
        mov a3,d1
        cmp d1,d0
        bne .Largs
.Lstate_fresh:
        mov a2,a0
        clr d0
        call lut_store_image_check,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lfinish
        mov a2,a0
        add CANDIDATE,a0
        mov 1408,d0
        call .Lzero,[d2,d3,a2,a3],20
        mov 0x3153524c,d0
        mov d0,(STATE,a2)
        mov 1,d0
        mov d0,(STATE+4,a2)
        mov a3,(STATE+8,a2)
        mov (16,a2),d0
        mov d0,(STATE+12,a2)
        mov (2460,a3),d0
        mov d0,(STATE+28,a2)
        mov 0x314c524c,d0
        mov d0,(CANDIDATE,a2)
        mov (16,a2),d0
        mov d0,(CANDIDATE+12,a2)
        clr d2
.Lcell:
        mov (20,a2),d0
        lsr d2,d0
        btst 1,d0
        beq .Lnext
        mov d2,d0
        asl 6,d0
        mov a2,d3
        add CANDIDATE+64,d3
        add d0,d3
        mov d3,a0
        mov 2348,d0
        call lut_image_lease_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lprepare_failed
        mov d3,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbad_view
        add 32,d0
        mov d0,(16,sp)
        mov d3,a0
        mov d0,(32,a0)
        mov d2,d0
        /* Same stock register multiply as durable cell-address preparation.
         * Retain the original six-byte extent and every symbol address. */
        mov 2220,d1
        mul d1,d0
        nop
        add 64,d0
        add a2,d0
        mov d0,(20,sp)
        mov (16,sp),a0
        call .Ldescriptors,[d2,d3,a2,a3],20
        mov (16,sp),a0
        add 96,a0
        mov (20,sp),a1
        add 32,a1
        mov 2188,d0
        call .Lcopy,[d2,d3,a2,a3],20
        mov (16,sp),a0
        call lut_runtime_check_table,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lprepare_failed
        mov d3,a0
        mov (20,sp),a1
        mov (8,a1),d0
        mov d0,(36,a0)
        mov (4,a1),d0
        mov d0,(56,a0)
        mov 1,d0
        mov d0,(60,a0)
        add 40,a0
        add 16,a1
        mov 16,d0
        call .Lcopy,[d2,d3,a2,a3],20
        mov d2,d0
        asl 5,d0
        mov a2,a0
        add NAMES,a0
        add d0,a0
        mov d3,a1
        add 40,a1
        mov 16,d1
.Lname:
        movbu (a1),d0
        movhu d0,(a0)
        inc a1
        add 2,a0
        sub 1,d1
        bne .Lname
        mov (STATE+32,a2),d0
        inc d0
        mov d0,(STATE+32,a2)
.Lnext:
        inc d2
        cmp 10,d2
        bcs .Lcell
        mov a3,a0
        mov OWNER,a1
        call lut_frame_pool_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lprepare_failed
        /* Native copies cannot fail after validated disjoint owned extents.
         * Registry readers are gated and global style mask stays0 until last. */
        mov a3,a0
        add 128,a0
        mov a2,a1
        add CANDIDATE+64,a1
        mov 640,d0
        call .Lcopy,[d2,d3,a2,a3],20
        mov a3,a0
        add 1440,a0
        mov a2,a1
        add NAMES,a1
        mov 320,d0
        call .Lcopy,[d2,d3,a2,a3],20
        /* Move ownership: never release candidate leases after this point. */
        mov a2,a0
        add CANDIDATE,a0
        mov 1344,d0
        call .Lzero,[d2,d3,a2,a3],20
        mov (16,a2),d0
        mov d0,(76,a3)
        mov (20,a2),d1
        mov psw,d3
        and 63487,psw
        mov d1,(72,a3)
        movhu d1,(0x70a0dec0)
        mov 3,d0
        mov d0,(STATE+4,a2)
        mov d3,psw
        mov d1,(12,sp)
        clr d0
        bra .Lfinish
.Lbad_view:
        mov -18,d0
.Lprepare_failed:
lut_restore_prepare_failed:
        mov d0,(STATE+16,a2)
        mov 2,d0
        mov d0,(STATE+4,a2)
        call .Lrelease,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lretry_required
        mov (STATE+16,a2),d0
        bra .Lfinish
.Lcleanup_entry:
        mov (STATE,a2),d0
        cmp 0x3153524c,d0
        bne .Largs
        mov (STATE+8,a2),d0
        mov a3,d1
        cmp d1,d0
        bne .Largs
        mov (STATE+4,a2),d0
        cmp 2,d0
        bne .Largs
        mov (72,a3),d0
        cmp 0,d0
        bne .Lbusy
        call .Lrelease,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lretry_required
        mov 1,d0
        mov d0,(4,a3)
        clr d0
        bra .Lfinish
.Lretry_required:
        mov -15,d0
        bra .Lfinish
.Lbusy:
        mov -2,d0
        bra .Lfinish
.Largs:
        mov -1,d0
.Lfinish:
        mov d0,d2
        mov d0,(60,a3)
        mov (8,sp),d0
        cmp 0,d0
        beq .Ldrop_pin
        mov a3,a0
        add 64,a0
        call lut_registry_leave,[d2,d3,a2,a3],20
.Ldrop_pin:
        mov a3,a0
        mov (4,sp),a1
        call lut_store_core_leave,[d2,d3,a2,a3],20
        mov d2,d0
        mov (12,sp),d1
.Lreturn:
        ret [d2,d3,a2,a3],60

/* Pending allocations are caller-owned until publication or complete cleanup.
 * A failed release retains the exact lease record and primary error for retry. */
.Lrelease:
        clr d2
.Lrelease_cell:
        mov d2,d0
        asl 6,d0
        mov a2,d3
        add CANDIDATE+64,d3
        add d0,d3
        mov d3,a0
        mov (a0),d0
        cmp 0,d0
        beq .Lrelease_next
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lrelease_failed
        mov d3,a0
        mov 64,d0
        call .Lzero,[d2,d3,a2,a3],20
.Lrelease_next:
        inc d2
        cmp 10,d2
        bcs .Lrelease_cell
        mov (STATE+28,a2),d0
        cmp 0,d0
        bne .Lreleased
        mov a3,a0
        call lut_queue_close_guard,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lrelease_failed
.Lreleased:
        mov 4,d0
        mov d0,(STATE+4,a2)
        clr d0
        mov d0,(STATE+20,a2)
        ret [d2,d3,a2,a3],20
.Lrelease_failed:
        mov d0,(STATE+20,a2)
        mov 4,d1
        mov d1,(4,a3)
        mov -15,d0
        ret [d2,d3,a2,a3],20

.Ldescriptors:
        mov a0,a2
        mov lut_convert_banks,a1
        mov 8,d2
.Ldescriptor:
        movhu (a1),d0
        mov d0,(a0)
        movhu (2,a1),d0
        add a2,d0
        mov d0,(4,a0)
        movhu (4,a1),d0
        add a2,d0
        mov d0,(8,a0)
        add 6,a1
        add 12,a0
        sub 1,d2
        bne .Ldescriptor
        ret [d2,d3,a2,a3],20
.Lcopy:
        call native_memcpy,[a2,a3],8
        ret [d2,d3,a2,a3],20
.Lzero:
        mov d0,d1
        clr d0
.Lzero_byte:
        movbu d0,(a0)
        inc a0
        sub 1,d1
        bne .Lzero_byte
        ret [d2,d3,a2,a3],20
.Lzeroed:
        mov d0,d2
.Lzeroed_byte:
        movbu (a0),d0
        cmp 0,d0
        bne .Lnotzero
        inc a0
        sub 1,d2
        bne .Lzeroed_byte
        mov 1,d0
        ret [d2,d3,a2,a3],20
.Lnotzero:
        clr d0
        ret [d2,d3,a2,a3],20
lut_restore_code_end:
lut_restore_end:
