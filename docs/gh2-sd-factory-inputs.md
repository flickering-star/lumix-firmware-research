# GH2 factory SD inputs and a lens-validation flag

Two filename leads now have traced consumers in the verified GH2 1.2 plaintext.
`GH2.AHX` / `GH2E.AHX` feed a factory programming job; `ESFFFFFF.BIN` acts as a
file-presence flag with a verified lens-update consumer. Neither is a firmware
export or a demonstrated GM5 feature.

The [native-byte report](../evidence/gh2-sd-factory-inputs.json) pins the complete
GH2 decoded body, checks thirteen instruction regions and fifteen relative calls,
and retains the reviewed disassembly. The input SHA-256 is
`7501269737da3fcba4b9483d9171b291b9c96bf08780eaa83b24128cffd512ea`.
Address mappings follow the [earlier GH2 analysis](gh2-debug-tools.md).

## The AHX path reads and programs an image

Startup at `0x4000385a` tests separate predicates before the normal temporary
service-entry test. Predicate `0x7bccb371` requires drive-decoder result `3`,
the raw AF/AE LOCK input `0x400`, the DISPLAY predicate, and an additional
hardware predicate. The latter, `0x401457b9`, requires bit `0x02` of MMIO
`0x9c00c082` to remain clear for ten reads. Its physical signal is unresolved.
Drive results `1` and `3` have not been assigned physical dial positions here.
These observations do not supply a verified button procedure.

With job mode zero, startup calls `0x40060e1f`. That job tries `A:\GH2.AHX`, then
`A:\GH2E.AHX`, through reader `0x400f9154`. Decoded bytes go to fixed staging
base `0xb5000000`. The fallback selects mode `3` for a later helper; that mode's
complete meaning remains unresolved.

The reader rejects files smaller than `0x600010` bytes and processes fixed
48-character text records into sixteen decoded bytes. The record parser at
`0x400f9384` recognizes ASCII `S3`, decodes an eight-hex-character address,
compares it with the caller's expected sequential offset, and stores data at
the staging base plus that offset. It checks an additive one's-complement
checksum and CRLF. The address does not select an arbitrary CPU destination.
The interpretation agrees with NXP's description of
[Motorola S3 records](https://www.nxp.com/docs/en/reference-manual/DSPFAQ11478_LINKER.UM.pdf),
section 5.6.2.2. The native helper returns `7` for other records beginning with
`S`; strict S7 trailer validation has not been established.

After a further extent check, the factory job calls `0x400f946a`. It preserves
selected existing data in the staged image and copies programming routines into
RAM. Copy helper `0x400f9ed1` copies `0x400f9804–0x400f9ecd`, end exclusive;
the prepared code is called indirectly at `0x400f97fe`. Another reviewed helper
issues 16-bit flash command/data writes and polls the destination. These are
concrete programming effects, rather than an inference from an AHX filename.

No AES operation was identified in the inspected record parser. The complete
programming and acceptance conditions have not been proven. No AHX image was
created, no target instructions were executed, and no camera was contacted.

## The BIN marker changes later validation

A separate startup predicate at `0x7bccb431` uses drive result `1` with the same
key and hardware conditions. It invokes the factory job with mode one, which
calls `0x40154ff3` and skips the AHX reader on that branch.

That routine opens `A:\ESFFFFFF.BIN` in `rb` mode. A successful open sets RAM
byte `0x7435d728` to one and closes the file. It does not read its contents.
Getter `0x4015501c` exposes the byte to other code.

One verified consumer is a header validator at `0x400f8b32`. It requires the
second byte to be `L`, checks reserved fields, and classifies first bytes
`O`, `S`, `P`, `R` and `Q`. At `0x400f8c04` it calls the flag getter; a nonzero
result skips several later metadata comparisons. The initial structure checks
remain on the inspected path.

An independently acquired official Panasonic lens update supplies a format
control. The [H-FS12032 download page](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/fs12032.html)
links version 1.2. Its archive contains `ES102012.lin`, 458,816 bytes, SHA-256
`ce9499157483ec1570cce8317d9606bdacc361fa8bc40664474c31be2c9ccc9e`.
Its prefix is `PL`; its field positions match the inspected validator:

| Lens-file offset | Observed value |
| --- | --- |
| `0x02`, little-endian u16 | `0x1020` |
| `0x04`, little-endian u16 | `0x1000` |
| `0x0c`, little-endian u32 | `0x70000` |
| `0x10`, little-endian u16 | `0x1200` |

The [acquisition receipt](../evidence/h-fs12032-lens-control-acquisition.json)
records the official download workflow, archive hash and ZIP CRC verification.
This establishes a lens-file control for that consumer, not GH2 compatibility
with that particular 2020 lens release. Other flag consumers are not completely
classified. A body-firmware decryption bypass, text console or GM5 counterpart
has not been established. No marker file was written to a card.

## Reproduce the offline checks

With the recorded intact inputs and local MN103 decoder, use a fresh output:

```sh
python3 tools/gh2_sd_loader_verify.py work/legacy-control/GH2__V12.body.decoded.bin --out work/gh2-sd-factory-new.json
```

The [verifier](../tools/gh2_sd_loader_verify.py) rejects different GH2/lens inputs
before disassembly and refuses to overwrite an existing output. Its mechanical
checks cover hashes, instruction bytes, literal strings, copy constants and call
targets. The interpretation of native behavior is manual analysis, not emulation.
The [binary USB readers](gh2-service-sequence.md) remain the more direct
plaintext-access lead, subject to their model and service-state requirements.
