/* GM1 bindings for GM5's temporary list ownership contract.
 * Library+5200 LIL1[32],+5232 state0/1live/2retired,+5236 names,
 * +5240 release error,+5244 count. Native request2632, view+32:
 * UTF16[64][16] followed by65 original eight-byte generic rows.
 * A worker retires first; UI completion acknowledges by submitting release.
 * No allocation/directory pointer is exposed by a text getter.
 */
        .text
        .am33_2
        .global lut_gm1_list_scan,lut_gm1_list_dismiss,lut_gm1_list_release
        .global lut_gm1_list_name,lut_gm1_list_end
        .global lut_gm1_list_choose
        .extern lut_gm1_library_get,lut_gm1_control_open,lut_gm1_import_standard
        .extern lut_load_dialog_init,lut_load_dialog_open,lut_load_dialog_close
        .extern lut_load_dialog_file,lut_image_lease_open,lut_image_lease_close
        .extern lut_image_view
        .equ S,0x708f52c8

.Lowner:
        call lut_gm1_library_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        mov (S+72),a0
        cmp a0,d0
        bne .Largs
        mov d0,a0
        clr d0
        ret [d2,d3,a2,a3],20
.Largs:
        mov -18,d0
.Lreturn:
        ret [d2,d3,a2,a3],20

lut_gm1_list_dismiss:
        call .Lowner,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov a0,a3
        mov (128,a3),d0
        cmp 0,d0
        beq .Lretire
        mov a3,a0
        add 128,a0
        call lut_load_dialog_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
.Lretire:
        mov (5232,a3),d0
        cmp 0,d0
        beq .Lok
        mov 2,d0
        mov d0,(5232,a3)
.Lok:
        clr d0
        ret [d2,d3,a2,a3],20

lut_gm1_list_release:
        call .Lowner,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov a0,a3
        mov (5232,a3),d0
        cmp 0,d0
        beq .Lok
        cmp 2,d0
        bne .Lbusy
        mov a3,a0
        add 5200,a0
        call lut_image_lease_close,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lrelease_failed
        mov a3,a0
        add 5200,a0
        mov 12,d0
        call .Lzero,[d2,d3,a2,a3],20
        clr d0
        mov d0,(S+80)
        mov d0,(S+84)
        ret [d2,d3,a2,a3],20
.Lrelease_failed:
        mov -15,d0
        mov d0,(5240,a3)
        ret [d2,d3,a2,a3],20
.Lbusy:
        mov -2,d0
        ret [d2,d3,a2,a3],20

lut_gm1_list_scan:
        call lut_gm1_list_dismiss,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        call lut_gm1_list_release,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        call lut_gm1_import_standard,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        call lut_gm1_control_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        call .Lowner,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov a0,a3
        mov a3,a0
        add 128,a0
        mov 80,d0
        call .Lzero,[d2,d3,a2,a3],20
        mov a3,a0
        add 128,a0
        call lut_load_dialog_init,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov a3,a0
        add 128,a0
        call lut_load_dialog_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov (148,a3),d0
        cmp 64,d0
        bhi .Largs
        mov d0,d3
        /* Match GM5: a failed Open record is owned until explicit release. */
        mov 2,d0
        mov d0,(5232,a3)
        mov a3,a0
        add 5200,a0
        mov 2632,d0
        call lut_image_lease_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov a3,a0
        add 5200,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs
        add 32,d0
        mov d0,(5236,a3)
        mov d0,a2
        mov d0,a0
        mov 642,d0
        call .Lzero,[d2,d3,a2,a3],20
        clr d2
.Llist:
        cmp d3,d2
        bcc .Llisted
        mov a3,a0
        add 128,a0
        mov d2,d0
        call lut_load_dialog_file,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lfile_failed
        mov d0,a0
        add 19,a0
        mov d2,d0
        asl 5,d0
        mov a2,a1
        add d0,a1
        call .Lname,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov d2,d0
        asl 3,d0
        mov a2,a0
        add 2048,a0
        add d0,a0
        movhu d2,(a0)
        mov 0x0104,d0
        movhu d0,(2,a0)
        inc d2
        bra .Llist
.Llisted:
        mov d2,d0
        asl 3,d0
        mov a2,a0
        add 2048,a0
        add d0,a0
        mov -1,d0
        movhu d0,(a0)
        mov d3,(5244,a3)
        mov d3,(S+80)
        clr d0
        mov d0,(S+84)
        mov 1,d0
        mov d0,(5232,a3)
        clr d0
        ret [d2,d3,a2,a3],20
.Lfile_failed:
        mov d1,d0
        ret [d2,d3,a2,a3],20

/* Worker-only borrowed name. The list remains registered until UI Ack.
 * D0=index -> D0=pointer/0,D1=status. Never called by native text painting. */
lut_gm1_list_name:
        mov d0,d2
        call .Lowner,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lname_error
        mov a0,a3
        mov (5232,a3),d0
        cmp 1,d0
        bne .Lname_args
        mov (5244,a3),d0
        cmp 64,d0
        bhi .Lname_args
        cmp d0,d2
        bcc .Lname_args
        mov (5224,a3),d0
        cmp 2632,d0
        bne .Lname_args
        mov a3,a0
        add 5200,a0
        call lut_image_view,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lname_args
        add 32,d0
        mov (5236,a3),d1
        cmp d1,d0
        bne .Lname_args
        asl 5,d2
        add d2,d0
        clr d1
        ret [d2,d3,a2,a3],20
.Lname_args:
        mov -18,d0
.Lname_error:
        mov d0,d1
        clr d0
        ret [d2,d3,a2,a3],20

/* Same stable selected-name field used by GM5's confirmation-page copy. */
lut_gm1_list_choose:
        call lut_gm1_list_name,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lchoose_bad
        mov d0,a2
        call .Lowner,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov a0,a3
        mov a3,a0
        add 5248,a0
        mov 8,d1
.Lchoose_word:
        mov (a2),d0
        inc4 a2
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lchoose_word
        clr d0
        ret [d2,d3,a2,a3],20
.Lchoose_bad:
        mov d1,d0
        ret [d2,d3,a2,a3],20

/* These two bounded helpers are copied literally from the shared GM5
 * controller; only its error-label names are adapted by the builder. */
lut_gm1_list_shared_helpers:
lut_gm1_list_end:
