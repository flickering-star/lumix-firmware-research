/* A0=owned LIL1 lease -> D0=uncached CPU pointer,D1=capacity or0,0.
 * CALL F0/20. No allocation, mutation, memory copy or cache command.
 * Uses the original native1/7/B image-address conversion contract.
 * Region1bus134..186 -> uncachedB340..B860. Cached access is not enabled.
 * Validity/ownership checked against the actual original descriptor, not only
 * caller record fields. A shared descriptor is refused for private imports.
 */
        .text
        .am33_2
        .global lut_image_view,lut_image_view_end
        .extern lut_ram_span
.ifdef LUT_ADJACENT_POOL
        .extern lut_adjacent_pool_validate
.endif
lut_image_view:
        mov a0,d0
        and 3,d0
        bne .Lbad
        mov a0,a3
        mov a0,d0
        mov 32,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbad
        mov (a3),d0
        cmp 0x314c494c,d0
        bne .Lbad
        mov (4,a3),d0
        cmp 1,d0
        bne .Lbad
        mov (12,a3),d0
        cmp 0x70394dbc,d0
.ifdef LUT_ADJACENT_POOL
        beq .Lknown_parent
        mov d0,a0
        call lut_adjacent_pool_validate,[d2,d3,a2,a3],20
        cmp 1,d0
        bne .Lbad
.Lknown_parent:
.else
.ifdef LUT_RESERVED_POOL
        beq .Lknown_parent
        cmp 0xbbe50040,d0
        bne .Lbad
.Lknown_parent:
.else
        bne .Lbad
.endif
.endif
        mov (8,a3),d0
        mov d0,d1
        and 3,d1
        bne .Lbad
        mov 28,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lbad
        mov (8,a3),a2
        mov (a2),d0
        cmp 0x7be2e290,d0
        bne .Lbad
        mov (4,a2),d0
        cmp 1,d0
        bne .Lbad
        mov (12,a2),d0
        cmp 1,d0
        bne .Lbad
        mov (24,a2),d0
        mov (12,a3),d1
        cmp d1,d0
        bne .Lbad
        mov (16,a2),d0
        mov (16,a3),d1
        cmp d1,d0
        bne .Lbad
        mov (20,a2),d1
        mov (20,a3),d2
        cmp d2,d1
        bne .Lbad
        cmp 1,d1
        bcs .Lbad
        cmp 0x100000,d1
        bhi .Lbad
        mov (24,a3),d2
        cmp 1,d2
        bcs .Lbad
        cmp d1,d2
        bhi .Lbad
.ifdef LUT_ADJACENT_POOL
        mov (12,a3),a0
        mov a0,d2
        cmp 0x70394dbc,d2
        beq .Ladjacent_stock_bounds
        mov (16,a2),d0
        mov (12,a0),d2
        cmp d2,d0
        bcs .Lbad
        mov (16,a0),d3
        add d2,d3
        mov d0,d2
        add d1,d2
        bcs .Lbad
        cmp d3,d2
        bhi .Lbad
        bra .Ladjacent_convert
.Ladjacent_stock_bounds:
.endif
.ifdef LUT_RESERVED_POOL
        mov (12,a3),d3
        cmp 0xbbe50040,d3
        bne .Lstock_bounds
        cmp 0x1be50200,d0
        bcs .Lbad
        mov d0,d2
        add d1,d2
        bcs .Lbad
        cmp 0x1be70000,d2
        bhi .Lbad
        bra .Lconvert
.Lstock_bounds:
.endif
        cmp 0x13400000,d0
        bcs .Lbad
        mov d0,d2
        add d1,d2
        bcs .Lbad
        cmp 0x18600000,d2
        bhi .Lbad
.ifdef LUT_ADJACENT_POOL
.Ladjacent_convert:
.endif
.ifdef LUT_RESERVED_POOL
.Lconvert:
.endif
        and 0x0fffffff,d0
        or 0xb0000000,d0
        ret [d2,d3,a2,a3],20
.Lbad:
        clr d0
        clr d1
        ret [d2,d3,a2,a3],20
lut_image_view_end:
