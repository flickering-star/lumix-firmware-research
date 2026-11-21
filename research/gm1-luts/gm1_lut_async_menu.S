/* GM1 UI binding for the shared GM5 native worker/completion implementation.
 * Existing navigation, Language-style painter, touch rows and owned filenames
 * remain. Only slow action submissions/Ready and busy cancellation live here.
 * Job128 is session+2432; its112..127 use GM5's DTR1 continuation layout.
 * S+92 is GM5's exit flag0normal/1Back/2deferred shutter. Library reserved
 * 5184/5188 hold deferred key/context and5196 the first operation error.
 * No boot/SD hook; the native UI owner retains all bind/draw operations.
 */
        .text
        .am33_2
        .global lut_gm1_async_ready,lut_gm1_async_event,lut_gm1_async_open
        .global lut_gm1_async_menu_end
        .extern lut_gm1_control_get,lut_gm1_library_get,lut_image_view
        .extern lut_async_job_init,lut_ui_completion_init,lut_ui_completion_start
        .extern lut_ui_completion_cancel,previous_library_event,previous_library_open
        .extern lut_library_event
        .extern native_screen,native_set_style,native_style_dirty
        .extern native_list_bind,native_refresh
        .extern lut_library_rows,lut_library_actions,lut_library_message
        .equ S,0x708f52c8

/* CALLS D0result,D1mask,A0Library,A1job, after Ack/timer/ref cleanup. */
lut_gm1_async_ready:
        movm [d2,d3,a2,a3],(sp)
        add -16,sp
        mov d0,(4,sp)
        mov a0,a2
        mov a1,a3
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp a2,d0
        bne .Rdone
        call .Ljob,[d2,d3,a2,a3],20
        cmp a3,d0
        bne .Rdone
        mov (24,a3),d3
        mov (112,a3),d0
        cmp 0,d0
        beq .Rresult
        cmp 0x31525444,d0
        bne .Rinvalid
        mov (124,a3),d0
        mov (52,a3),d1
        cmp d1,d0
        bne .Rinvalid
        /* Successful Resolve has already cleared its transaction fields.
         * A still-pending retry must belong to precisely the tagged epoch. */
        mov (4,sp),d0
        cmp -15,d0
        bne .Rretry_operation
        mov (120,a3),d0
        mov (4952,a2),d1
        cmp d1,d0
        bne .Rinvalid
.Rretry_operation:
        mov (116,a3),d3
.Rresult:
        mov (4,sp),d0
        cmp -15,d0
        bne .Rcomplete
        cmp 2,d3
        beq .Rpending_mutation
        cmp 3,d3
        bne .Rcomplete
.Rpending_mutation:
        mov (4932,a2),d0
        cmp 4,d0
        bcs .Rcomplete
        cmp 6,d0
        bhi .Rcomplete
        mov 0x31525444,d0
        mov d0,(112,a3)
        mov d3,(116,a3)
        mov (4952,a2),d0
        mov d0,(120,a3)
        mov 4,d0
        clr d1
        mov 0,a1
        call .Lsubmit,[d2,d3,a2,a3],20
        bra .Rdone
.Rcomplete:
        clr d0
        .irp off,112,116,120,124
        mov d0,(\off,a3)
        .endr
        mov (4,sp),d0
        cmp 0,d0
        beq .Rstatus_saved
        cmp -12,d0
        bne .Rsave_error
        mov (S+92),d1
        cmp 0,d1
        bne .Rstatus_saved
.Rsave_error:
        mov (5196,a2),d1
        cmp 0,d1
        bne .Rstatus_saved
        mov d0,(5196,a2)
.Rstatus_saved:
        cmp 4,d3
        beq .Rfinish
        cmp 5,d3
        beq .Rfinish
        cmp 1,d3
        bne .Rcleanup
        mov (4,sp),d0
        cmp 0,d0
        bne .Rcleanup
        mov (S+92),d0
        cmp 0,d0
        bne .Rcleanup
        mov (S+4),d0
        cmp 1,d0
        bne .Rcleanup
        call native_screen,[],0
        cmp 0x10f0,d0
        bne .Rcleanup
        mov 2,d0
        mov d0,(S+76)
        mov a2,a0
        add 448,a0
        mov (S+84),d1
        mov (S+80),d0
        cmp 0,d0
        bne .Rbind
        mov lut_library_message,a0
        clr d1
        bra .Rbind
.Rcleanup:
        /* Same ordering as GM5: finish/dismiss the worker-owned dialog
         * before navigation or a deferred shutter can leave this page. */
        mov 4,d0
        clr d1
        mov 0,a1
        call .Lsubmit,[d2,d3,a2,a3],20
        bra .Rdone
.Rfinish:
        mov (S+4),d0
        cmp 1,d0
        bne .Rdone
        call native_screen,[],0
        cmp 0x10f0,d0
        bne .Rdone
        mov (5196,a2),d0
        cmp 0,d0
        bne .Rerror
        mov (S+92),d0
        cmp 2,d0
        beq .Rparent
        cmp 1,d0
        beq .Rcells
.Ractions:
        clr d0
        mov d0,(S+92)
        mov 1,d0
        mov d0,(S+76)
        mov lut_library_actions,a0
        clr d1
        bra .Rbind
.Rcells:
        clr d0
        mov d0,(S+76)
        mov d0,(S+92)
        mov lut_library_rows,a0
        mov (S+8),d1
.Rbind:
        call .Lbind,[d2,d3,a2,a3],20
        bra .Rdone
.Rparent:
        mov 0x0f000002,d0
        mov (5184,a2),d1
        mov (5188,a2),a0
        mov lut_library_event,a1
        calls (a1)
        clr d0
        mov d0,(S+76)
        mov d0,(S+92)
        mov d0,(5184,a2)
        mov d0,(5188,a2)
        bra .Rdone
.Rinvalid:
        mov -18,d0
.Rerror:
        call .Lerror,[d2,d3,a2,a3],20
.Rdone:
        ret [d2,d3,a2,a3],32

/* CALLS event wrapper. Unhandled input retains the existing GM1 handler. */
lut_gm1_async_event:
        movm [d2,d3,a2,a3],(sp)
        add -16,sp
        mov d0,(4,sp)
        mov d1,(8,sp)
        mov a0,(12,sp)
        cmp 0x0f000002,d0
        bne .Edelegate
        mov (S+4),d0
        cmp 1,d0
        bne .Edelegate
        call native_screen,[],0
        cmp 0x10f0,d0
        bne .Edelegate
        mov (8,sp),d2
        cmp 0x10003,d2
        blt .Ekey
        cmp 0x10006,d2
        bgt .Ekey
        sub 0x10000,d2
.Ekey:
        mov (S+76),d3
        cmp 0,d3
        beq .Edelegate
        cmp 0,d2
        blt .Edelegate
        cmp 2,d2
        ble .Eshutter
        cmp 4,d3
        beq .Ebusy
        cmp 7,d2
        bne .Eback
        movhu (0x7010292e),d2
        cmp 1,d3
        beq .Eaction
        cmp 3,d3
        bne .Eback
        cmp 0,d2
        bne .Edelegate
        mov 2,d0
        mov (S+84),d1
        mov 1,a1
        bra .Estart
.Eaction:
        cmp 0,d2
        beq .Escan
        cmp 1,d2
        bne .Edelegate
        mov 3,d0
        bra .Ecell
.Escan:
        mov 1,d0
.Ecell:
        mov (S+8),d1
        mov 0,a1
        bra .Estart
.Eback:
        mov (8,sp),d2
        cmp 8,d2
        beq .Eclose_list
        cmp 10,d2
        beq .Eclose_list
        cmp 11,d2
        beq .Eclose_list
        cmp 3,d2
        bne .Edelegate
.Eclose_list:
        cmp 2,d3
        bne .Eerror_back
        mov 4,d0
        bra .Ezero
.Eerror_back:
        cmp 6,d3
        bne .Edelegate
        mov 4,d0
.Ezero:
        clr d1
        mov 0,a1
.Estart:
        call .Lnew,[d2,d3,a2,a3],20
        bra .Edone
.Eshutter:
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Edone
        mov d0,a2
        mov d2,(5184,a2)
        mov (12,sp),d0
        mov d0,(5188,a2)
        mov 2,d0
        mov d0,(S+92)
        cmp 4,d3
        beq .Ecancel_job
        mov 4,d0
        clr d1
        mov 0,a1
        call .Lsubmit,[d2,d3,a2,a3],20
        bra .Edone
.Ebusy:
        cmp 8,d2
        beq .Ecancel
        cmp 10,d2
        beq .Ecancel
        cmp 11,d2
        beq .Ecancel
        cmp 3,d2
        bne .Edone
.Ecancel:
        mov 1,d0
        mov d0,(S+92)
.Ecancel_job:
        call .Ljob,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Edone
        mov d0,a0
        call lut_ui_completion_cancel,[d2,d3,a2,a3],20
        bra .Edone
.Edelegate:
        mov (4,sp),d0
        mov (8,sp),d1
        mov (12,sp),a0
        mov previous_library_event,a1
        calls (a1)
.Edone:
        ret [d2,d3,a2,a3],32

/* Match GM5's idle-only Library entry. Touch setup happens only after this
 * returns, so a still-owned pending session cannot be reopened/rebound. */
