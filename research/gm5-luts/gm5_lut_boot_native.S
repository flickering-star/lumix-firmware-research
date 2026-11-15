/* Internal-only startup restoration. Direct entry F0/20, no arguments.
 * Runs on the original UI owner after UI initialization, before input Receive.
 * Captures saved style before temporary Standard. No SD or NOR writer calls.
 * A temporary stack lease is safe only while executing; any cleanup refusal
 * transfers its complete owned record to the reserved registry tail (LBT1).
 * A later explicit retry moves it back onto its own stack before cleanup.
 * Existing durable mutations/Close refuse the unknown pending magic.
 */
        .text
        .am33_2
        .global lut_boot_restore,lut_boot_startup_shim,lut_boot_code_end
        .global lut_boot_workspace_allocate
        .extern native_ui_startup,native_ui_startup_continue
        .extern native_set_style,original_ensure_session,native_memcpy
        .extern lut_image_lease_open,lut_image_lease_close,lut_image_view
        .extern lut_session_view_shared,lut_restore_run,lut_restore_cleanup
        .equ CORE_GLOBAL,0x70a0e9c0
        .equ OWNER,0x70a0e9a0
        .equ STATE,832
        .equ MAGIC,0x3154424c

/* JMP at the original five-byte UI-startup CALL. Preserve its D2/8 call and
 * exact continuation; Bootstrap's own F0/20 also preserves the other saves.
 */
lut_boot_startup_shim:
        call native_ui_startup,[d2],8
        call lut_boot_restore,[d2,d3,a2,a3],20
        jmp native_ui_startup_continue

lut_boot_restore:
        add -56,sp
        mov (0x8050),d0
        cmp 0,d0
        bne .Largs
        mov (0x70a01d48),d0
        cmp 0,d0
        beq .Largs
        mov (CORE_GLOBAL),a3
        cmp 0,a3
        bne .Lexisting
        movbu (0x7bfb0055),d0
        cmp 16,d0
        bls .Ldesired
        clr d0
.Ldesired:
        mov d0,(36,sp)
        call original_ensure_session,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lsession_failed
        mov (CORE_GLOBAL),a3
        clr d0
        call native_set_style,[d2,d3,a2],16
        mov sp,a0
        add 4,a0
        mov 32,d0
        call .Lzero,[d2,d3,a2,a3],20
        mov sp,a0
        add 4,a0
        mov 28672,d0
lut_boot_workspace_allocate:
        call lut_image_lease_open,[d2,d3,a2,a3],20
        mov d0,(40,sp)
        cmp 0,d0
        bne .Lclose_workspace
        mov sp,a0
        add 4,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lview_bad
        mov d0,a2
        mov a2,a0
        mov 28672,d0
        call .Lzero,[d2,d3,a2,a3],20
        mov a2,a0
        mov 8,d1
        mov 0xa55a3cc3,d0
.Lguard_begin:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lguard_begin
        mov a2,a0
        add 28640,a0
        mov 8,d1
.Lguard_end:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lguard_end
        mov a3,a0
        mov sp,a1
        add 4,a1
        call lut_restore_run,[d2,d3,a2,a3],20
        mov d0,(40,sp)
        cmp -15,d0
        bne .Lclose_workspace
        mov (32+27180+16,a2),d0
        mov d0,(40,sp)
        bra .Lretain_restore
.Lview_bad:
        mov -18,d0
        mov d0,(40,sp)
.Lclose_workspace:
        mov sp,a0
        add 4,a0
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lretain_close
.Lcompleted:
        /* All temporary ownership has ended. The complete reconstructed
         * registry and frame pool already precede any requested LUT select. */
        mov a3,a0
        add STATE,a0
        mov 256,d0
        call .Lzero,[d2,d3,a2,a3],20
        mov (36,sp),d2
        cmp 7,d2
        bcs .Lselect
        mov d2,d0
        sub 7,d0
        mov (72,a3),d1
        lsr d0,d1
        btst 1,d1
        bne .Lselect
        clr d2
.Lselect:
        mov d2,d0
        call native_set_style,[d2,d3,a2],16
        mov (40,sp),d0
        mov d0,(60,a3)
        mov d2,d1
        bra .Lreturn
.Lretain_restore:
        mov 1,d2
        bra .Lretain
.Lretain_close:
        mov 2,d2
.Lretain:
        mov a3,a0
        add STATE,a0
        mov 256,d0
        call .Lzero,[d2,d3,a2,a3],20
        mov d2,(STATE+4,a3)
        mov (36,sp),d0
        mov d0,(STATE+8,a3)
        mov (40,sp),d0
        mov d0,(STATE+12,a3)
        mov (0x70a01d48),d0
        mov d0,(STATE+16,a3)
        mov a3,a0
        add STATE+32,a0
        mov sp,a1
        add 4,a1
        mov 32,d0
        call .Lcopy,[d2,d3,a2,a3],20
        /* Move, never duplicate ownership across the API return. */
        mov sp,a0
        add 4,a0
        mov 32,d0
        call .Lzero,[d2,d3,a2,a3],20
        mov MAGIC,d0
        mov d0,(STATE,a3)
        mov -15,d0
        mov d0,(60,a3)
        clr d1
        bra .Lreturn

.Lexisting:
        mov OWNER,a0
        call lut_session_view_shared,[d2,d3,a2,a3],20
        cmp 2560,d1
        bne .Largs
        add 32,d0
        mov a3,d1
        cmp d1,d0
        bne .Largs
        mov (STATE,a3),d0
        cmp MAGIC,d0
        bne .Lalready
        mov (STATE+16,a3),d0
        mov (0x70a01d48),d1
        cmp d1,d0
        bne .Largs
        mov (48,a3),d0
        cmp 0,d0
        bne .Lbusy
        mov (1796,a3),d0
        cmp 0,d0
        bne .Lbusy
        mov (1864,a3),d0
        cmp 0,d0
        bne .Lbusy
        mov (STATE+4,a3),d2
        cmp 1,d2
        beq .Lretry_record
        cmp 2,d2
        bne .Largs
.Lretry_record:
        mov (STATE+8,a3),d0
        cmp 16,d0
        bhi .Largs
        mov d0,(36,sp)
        mov (STATE+12,a3),d0
        mov d0,(40,sp)
        mov sp,a0
        add 4,a0
        mov a3,a1
        add STATE+32,a1
        mov 32,d0
        call .Lcopy,[d2,d3,a2,a3],20
        mov a3,a0
        add STATE+32,a0
        mov 32,d0
        call .Lzero,[d2,d3,a2,a3],20
        cmp 2,d2
        beq .Lclose_workspace
        mov a3,a0
        mov sp,a1
        add 4,a1
        call lut_restore_cleanup,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lretain_restore
        /* The failed reconstruction has now completely rolled back. Keep its
         * original primary error; this entry retries cleanup, not allocation. */
        bra .Lclose_workspace
.Lalready:
        mov 1,d0
        movbu (0x701ad636),d1
        bra .Lreturn
.Lsession_failed:
        mov d0,(40,sp)
        mov (36,sp),d2
        cmp 7,d2
        bcs .Lsession_select
        clr d2
.Lsession_select:
        mov d2,d0
        call native_set_style,[d2,d3,a2],16
        mov (40,sp),d0
        mov d2,d1
        bra .Lreturn
.Largs:
        mov -1,d0
        clr d1
        bra .Lreturn
.Lbusy:
        mov -2,d0
        clr d1
.Lreturn:
        ret [d2,d3,a2,a3],76
.Lcopy:
        call native_memcpy,[a2,a3],8
        ret [d2,d3,a2,a3],20
.Lzero:
        mov d0,d1
        clr d0
.Lzero_word:
        mov d0,(a0)
        inc4 a0
        sub 4,d1
        bne .Lzero_word
        ret [d2,d3,a2,a3],20
lut_boot_code_end:
