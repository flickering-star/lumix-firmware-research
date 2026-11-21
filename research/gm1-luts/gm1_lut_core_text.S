/* Read-only text adapters for the single retained core. Native frameless
 * leaf contract is preserved, including the entry MDR fast-return link.
 * The existing full-core lifetime retains names until reset; temporary-list
 * lifetime is a separate follow-up. No allocation or writer runs here.
 */
        .text
        .am33_2
        .global lut_gm1_core_library_text,lut_gm1_core_resource_text
        .global lut_gm1_core_text_end
        .extern lut_gm1_core_library_get,lut_gm1_core_ui
        .extern lut_library_texts,native_text_continue

.org 0,0xff
lut_gm1_core_library_text:
        add -20,sp
        mov mdr,d1
        mov d1,(4,sp)
        mov d0,(8,sp)
        mov a1,(12,sp)
        exthu d0
        cmp 121,d0
        bne .Lresource
        movhu (0x7022506e),d1
        cmp 0x10f0,d1
        bne .Lprevious
        mov 7030,d0
        bra .Lstatic
.Lresource:
        cmp 7030,d0
        bcs .Lprevious
        cmp 7113,d0
        bhi .Lprevious
        cmp 7040,d0
        bcs .Lstatic
        mov d0,(16,sp)
        call lut_gm1_core_library_get,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lstatic_original
        mov d0,a0
        mov (0x708f5310),d1
        cmp d1,d0
        bne .Lstatic_original
        mov (16,sp),d0
        sub 7040,d0
        cmp 10,d0
        bcs .Lcell
        sub 10,d0
        cmp 64,d0
        bcc .Lstatic_original
        add 968,a0
        bra .Lindex
.Lcell:
        add 3016,a0
.Lindex:
        asl 5,d0
        add d0,a0
        movhu (a0),d0
        cmp 0,d0
        beq .Lstatic_original
        bra .Lreturn
.Lstatic_original:
        mov (8,sp),d0
        exthu d0
.Lstatic:
        sub 7030,d0
        asl2 d0
        mov lut_library_texts,a0
        mov (d0,a0),a0
.Lreturn:
        mov (4,sp),d0
        mov d0,mdr
        mov (8,sp),d0
        mov (12,sp),a1
        add 20,sp
        retf [],0
.Lprevious:
        mov (4,sp),d1
        mov d1,mdr
        mov (8,sp),d0
        mov (12,sp),a1
        add 20,sp
        jmp lut_gm1_core_resource_text

.org 165,0xff
lut_gm1_core_resource_text:
        mov d0,d1
        exthu d1
        cmp 6849,d1
        jmp native_text_continue
.org 313,0xff
lut_gm1_core_text_end:
