# GH2 update-key consumer and the GM5 format boundary

The legacy GH2 AES key is now traced from its initializer to the actual update
decryptor. Extracting that key from the verified GH2 image and using the update's
stored IV reproduces the **entire official GH2 1.2 plaintext byte for byte**.
The same native consumer explicitly accepts an older container revision and
selector values than those present in GM5 1.1. This establishes the legacy
mechanism; it does not decode GM5 or identify GM5's cipher.

The [evidence report](../evidence/gh2-update-consumer.json) records 17 native
regions, 1,353 instructions checked against source bytes, 23 relative call links,
the cipher object's function table and the independent OpenSSL replay. Native
code semantics remain manual static interpretations; this is not camera-code
execution or emulation.

## The key has an actual updater consumer

The source is the independently verified decoded body of
[Panasonic's official GH2 1.2 update](https://av.jpn.support.panasonic.com/support/share/eww/en/dsc/fts/mac/GH2__V12.zip),
SHA-256 `7501269737da3fcba4b9483d9171b291b9c96bf08780eaa83b24128cffd512ea`.
The mappings are the same ones established in the
[diagnostic investigation](gh2-debug-tools.md).

| Stage | GH2 address / offset | Observed behavior |
| --- | --- | --- |
| Key initializer | Body `0x7f50f8`, mapped flash `0x407f4cf8` | Sixteen bytes `90b43b5ce34c6e667fb28376b5fa5c27` |
| Startup copy | `0x40000195–0x400001b3`, end exclusive | Copies flash `0x407f4cd0–0x407f6384` to RAM `0x74000000`; the key consequently lands at `0x74000028` |
| Update job | Load at `0x7bcd61c6`, call at `0x7bcd61ce` | Passes that RAM address and length 16 to `0x7bcd5a8a` |
| Context setter | `0x7bcd5a8a` | Copies the key into the update context at offset 40 and stores its length |
| Cipher setup | `0x7bcd5bd7–0x7bcd5c12` | Constructs the AES object, selects 128 key bits and mode 1, passes the context's key and header bytes at offset `0x80` as IV |
| Cipher dispatch | Table `0x4024999c`, slots `0x1c` and `0x24` | Initialization reaches `0x400604b0`; update reaches `0x400605a6` through wrappers |
| AES decryption | `0x400605a6`, block helper `0x400609b2` | Decrypts each block, then XORs it with the saved initial IV / previous ciphertext block |

The key expansion uses the standard AES S-box at body offset `0x20b388`; the
block decryptor uses the inverse S-box at `0x20b488`. The copy, caller and
decryptor together provide stronger evidence than finding a key-like string or
an AES table alone.

The replay decrypts official file bytes `0x200` through EOF using AES-128-CBC,
the extracted native key and IV `eaefe7eee29547706360c431f8452b50` from outer
header offset `0x80`. It reproduces the pinned plaintext and its MD5
`35cb77e2ef08df9ef334ff1e496b0b02`, which equals the official header's bytes
`0x40–0x50`.

The native digest branch also agrees: selector 2 constructs an object whose
initializer at `0x40003c5c` contains the four MD5 initial-state constants. The
update job compares its resulting digest with header offset `0x40`.

### What this establishes about signatures

The reviewed GH2 1.2 path checks an MD5 digest and decrypts with AES-128-CBC.
No public-key signature-verification stage was identified in that path. MD5
can be recomputed after an edit, and AES encryption can be reproduced once its
symmetric key is known. Model/version and header-consistency checks remain
separate conditions. This is a bounded conclusion about the inspected path,
not a whole-program proof that no signature mechanism exists anywhere in GH2.
It does not establish GM1/GM5's newer update acceptance rules.

## GH2's parser does not support the GM5 layout

These are values read directly from the two official files:

| Outer-header offset | GH2 1.2 | GM5 1.1 | Interpretation established in GH2's code |
| --- | --- | --- | --- |
| `0x08` | `0x101` | `0x200` | Header reader requires exactly `0x101` |
| `0x2c` | `2` | `3` | Digest selector; validator accepts 0 or 2 |
| `0x30` | `0` | `0` | Validator requires zero |
| `0x34` | `2` | `3` | Cipher selector; validator accepts 0 or 2 |

The format comparison is at `0x7bcd5b16`; the additional validation is in
`0x7bcd5faa`. That validator also checks model/version and relationships between
fields. The table above describes selected checks, not a full compatibility
model or a modified-update acceptance test.

In GH2, cipher selector 2 reaches the observed AES-CBC implementation. GM5's
updater is still encrypted, so **value 3 has no established cipher meaning in
GM5**. It could involve a changed key or mechanism; its numerical value alone
cannot identify either. Likewise, the 32-byte fields in GM5 cannot yet be named
as plaintext hashes or keys merely from their lengths.

This strengthens the boundary on the earlier
[24 direct legacy-key tests](gm5-v11-analysis.md#older-panasonic-aes-key-bounded-negative-result).
Repeating the legacy decoder with another IV cannot address the unsupported
container and selector paths. Those negative tests remain bounded tests, rather
than proof that GM5 uses a particular replacement algorithm.

## Firmware-related SD filenames remain unresolved

GH2 contains these four literals at body offsets `0x2304ac`, `0x2304bb`,
`0x2304ca` and `0x2304da`:

- `B:\ROMDATA.BIN`
- `A:\ROMDATA.BIN`
- `B:\FIRMWARE.BIN`
- `A:\FIRMWARE.BIN`

There are no exact four-byte little-endian occurrences of their main-mapping
start addresses elsewhere in the complete decoded body. Computed, relative or
aliased references remain possible. **No consumer, export direction or
activation sequence has been established for these filenames.** They should
not be treated as a discovered SD firmware-dump feature.

Other SD filenames now have actual consumers: the
[factory-input follow-up](gh2-sd-factory-inputs.md) traces `GH2.AHX` /
`GH2E.AHX` to a programming job and `ESFFFFFF.BIN` to a RAM flag with a
lens-header-validation consumer. These paths do not resolve the four filenames
above or establish a plaintext export.

An additional caller of the known card-writing helper was resolved:
`0x400f021d` selects a settings-export filename and passes a caller's buffer and
length to `0x400f010d`. Its callers at `0x40025fd7` and `0x40025ffc` first invoke
the already traced settings text formatter at `0x401df73f`, with selectors zero
and one. This is another link in the settings-backup path; it does not establish
an executable firmware export.

## Reproduce

```sh
python3 tools/gh2_update_verify.py work/legacy-control/GH2__V12.body.decoded.bin --out work/gh2-update-consumer.json
```

The [verifier](../tools/gh2_update_verify.py) pins both official update hashes and
the decoded-body hash before disassembly or OpenSSL replay. It refuses existing
outputs and saves no decrypted binary. It uses only local files and host tools.

The strongest remaining access lead is still the
[separate binary USB maintenance interface](gh2-service-sequence.md). GH2 code
shows why a plaintext program-memory read could expose an update key as well as
executable code. Whether GM5 exposes the corresponding interface/readers, and
where its key is stored, remain unverified. No camera or local-network connection
was attempted during this follow-up.
