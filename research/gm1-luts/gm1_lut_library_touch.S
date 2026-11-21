/* Explicit GM1 Library touch configuration. F0/20; no startup/SD work.
 * Metadata+4896 owns the native parent's16B configuration and enable byte.
 * The row-child binder and touch event normalizer are reused GM5 modules.
 */
        .text
        .am33_2
        .global lut_gm1_touch_open,lut_gm1_touch_restore,lut_gm1_touch_config_end
        .extern lut_gm1_library_open,native_touch_config,native_refresh
        .extern parent_restore_continue
        .equ S,0x708f52c8

lut_gm1_touch_open:
        call lut_gm1_library_open,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn
        mov (S+72),a3
        add 4896,a3
        mov (a3),d0
        cmp 0,d0
        bne .Lbusy
        movbu (0x7004ec10),d0
        mov d0,(4,a3)
        mov 0x7004ec14,a0
        mov a3,a1
        add 8,a1
        mov 4,d1
.Lsave:
        mov (a0),d0
        mov d0,(a1)
        inc4 a0
        inc4 a1
        sub 1,d1
        bne .Lsave
        mov 0x3148544c,d0
        mov d0,(a3)
        mov 92,d0
        mov 1,d1
        mov 1,a0
        call native_touch_config,[d2],4
        call native_refresh,[d2],8
        clr d0
.Lreturn:
        ret [d2,d3,a2,a3],20
.Lbusy:
        mov -2,d0
        ret [d2,d3,a2,a3],20

/* A jump at the private parent's first six-byte load reaches this entry.
 * The preceding shared child binder already restored both parent's rows.
 */
lut_gm1_touch_restore:
        call .Lrestore,[d2,d3,a2,a3],20
        mov (S+16),d0
        jmp parent_restore_continue
.Lrestore:
        mov (S+72),a3
        add 4896,a3
        mov (a3),d0
        cmp 0x3148544c,d0
        bne .Lreturn
        mov (4,a3),d0
        movbu d0,(0x7004ec10)
        mov a3,a0
        add 8,a0
        mov 0x7004ec14,a1
        mov 4,d1
.Lrestore_words:
        mov (a0),d0
        mov d0,(a1)
        inc4 a0
        inc4 a1
        sub 1,d1
        bne .Lrestore_words
        mov a3,a0
        mov 6,d1
        clr d0
.Lclear:
        mov d0,(a0)
        inc4 a0
        sub 1,d1
        bne .Lclear
        ret [d2,d3,a2,a3],20
lut_gm1_touch_config_end:
