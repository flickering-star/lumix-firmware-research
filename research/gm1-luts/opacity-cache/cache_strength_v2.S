/* GM1 v0.2.4 Opacity strength cache — v2 (binary-verified layout). One change only.
 *
 * Job body (4504B, verified in v0.2.4 binary 0x407f40f0 open / 0x407f4070 .Lviews):
 *   body[0..32)      unused by every view; zeroed at open (0x407f4143)  <- 16B key here
 *   body[32..2316)   table 2284B   == (24,sp) in capture
 *   body[2316..4504) scratch 2188B == (28,sp); written only by strength_generate
 * scratch keeps the last generate output until the next generate for this job, so it IS the cache.
 *
 * Hook 0x407f434a..0x407f436b (33B) in capture. Entry state (verified):
 *   a3 = job metadata (used after 0x407f436b; NOT modified here)
 *   (8,sp)=cell 0..9, (12,sp)=tick 1..9 here, (16,sp)=cell generation, (24,sp)=table, (28,sp)=scratch
 *   (36,40,44,sp) unused by capture (only 4..32 written)  -> key0 / s1 / s2 temporaries
 *   d2,d3,d1,a0..a2 dead after 0x407f436b (restored by capture's ret) -> free to use
 * Key (body[0..16)): [0]=0x4b430000|cell<<8|percent  [4]=generation  [8]=s1  [12]=s2
 *   s1/s2 = running sums over table+96 (2188B = 547 words): s1+=w, s2+=s1
 * Hit : all 4 match  -> memcpy(table+96 <- scratch, 2188) -> 0x407f436b
 * Miss: key[0]=0 first -> original generate (+memcpy) -> key[4..15] -> key[0] last -> 0x407f436b
 * Fail: generate !=0 -> key stays 0 -> 0x407f43ad (original abort path)
 * Writes stay inside body[0..16) and the original table/scratch. Guards (body-32, body+4504)
 * are never touched. No allocation, no static RAM, no SD/flash/UI access.
 */
        .am33_2
        .global cache_hook,cache_entry,cache_end
        .extern strength_generate,native_memcpy,capture_publish,capture_abort

        .equ OUT_BYTES,2188
        .equ WORDS,547
        .equ KEY_TAG,0x4b430000
        .equ S_KEY0,36
        .equ S_S1,40
        .equ S_S2,44

        .section .text.hook,"ax"
cache_hook:                             /* at 0x407f434a, d0 = percent (unused here) */
        jmp cache_entry
        .rept 28
        nop
        .endr

        .text
cache_entry:
        /* checksum source: a0 = table+96 */
        mov (24,sp),a0
        add 96,a0
        clr d1
        clr d3
        mov WORDS,d2
.Lsum:
        mov (a0),d0
        add d0,d1
        add d1,d3
        inc4 a0
        sub 1,d2
        bne .Lsum
        mov d1,(S_S1,sp)
        mov d3,(S_S2,sp)
        /* key0 = TAG | cell<<8 | percent(tick*10) */
        mov (12,sp),d0
        mov 10,d1
        mul d1,d0
        mov (8,sp),d1
        asl 8,d1
        or d1,d0
        or KEY_TAG,d0
        mov d0,(S_KEY0,sp)
        /* a1 = body = table-32 */
        mov (24,sp),a1
        add -32,a1
        mov (a1),d1
        cmp d1,d0
        bne .Lmiss
        mov (4,a1),d1
        mov (16,sp),d0
        cmp d1,d0
        bne .Lmiss
        mov (8,a1),d1
        mov (S_S1,sp),d0
        cmp d1,d0
        bne .Lmiss
        mov (12,a1),d1
        mov (S_S2,sp),d0
        cmp d1,d0
        bne .Lmiss
        /* hit: table+96 <- scratch (same call as original 0x407f435b..0x407f4369) */
        mov (24,sp),a0
        add 96,a0
        mov (28,sp),a1
        mov OUT_BYTES,d0
        call native_memcpy,[a2,a3],8
        jmp capture_publish

.Lmiss:
        mov (24,sp),a1
        add -32,a1
        clr d0
        mov d0,(a1)                     /* invalidate before generate */
        /* original sequence 0x407f4346..0x407f4369 */
        mov (12,sp),d0
        mov 10,d1
        mul d1,d0
        mov (28,sp),a0
        mov (24,sp),a1
        add 96,a1
        call strength_generate,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lfail
        mov (24,sp),a0
        add 96,a0
        mov (28,sp),a1
        mov OUT_BYTES,d0
        call native_memcpy,[a2,a3],8
        /* publish key, word 0 last */
        mov (24,sp),a1
        add -32,a1
        mov (16,sp),d0
        mov d0,(4,a1)
        mov (S_S1,sp),d0
        mov d0,(8,a1)
        mov (S_S2,sp),d0
        mov d0,(12,a1)
        mov (S_KEY0,sp),d0
        mov d0,(a1)
        jmp capture_publish
.Lfail:
        jmp capture_abort
cache_end:
