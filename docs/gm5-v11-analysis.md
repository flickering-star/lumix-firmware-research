# Official GM5 1.1: container and encoding analysis

**Historical container-analysis checkpoint.** Subsequent service-USB reads
recovered the GM5 key. Five-round AES-128-CBC decodes all eight components and
every SHA-256 field matches; the directory's ECDSA P-256 signature also verifies.
See the current [flashing investigation](gm5-flashing.md),
[decode report](../evidence/gm5-v11-decoded.json) and
[signature report](../evidence/gm5-directory-signature.json). The unresolved
claims below describe the earlier stage, rather than the present state.

The official update is now downloaded and inspected. It has eight encoded
components and a verified outer CRC32. Their sizes and apparent destinations
support **replacement images for components**, but do not establish a full flash
backup. The exact Olympus OE transform and direct use of a verified older Lumix
AES key did not reveal plaintext.

## Acquired sample

The [official GM5 page](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gm5.html)
links the [Mac ZIP](https://av.jpn.support.panasonic.com/support/share/eww/en/dsc/fts/mac/GM5__V11.zip).
The system `curl` downloaded it over HTTPS with certificate verification enabled;
HTTP status was 200. ZIP CRC verification passed. The archive contains exactly
one member, `GM5__V11.bin`.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| ZIP | 31,905,359 | `0e9be7b3bb0eb0378f67110efe3ef7657d7b7920f9a52e1534653029ef21e515` |
| BIN | 31,901,184 | `d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243` |

Original files are in `firmware/official-gm5-v11/`. The
[acquisition receipt](../evidence/gm5-v11-acquisition.json) retains URLs, sizes,
hashes, TLS result and the archived official page's hash. These are locally
computed hashes, not a publisher signature. Earlier DNS failures were real but
are superseded by the session's permission change and this successful download.
The installed Python's certificate store still failed; system `curl` succeeded
without disabling TLS verification.

## Header and directory

Directly verified in this sample:

- Outer magic `UPD\0`, model `GM5`, and a 512-byte outer block.
- The field at file offset `0x3c` equals `file_size - 0x200`.
- The little-endian field at `0x40` is `0xe2b1a149`, exactly CRC32 of bytes
  `0x200` through EOF.
- The first `0x40` bytes are repeated at `0x2a0`; the CRC itself is outside that
  repeated range.
- A directory count of eight at `0x2e8`, followed by eight `0x5c`-byte records
  from `0x2ec`. Payloads begin at `0x600` and are contiguous to EOF.

Each record contains a 12-byte name, four little-endian 32-bit fields, a 32-byte
field, a 16-byte field, and sixteen reserved bytes. The four integers behave as
body-relative file offset, size, destination-offset candidate, and flags. All
eight flags equal three. The stored file offset requires **adding `0x200`** to
locate the payload in this file.

| Component | File offset | Encoded bytes | Destination candidate |
| --- | --- | --- | --- |
| `program` | `0x00000600` | `0x00800000` (8 MiB) | `0x00000000` |
| `guires` | `0x00800600` | `0x00c00000` (12 MiB) | `0x00800000` |
| `program2` | `0x01400600` | `0x00360000` | `0x01400000` |
| `armcode` | `0x01760600` | `0x00340000` | `0x01760000` |
| `other` | `0x01aa0600` | `0x00380000` | `0x01b40000` |
| `eep_ow_a` | `0x01e20600` | `0x00020000` | `0x01fa0000` |
| `eep_ow_b` | `0x01e40600` | `0x00020000` | `0x01fc0000` |
| `eep_adjfix` | `0x01e60600` | `0x0000c000` | `0x01fe0000` |

These destination candidates fit the manual's **32 MiB NOR** without overlap.
If they are flash byte offsets, payloads cover 31,899,648 bytes, or **95.068%**,
and leave these ranges uncovered:

- `0x01aa0000–0x01b40000`: 640 KiB.
- `0x01ec0000–0x01fa0000`: 896 KiB.
- `0x01fec000–0x02000000`: 80 KiB.

Range ends above are exclusive. This is a consistent flash-layout hypothesis;
the actual updater consumer has not been traced. It does not identify which gap
contains boot code, calibration, reserved space or something else. A component
name such as `armcode` does not establish the main processor's ISA.

The large, aligned components are evidence against a small change-only package.
Their decoded contents remain unknown, so this is not proof of every step the
camera performs when applying the update. The file also cannot restore bytes it
does not contain and should not be described as a complete chip backup.

## Exact Olympus transform: negative result with a positive control

The inspected Olympus OE scheme rearranges each 16-byte group using positions
`1,3,0,2,6,4,7,5,11,10,9,8,13,14,12,15`, then XORs each byte with `0xff`.
The [reference implementation](https://github.com/fishcu/oly_fw_analysis/blob/9be1867ace6638d79e705048212dfddd3a1e794f/tools/oly_container.py)
was pinned and checked against the local stock PEN-F 3101 image:

- All four Olympus component checksums passed.
- An unchanged decode/re-encode reproduced the entire Olympus container.
- Its main decoded SHA-256 matched
  `a2eb1d1f1afe47cce148e9aae0a04dfb82547d9de9437d342e012341140913f4`.

Applying the same decoder to each of the eight GM5 payloads produced no relevant
keyword strings or clear plaintext structure. The GM5 `program` entropy remained
**7.999979003 bits/byte**. The PEN-F control's main payload has entropy
**5.872547961**, identical before and after its successful decode.

That equality is expected: rearranging bytes preserves their counts, and a fixed
XOR merely relabels the 256 possible values. Consequently, this exact Olympus
transform **cannot change byte-value Shannon entropy**. A changed string count
after a permutation is not itself evidence of decoding.

This rejects the straightforward reuse of Olympus OE obfuscation as a sufficient
decoder for this GM5 update. It does not rule out an extra encryption/compression
layer or a different encoding. See the
[positive-control evidence](../evidence/gm5-v11-olympus-check.json) and per-component
results in the [container report](../evidence/gm5-v11-container.json).

## Older Panasonic AES key: bounded negative result

A public GH2 AES-128 key was independently checked against an official
`GH2__V12.zip` control. AES-128-CBC decoding of that older image's body, using its
stored IV, matched the **complete expected plaintext MD5**. This gives an actual
positive control, rather than trusting a key string in another project's report.

The same key was then tested against all eight GM5 payloads in three direct
layouts: CBC with the directory's 16-byte field as IV, CBC with a zero IV, and
ECB. All 24 outputs remained random-looking, with no relevant keyword strings or
matches to the corresponding 32-byte directory field under a SHA-256 hypothesis.
No failed candidate was retained as a decoded firmware image.

This is **one key and three layouts**, not an AES identification or exhaustive
decryption attempt. No key derivation or extra compression layer was tested.
The [evidence report](../evidence/gm5-v11-legacy-aes-check.json) records the control,
key source, assumptions and individual results.

The subsequent [native GH2 updater trace](gh2-update-consumer.md) independently
locates that key in GH2's own program image and follows it into the AES-CBC
consumer. Its parser requires container revision `0x101` and accepts cipher
selector 0 or 2 at header offset `0x34`; this GM5 file instead contains revision
`0x200` and value 3. The digest-selector position at `0x2c` also changes from 2
to 3. These are concrete limits on reusing the old decoder. They do not establish
what those selector values mean in GM5's still-unexamined updater.

## What remains unknown

The 32-byte directory fields do not equal SHA-256 of the encoded payloads. The
two `eep_ow` entries have the same 32-byte field but different ciphertext and
different 16-byte fields. A later [TZ30 same-format control](upd-v2-clear-controls.md)
shows that all eight of its clear entries store the exact component SHA-256 in
that position. This supports a plaintext-digest interpretation for GM5, but that
interpretation remains unverified for its encoded components. Treating each
GM5 field directly as an AES-256-CBC key with its sixteen-byte field as IV did
not produce a matching candidate digest in any component.

The inner 64-byte field at `0x220` remains uninterpreted. Field length and entropy
alone cannot assign cryptographic meaning.

CRC32 reproduction establishes a container integrity check. It does not establish
whether the camera checks signatures or keyed authentication elsewhere. No
plaintext GM5 code, cipher key, engineering menu or modified-update acceptance
has been recovered.

The next decisive input is a camera-side reader or a service tool that reveals
the actual read/update consumer. The newly acquired
[FZ30 service package](service-software-findings.md) provides a historical USB
reference; GM5 support and program-memory access remain unverified.

## Reproduce the read-only analysis

```sh
python3 tools/panasonic_upd.py firmware/official-gm5-v11/GM5__V11.bin --out work/gm5-upd-report.json --carve work/gm5-encoded-components --olympus-check
python3 -m unittest discover -s tests -p test_panasonic_upd.py -v
```

The parser checks body length, repeated headers, CRC32, directory bounds and
nonoverlapping payload ranges before carving unchanged encoded bytes. It refuses
existing outputs. The test command above is entirely offline and opens no
network sockets. The broader suite passed 21 tests once after network access was
enabled; four pre-existing integration cases used a temporary localhost HTTP
server. A macOS local-network permission prompt was reported during that work;
its precise OS trigger was not independently identified. No camera or LAN
discovery was involved in these checks.
