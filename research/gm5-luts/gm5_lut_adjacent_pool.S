/* Retained LUT storage backed by one ordinary native image-manager allocation.
 * lookup has the original pool getter ABI [a2]/8, with its existing caller's
 * D3=request and A3=LIL1. Only the session may create a pool. Root128B lives
 * in the owned image allocation; root+0 is the native
 * 16B image allocation record, +16magic, +20ready, +32native subpool,
 * +96options, +112region. The image manager rounds128KiB to2MiB; the subpool
 * exposes128KiB minus512B reserved for the root. The manager's backpointer
 * is rebound under its original mutex, and moved back to the stack BEFORE
 * final backing release. No kernel heap, fixed RAM hole or new boot hook.
 * Other request sizes retain stock region1 for temporary parser/file buffers.
 */
        .text
        .am33_2
        .global lut_adjacent_pool_lookup,lut_adjacent_pool_validate
        .global lut_adjacent_pool_collect,lut_adjacent_pool_end
        .extern native_image_pool,native_memset
        .extern native_heap_allocate,native_heap_release
        .extern native_heap_init
        .extern native_pool_constructor,native_pool_addref,native_pool_release
        .extern native_heap_lock,native_heap_unlock
        .equ OWNER,0x70a0e9a0
        .equ MAGIC,0x3148504c

lut_adjacent_pool_lookup:
        cmp 960,d3
        beq .Lretained
        cmp 2348,d3
        beq .Lretained
        cmp 3072,d3
        beq .Lretained
        cmp 4568,d3
        beq .Lretained
        jmp native_image_pool
.Lretained:
        add -48,sp
        mov d2,(4,sp)
        mov d3,(8,sp)
        mov a3,(12,sp)
        mov (0x8050),d0
        cmp 0,d0
        bne .Lbad
        mov (OWNER+12),a0
        cmp 0,a0
        beq .Lcreate
        mov a0,a2
        call lut_adjacent_pool_validate,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lbad
        mov a2,a0
        bra .Lreference
.Lcreate:
        mov a3,d0
        cmp OWNER,d0
        bne .Lbad
        cmp 3072,d3
        bne .Lbad
        mov (OWNER),d0
        cmp 0x314c494c,d0
        bne .Lbad
        mov (OWNER+4),d0
        cmp 3,d0
        bne .Lbad
        /* Raw lease open has already claimed its zero owner record. */
        call native_heap_init,[],4
        mov sp,a0
        add 16,a0
        clr d0
        mov 16,d1
        call native_memset,[a2],4
        mov sp,a0
        add 16,a0
        clr d0
        mov 131072,d1
        call native_heap_allocate,[d2,d3,a2,a3],28
        cmp 0,d0
        bne .Lbad
        mov (24,sp),d0
        cmp 0x18600000,d0
        bcs .Lrelease_stack
        mov d0,d1
        add 0x200000,d1
        bcs .Lrelease_stack
        cmp 0x1b400000,d1
        bhi .Lrelease_stack
        mov (28,sp),d1
        cmp 0x200000,d1
        bne .Lrelease_stack
        and 0x0fffffff,d0
        or 0xb0000000,d0
        mov d0,a2
        mov a2,a0
        clr d0
        mov 128,d1
        call native_memset,[a2],4
        mov sp,a0
        add 16,a0
        mov a2,a1
        call .Lrebind,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lrelease_stack
        mov (8,a2),d0
        add 512,d0
        mov 1,d1
        mov d1,(112,a2)
        mov d0,(116,a2)
        mov 130560,d1
        mov d1,(120,a2)
        mov 512,d0
        mov d0,(96,a2)
        mov a2,a0
        add 32,a0
        mov a2,a1
        add 112,a1
        mov a2,d0
        add 96,d0
        call native_pool_constructor,[a2,a3],16
        cmp 0,d0
        bne .Lrelease_backing
        mov a2,a0
        add 32,a0
        call native_pool_addref,[d2,a2],12
        cmp 1,d0
        bne .Lrelease_backing
        mov MAGIC,d0
        mov d0,(16,a2)
        mov 1,d0
        mov d0,(20,a2)
        mov a2,a0
        add 32,a0
.Lreference:
        mov a0,a2
        call native_pool_addref,[d2,a2],12
        mov a2,a0
        bra .Lreturn
.Lrelease_backing:
        mov a2,a0
        call .Lfree_backing,[d2,d3,a2,a3],20
        bra .Lbad
.Lrelease_stack:
        mov sp,a0
        add 16,a0
        clr d0
        call native_heap_release,[d2,a2],12
.Lbad:
        mov 0,a0
.Lreturn:
        mov (4,sp),d2
        mov (8,sp),d3
        mov (12,sp),a3
        ret [a2],56

/* A0=pool ->D0=1 iff root and its live native manager record agree.
 * No supplied return, address allocation, mutation or hardware query.
 */
lut_adjacent_pool_validate:
        mov a0,a2
        mov a0,d0
        and 3,d0
        bne .Linvalid
        mov a2,d0
        cmp 0xb8600020,d0
        bcs .Linvalid
        cmp 0xbb200020,d0
        bhi .Linvalid
        mov -32,a3
        add a2,a3
        mov (16,a3),d0
        cmp MAGIC,d0
        bne .Linvalid
        mov (20,a3),d0
        cmp 1,d0
        bne .Linvalid
        movhu (a3),d0
        cmp 0,d0
        bne .Linvalid
        movhu (2,a3),d2
        cmp 0,d2
        beq .Linvalid
        mov (4,a3),d0
        cmp 131072,d0
        bne .Linvalid
        mov (8,a3),d3
        cmp 0x18600000,d3
        bcs .Linvalid
        cmp 0x1b200000,d3
        bhi .Linvalid
        mov (12,a3),d0
        cmp 0x200000,d0
        bne .Linvalid
        mov (a2),d0
        cmp 0x7be2e240,d0
        bne .Linvalid
        mov (4,a2),d0
        cmp 1,d0
        bcs .Linvalid
        mov (8,a2),d0
        cmp 1,d0
        bne .Linvalid
        mov (12,a2),d0
        sub 512,d0
        cmp d3,d0
        bne .Linvalid
        mov (16,a2),d0
        cmp 130560,d0
        bne .Linvalid
        mov (28,a2),d0
        cmp 512,d0
        bne .Linvalid
        movbu (0x702db7a4),d1
        cmp 2,d1
        bcs .Linvalid
        cmp 32,d1
        bhi .Linvalid
        mov 0x702db5a4,a0
.Lrecord:
        movhu (a0),d0
        cmp d2,d0
        bne .Lnext
        mov (12,a0),d0
        mov a3,d1
        cmp d1,d0
        bne .Linvalid
        mov (8,a0),d0
        cmp d3,d0
        bne .Linvalid
        movbu (2,a0),d0
        cmp 0,d0
        bne .Linvalid
        movbu (3,a0),d0
        cmp 1,d0
        bne .Linvalid
        mov 1,d0
        ret [d2,d3,a2,a3],20
.Lnext:
        add 16,a0
        sub 1,d1
        bne .Lrecord
.Linvalid:
        clr d0
        ret [d2,d3,a2,a3],20

/* A0=pool, called after a normal child/getter reference release. A ready
 * root is released only with its baseline reference and an empty real list.
 */
lut_adjacent_pool_collect:
        mov a0,a2
        call lut_adjacent_pool_validate,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lcollect_return
        mov (4,a2),d0
        cmp 1,d0
        bne .Lcollect_return
        mov (40,a2),d0
        cmp 0,d0
        bne .Lcollect_return
        mov a2,d1
        add 20,d1
        mov (20,a2),d0
        cmp d1,d0
        bne .Lcollect_return
        mov (24,a2),d0
        cmp d1,d0
        bne .Lcollect_return
        mov a2,a0
        mov native_pool_release,a1
        calls (a1)
        mov -32,a0
        add a2,a0
        call .Lfree_backing,[d2,d3,a2,a3],20
.Lcollect_return:
        clr d0
        ret [d2,d3,a2,a3],20

/* Transfer the native owner backpointer while holding the same mutex as
 * native allocation/removal. A0=old16B record,A1=new16B record ->0/-5.
 * Both pointers are alive and owned for the complete operation.
 */
.Lrebind:
        add -16,sp
        mov a0,a2
        mov a1,a3
        mov 16,d0
        call native_heap_lock,[d2,d3,a2,a3],20
        cmp 0,d0
        blt .Lrebind_failed
        mov -5,d3
        movbu (0x702db7a4),d1
        cmp 32,d1
        bhi .Lrebind_unlock
        movhu (2,a2),d2
        mov 0x702db5a4,a0
.Lrebind_scan:
        cmp 0,d1
        beq .Lrebind_unlock
        movhu (a0),d0
        cmp d2,d0
        beq .Lrebind_found
        add 16,a0
        sub 1,d1
        bra .Lrebind_scan
.Lrebind_found:
        mov (12,a0),d0
        mov a2,d1
        cmp d1,d0
        bne .Lrebind_unlock
        mov (8,a0),d0
        mov (8,a2),d1
        cmp d1,d0
        bne .Lrebind_unlock
        mov a0,(12,sp)
        mov a2,a1
        mov a3,a0
        mov 4,d1
.Lrebind_copy:
        mov (a1),d0
        mov d0,(a0)
        inc4 a0
        inc4 a1
        sub 1,d1
        bne .Lrebind_copy
        mov (12,sp),a0
        mov a3,(12,a0)
        clr d3
.Lrebind_unlock:
        mov 16,d0
        call native_heap_unlock,[d2,d3,a2],16
        mov d3,d0
        ret [d2,d3,a2,a3],36
.Lrebind_failed:
        mov -5,d0
        ret [d2,d3,a2,a3],36

.Lfree_backing:
        add -20,sp
        mov sp,a1
        inc4 a1
        call .Lrebind,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lfree_return
        mov sp,a0
        inc4 a0
        clr d0
        call native_heap_release,[d2,a2],12
.Lfree_return:
        ret [d2,d3,a2,a3],40
lut_adjacent_pool_end:
