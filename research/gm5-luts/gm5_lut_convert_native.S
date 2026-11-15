/* Import-time RGB Cube/VLT -> original 9-cube YCbCr bank layout.
 * A0=completed owned parser context,A1=fresh aligned2284-byte output,
 * D0=0 require explicit STD tag /1 user explicitly chose Standard.
 * CALL F0/20;0 success,-1args,-2layout,-3sample,-4base,-5metadata,-12cancel.
 * Never publishes an active slot. On errors after generation starts, output
 * is partial INVALID staging, to be discarded by the caller. No SD access.
 * Only Standard is supported. Neutral metadata subset: grain OFF/L0,
 * color noise OFF, sharpness/noise reduction0/L50. Unknown/nonneutral and
 * conflicting L0/L1 color-noise tokens are rejected, never silently ignored.
 * Original signed-chroma ->RGB software routine is reused. Forward conversion
 * is the separately checked added Q10 helper, not a recovered ISP routine.
 */
        .text
        .am33_2
        .global lut_convert_table,lut_convert_code_end
        .extern lut_sample_rgb,lut_ram_span,lut_convert_banks,lut_convert_inputs
        .extern native_ycbcr_to_rgb

lut_convert_table:
        cmp 0,a0
        beq .Linitial_bad
        cmp 0,a1
        beq .Linitial_bad
        cmp 1,d0
        bhi .Linitial_bad
        mov a0,d1
        and 3,d1
        bne .Linitial_bad
        mov a1,d1
        and 3,d1
        bne .Linitial_bad
        add -96,sp
        mov a0,(4,sp)
        mov a1,(8,sp)
        mov d0,(12,sp)
        mov a0,d0
        mov 128,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs_bad
        mov (4,sp),a2
        mov (a2),d0
        cmp 0x31425543,d0
        beq .Lcube_span
        cmp 0x31544c56,d0
        bne .Llayout_bad
        mov 32768,d1
        bra .Lsource_span
.Lcube_span:
        mov 524288,d1
.Lsource_span:
        mov a2,d0
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs_bad
        mov d0,(24,sp)
        mov d1,(20,sp)
        mov (8,sp),d0
        mov 2284,d1
        call lut_ram_span,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Largs_bad
        mov (20,sp),d2
        cmp d2,d0
        bcc .Ldisjoint
        mov (24,sp),d2
        cmp d2,d1
        bhi .Largs_bad
.Ldisjoint:
        mov (40,a2),d0
        cmp 0,d0
        bne .Lcanceled
        /* Validate complete geometry by sampling into private stack space,
         * before policy reads and any output-table stores. */
        clr d0
        mov d0,(68,sp)
        mov a2,a0
        mov sp,a1
        add 68,a1
        .ifdef LUT_BASELINE_STACK_ARGUMENTS
        /* Same output address, using ordinary address->data register MOV.
         * Keep the five-byte extent and all existing symbol/branch addresses.
         * The original form remains available for byte-exact comparisons. */
        mov a1,d0
        add 4,d0
        nop
        .else
        mov sp,d0
        add 72,d0
        .endif
        call lut_sample_rgb,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn_status
        mov a2,a0
        mov (12,sp),d0
        call .Lstandard_policy,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn_status
        mov (8,sp),a3
        mov lut_convert_inputs,a0
        mov a0,(36,sp)
        clr d3
        /* Canonicalize the single byte of native alignment padding. */
        clr d0
        movbu d0,(221,a3)
.Lbank:
        mov d3,d0
        mov 6,d1
        mul d1,d0
        mov lut_convert_banks,a0
        add d0,a0
        movhu (a0),d0
        mov d0,(48,sp)
        mov d3,d1
        mov 12,d2
        mul d2,d1
        mov a3,a1
        add d1,a1
        movhu d0,(a1)
        clr d0
        movhu d0,(2,a1)
        movhu (2,a0),d0
        add a3,d0
        mov d0,(4,a1)
        mov d0,(40,sp)
        movhu (4,a0),d0
        add a3,d0
        mov d0,(8,a1)
        mov d0,(44,sp)
        clr d2
.Lnode:
        mov (40,a2),d0
        cmp 0,d0
        bne .Lcanceled
        mov (36,sp),a0
        movbu (a0),d0
        movbu d0,(52,sp)
        movbu (1,a0),d0
        movbu d0,(53,sp)
        movbu (2,a0),d0
        movbu d0,(54,sp)
        add 3,a0
        mov a0,(36,sp)
        mov sp,a0
        add 52,a0
        mov sp,a1
        add 56,a1
        call native_ycbcr_to_rgb,[d2,d3,a2],12
        /* The original E0/12 function need not preserve A3. */
        mov (8,sp),a3
        mov a2,a0
        mov sp,a1
        add 56,a1
        .ifdef LUT_BASELINE_STACK_ARGUMENTS
        mov a1,d0
        add 4,d0
        nop
        .else
        mov sp,d0
        add 60,d0
        .endif
        call lut_sample_rgb,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lreturn_status
        mov sp,a0
        add 60,a0
        mov sp,a1
        add 64,a1
        call .Lrgb_to_ycbcr,[d2,d3,a2,a3],20
        mov (40,sp),a0
        movbu (64,sp),d0
        lsr 2,d0
        movbu d0,(a0)
        inc a0
        mov a0,(40,sp)
        mov (44,sp),a0
        .ifdef LUT_NATIVE_CRCB
        movbu (66,sp),d0
        .else
        movbu (65,sp),d0
        .endif
        lsr 2,d0
        .ifdef LUT_NATIVE_CRCB
        movbu (65,sp),d1
        .else
        movbu (66,sp),d1
        .endif
        lsr 2,d1
        asl 6,d1
        or d1,d0
        movhu d0,(a0)
        add 2,a0
        mov a0,(44,sp)
        inc d2
        mov (48,sp),d0
        cmp d0,d2
        bcs .Lnode
        inc d3
        cmp 8,d3
        bcs .Lbank
        mov (40,a2),d0
        cmp 0,d0
        bne .Lcanceled
        clr d0
.Lreturn_status:
        ret [d2,d3,a2,a3],116
.Largs_bad:
        mov -1,d0
        bra .Lreturn_status
.Llayout_bad:
        mov -2,d0
        bra .Lreturn_status
.Lcanceled:
        mov -12,d0
        bra .Lreturn_status
.Linitial_bad:
        mov -1,d0
        ret [d2,d3,a2,a3],20

/* Completed source has been range/geometry checked. No implicit VLog fallback.
 * A0=context,D0=explicit user Standard choice0/1. No context mutation. */
.Lstandard_policy:
        mov a0,a2
        mov d0,d3
        mov (a2),d0
        cmp 0x31544c56,d0
        beq .Luntagged
        mov (88,a2),d0
        mov d0,d1
        and -32,d1
        bne .Lmetadata_bad
        and 1,d0
        beq .Lcube_untagged
        mov (92,a2),d0
        cmp 1,d0
        bne .Lbase_bad
        mov a2,a0
        add 1152,a0
        mov .Lstd,a1
        call .Ltoken_equal,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lmetadata_bad
        bra .Ladjustments
.Lcube_untagged:
        mov (92,a2),d0
        cmp 0,d0
        bne .Lmetadata_bad
        cmp 1,d3
        bne .Lbase_bad
.Ladjustments:
        mov 1,d2
.Ladjustment:
        mov 1,d0
        asl d2,d0
        mov (88,a2),d1
        and d1,d0
        beq .Lnext_adjustment
        mov d2,d0
        mov 96,d1
        mul d1,d0
        mov a2,a0
        add 1152,a0
        add d0,a0
        mov a0,a3
        mov .Loff,a1
        cmp 2,d2
        bls .Lfirst_token
        mov .Lzero,a1
.Lfirst_token:
        call .Ltoken_equal,[d2,d3,a2,a3],20
        cmp 0,d0
        beq .Lnext_adjustment
        cmp 2,d2
        beq .Lmetadata_bad
        mov a3,a0
        mov .Ll0,a1
        cmp 1,d2
        beq .Lsecond_token
        mov .Ll50,a1
.Lsecond_token:
        call .Ltoken_equal,[d2,d3,a2,a3],20
        cmp 0,d0
        bne .Lmetadata_bad
.Lnext_adjustment:
        inc d2
        cmp 5,d2
        bcs .Ladjustment
        clr d0
        ret [d2,d3,a2,a3],20
.Luntagged:
        cmp 1,d3
        bne .Lbase_bad
        clr d0
        ret [d2,d3,a2,a3],20
.Lbase_bad:
        mov -4,d0
        ret [d2,d3,a2,a3],20
.Lmetadata_bad:
        mov -5,d0
        ret [d2,d3,a2,a3],20

/* A0=96-byte parser metadata record,A1=literal. Exact length/terminator. */
.Ltoken_equal:
        mov (a0),d2
        cmp 1,d2
        bcs .Ltoken_bad
        cmp 63,d2
        bhi .Ltoken_bad
        inc4 a0
.Ltoken_byte:
        movbu (a0),d0
        movbu (a1),d1
        cmp d1,d0
        bne .Ltoken_bad
        cmp 0,d0
        beq .Ltoken_bad
        inc a0
        inc a1
        sub 1,d2
        bne .Ltoken_byte
        movbu (a0),d0
        movbu (a1),d1
        or d1,d0
        bne .Ltoken_bad
        ret [d2,d3,a2,a3],20
.Ltoken_bad:
        mov -1,d0
        ret [d2,d3,a2,a3],20

/* Added Q10 RGB8 ->YCbCr8, neutral128, nearest positive rounding, clip255.
 * D-register byte loads avoid the old extended-address-load disagreement. */
.Lrgb_to_ycbcr:
        movbu (a0),d2
        movbu (1,a0),d3
        movbu (2,a0),d0
        mov d0,a2
        mov d2,d0
        mov 306,d1
        mul d1,d0
        mov d0,a0
        mov d3,d0
        mov 601,d1
        mul d1,d0
        add d0,a0
        mov a2,d0
        mov 117,d1
        mul d1,d0
        add a0,d0
        add 512,d0
        asr 10,d0
        movbu d0,(a1)
        mov d2,d0
        mov -173,d1
        mul d1,d0
        mov d0,a0
        mov d3,d0
        mov -339,d1
        mul d1,d0
        add d0,a0
        mov a2,d0
        asl 9,d0
        add a0,d0
        add 131584,d0
        asr 10,d0
        cmp 255,d0
        ble .Lcb_store
        mov 255,d0
.Lcb_store:
        movbu d0,(1,a1)
        mov d2,d0
        asl 9,d0
        mov d0,a0
        mov d3,d0
        mov -429,d1
        mul d1,d0
        add d0,a0
        mov a2,d0
        mov -83,d1
        mul d1,d0
        add a0,d0
        add 131584,d0
        asr 10,d0
        cmp 255,d0
        ble .Lcr_store
        mov 255,d0
.Lcr_store:
        movbu d0,(2,a1)
        ret [d2,d3,a2,a3],20
lut_convert_code_end:
        .balign 4
.Lstd: .asciz "STD"
.Loff: .asciz "OFF"
.Lzero: .asciz "0"
.Ll0: .asciz "L0"
.Ll50: .asciz "L50"
