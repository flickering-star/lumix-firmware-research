# GM1S AHX update: confirmed policy change

The owner successfully activated the GM1S AHX updater and installed a full
same-body image whose only intended change was the stored update policy.
Read-only USB inspection afterward confirms **flash policy 1 → 0 and RAM
policy 1 → 0**. This demonstrates an actual GM1S AHX installation, beyond locating
a filename/parser in the firmware.

The tested body identifies as **DMC-GM1S**, with internal revision **0106/0106**.
These results do not establish compatibility with GM1 binaries or patches.
Firmware files, full device backups, keys and raw captures are not distributed.
See the [sanitized evidence](../evidence/gm1s-ahx-policy.json) and
[offline readback verifier](../tools/gm1s_ahx_readback_verify.py).

## Activation and observed sequence

With `GM1S.AHX` in the SD card's root, the successful combination was:

**Hold Playback + Q.Menu/Delete/Return + UP while switching the camera on.**

The owner reports that the camera did not open the normal menu. The power LED
blinked for several minutes, then the front lamp remained on for several
minutes, and the camera restarted automatically. Those stages and timings are
owner observations, not measurements of specific internal updater phases.

GM1S's own startup code agrees with that combination. Predicate `0x7bd42c36`
requires cached cross-key halfword `0x7036ef70` and rear-key2 halfword
`0x7036ef80` in 221..353, plus rear-key1 halfword `0x7036ef7e` in 0..66. The
combined decoded mask must include `0x88`. Card gate `0x7bdf5677` must return 1
inside the predicate and again at startup `0x4001d6cf`; its initial check requires
GPIO `0x9c00c0a0` bit `0x0200` clear across ten polls, followed by card setup.
Startup then invokes job `0x40132f79` with mode 0 at `0x4001d6e3`. This key
predicate does not test a mode-dial position.

## Policy location and measured result

| Location | Address | Before | After AHX restart |
| --- | --- | --- | --- |
| Stored policy initializer in flash | `0x40692634` | 1 | 0 |
| Initialized policy in RAM | `0x70a4ebc4` | 1 | 0 |
| Native flash-type byte | `0x701a76ed` | 4 | 4 |

The original initialized-data loop at `0x40003000..0x4000301e` copies
`0x406318b0..0x406bd7bc` to `0x709ede40`. The stored/RAM relationship is:

```text
0x406318b0 + (0x70a4ebc4 - 0x709ede40) = 0x40692634
```

Updater instruction `0x7bd4e76f` reads that RAM byte. A zero policy causes
`0x7bd4e806` to set context offset 112, enabling the existing zero-marker
unsigned-input branch. With stock policy 1, that marker is rejected with
`0x80000065`; a nonzero signed marker still follows the signature path.
Focused execution of original GM1S instructions verified the copy, policy
load, allowance selection and unsigned decision for both values.

Before/after inspections each used five fixed 1 KiB memory reads. All ten saved
responses passed framing/checksum and source-file consistency checks. The
entire flash policy page changed at **exactly one byte**, `0x40692634`, from 01
to 00. The header page and sampled fixed calibration page remain byte-identical
to the original backup; the live flash type remains4. No USB policy write was
sent by either inspection.

The USB serial descriptor is empty. Product/descriptor equality alone is not
a unique body identifier; matching source pages provide additional agreement
with the retained backup. This check covers selected pages, **not a complete
post-update 32 MiB readback**. Readback followed the updater's automatic restart;
an additional controlled manual power cycle has not been performed.

## The tested AHX image

The source is the owner's complete 32 MiB mapped NOR backup. The candidate
changes only file offset `0x692634` from 01 to 00 and preserves every other payload
byte, including that body's settings/calibration. The original image was also
encoded as a separate rollback file. Both use the normal filename`GM1S.AHX`.

AHX contains a raw flash-layout image encoded as ASCII Motorola S3 records.
It is not the official encrypted consumer BIN container converted to text.
Each record encodes 16 data bytes and occupies 48 text bytes:

```text
S315 + 8 hex address characters + 32 hex data characters + 2 checksum characters + CRLF
```

Addresses are sequential **image offsets starting at zero**, not mapped CPU
addresses. The checksum is the one's complement of the sum of the count,
four address bytes and sixteen data bytes. After 2,097,152 data records, the
file ends with `S70500000000FA\r\n`. Total file length is **100,663,312 bytes**
(`0x6000010`). Both complete files were independently decoded and compared
against every expected source byte before testing.

| Artifact | SHA-256 |
| --- | --- |
| Original 32 MiB backup | `31a976014477704164844ccb9618bf5e920f50a0cc250ecf824ca9189d5f3230` |
| Candidate decoded 32 MiB | `7cda3e36c9e25f69a7283eb72aef62c5472853f7daf94663563068acd7172668` |
| Candidate `GM1S.AHX` | `69fab144d429cf85a62f9932423eedb9beeb3c2838fbb985c0f0710507aa4c8f` |
| Original rollback `GM1S.AHX` | `337bc311f117827a145a6a011412519d28aa7f507c973988262038fe39f2600c` |

GM1S reader`0x40237952` calls parser `0x40237b77` and stages at `0xb3200000`.
It uses a 48-text-byte/16-data-byte stride and requires at least `0x600010` file
bytes. The caller checks the decoded extent through `0x40133266`. Full 32 MiB
passes flash types 3/4/5; the connected body reported type 4. Original parser
execution also accepted the actual first, policy-containing and last data
records before the physical test.

The normal file selects wrapper mode 0. Its caller at `0x40133194` passes
block value `0x40000` to `0x7bd23603`. The 32 MiB writer branch traverses the code
prefix `0..0x1fa0000` and tail `0x1fa0000..0x2000000`. Mode1 skips the tail;
mode 2 skips the prefix. The tested normal file does not select those modes.
The reader tries `GM1SE.AHX` only when `GM1S.AHX` cannot be opened; a successful
fallback selects wrapper mode 3. A parsing failure does not select the fallback.

## Recovery boundary

This is a useful, physically demonstrated path for loading a full same-body
backup while enough existing firmware still starts. It rewrites code and data
despite the candidate's one-byte difference. AHX itself depends on existing
startup/main/secondary code, card services and programming routines. Damage
to those dependencies can prevent reaching it again. This is not independent
processor-ROM recovery, and restoration after deliberately damaged firmware
has not been tested. The original rollback file has not been installed.

## Verify the retained readback evidence offline

With the original private backup and both capture directories:

```sh
python3 tools/gm1s_ahx_readback_verify.py \
  --backup /path/to/original/nor-window.bin \
  --before /path/to/gm1s-policy-before-ahx \
  --after /path/to/gm1s-policy-after-ahx \
  --out /path/to/new-readback-report.json
```

The verifier pins the original backup, validates all saved requests/replies,
checks payload/report hashes, verifies the one-byte policy-page difference,
and compares header/calibration/type guards. It performs no device I/O and
exports no raw memory contents or serials. Capture consistency is not an
independent hardware attestation.