lut_gm1_async_open:
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Oopen
        call .Ljob,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Oopen
        mov d0,a0
        mov (4,a0),d0
        mov (16,a0),d1
        or d1,d0
        mov (72,a0),d1
        or d1,d0
        mov (108,a0),d1
        or d1,d0
        cmp 0,d0
        bne .Obusy
.Oopen:
        call previous_library_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Oreturn
        clr d0
        mov d0,(S+92)
.Oreturn:
        ret [d2,d3,a2,a3],20
.Obusy:
        mov -2,d0
        bra .Oreturn

/* A fresh user action clears only its error/deferred intent, preserving the
 * shared job/controller state. Cleanup continuations use .Lsubmit directly. */
.Lnew:
        add -16,sp
        mov d0,(4,sp)
        mov d1,(8,sp)
        mov a1,(12,sp)
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lnew_bad
        mov d0,a2
        clr d0
        mov d0,(S+88)
        mov d0,(S+92)
        mov d0,(5184,a2)
        mov d0,(5188,a2)
        mov d0,(5196,a2)
        mov (4,sp),d0
        mov (8,sp),d1
        mov (12,sp),a1
        call .Lsubmit,[d2,d3,a2,a3],20
        ret [d2,d3,a2,a3],36
.Lnew_bad:
        mov -18,d0
        call .Lerror,[d2,d3,a2,a3],20
        ret [d2,d3,a2,a3],36

/* Current exact session job pointer; no allocation or new reference. */
.Ljob:
        call lut_gm1_control_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Ljob_return
        mov d0,a0
        add 32,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Ljob_return
        cmp 3072,d1
        bne .Ljob_bad
        add 2432,d0
.Ljob_return:
        ret [d2,d3,a2,a3],20
.Ljob_bad:
        clr d0
        ret [d2,d3,a2,a3],20

/* UI-only lazy LAJ1/UCT1 setup in the existing session's reserved128B. */
.Lprepare:
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lprepare_bad
        mov d0,d2
        mov d1,a2
        mov (12,a2),d0
        cmp 2,d0
        bne .Lprepare_bad
        call .Ljob,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lprepare_bad
        mov d0,a3
        mov (a3),d0
        cmp 0,d0
        bne .Lprepare_existing
        mov a3,a0
        mov a2,a1
        add 32,a1
        call lut_async_job_init,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lprepare_return
.Lprepare_existing:
        mov (a3),d0
        cmp 0x314a414c,d0
        bne .Lprepare_bad
        mov (68,a3),d0
        cmp 0,d0
        bne .Lprepare_configured
        mov a3,a0
        mov lut_gm1_async_ready,a1
        mov d2,d0
        call lut_ui_completion_init,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lprepare_return
.Lprepare_configured:
        mov (68,a3),d0
        cmp 0x31544355,d0
        bne .Lprepare_bad
        mov a3,d1
        clr d0
.Lprepare_return:
        ret [d2,d3,a2,a3],20
.Lprepare_bad:
        mov -18,d0
        clr d1
        ret [d2,d3,a2,a3],20

/* Submit returns before parsing/SD/NOR work. Only the UI owner binds rows. */
.Lsubmit:
        add -16,sp
        mov d0,(4,sp)
        mov d1,(8,sp)
        mov a1,(12,sp)
        cmp 1,d0
        bcs .Lsubmit_prepare
        cmp 3,d0
        bhi .Lsubmit_prepare
        clr d0
        call native_set_style,[d2,d3],12
        call native_style_dirty,[],0
.Lsubmit_prepare:
        call .Lprepare,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lsubmit_error
        mov d1,a3
        mov 4,d0
        mov d0,(S+76)
        mov a3,a0
        mov (4,sp),d0
        mov (8,sp),d1
        mov (12,sp),a1
        call lut_ui_completion_start,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lsubmit_error
        mov (112,a3),d0
        cmp 0x31525444,d0
        bne .Lsubmit_wait
        mov (36,a3),d0
        mov d0,(124,a3)
.Lsubmit_wait:
        mov lut_library_message,a0
        clr d1
        call .Lbind,[d2,d3,a2,a3],20
        clr d0
        ret [d2,d3,a2,a3],36
.Lsubmit_error:
        call .Lerror,[d2,d3,a2,a3],20
        ret [d2,d3,a2,a3],36
.Lerror:
        mov d0,(S+88)
        mov 6,d0
        mov d0,(S+76)
        mov lut_library_message,a0
        clr d1
.Lbind:
        mov 0x10f0,d0
        call native_list_bind,[d2,a2],12
        call native_refresh,[d2],8
        ret [d2,d3,a2,a3],20
lut_gm1_async_menu_end:
