# GM5 AHX recovery from a full same-body backup

On November 26, 2026, the owner reported that their GM5 was bricked. A complete
backup from that same body was encoded as `GM5.AHX`, with one update-policy byte
changed. After the file was copied to the SD card and verified, the owner
reported **"restored"**. This is an owner-confirmed GM5 recovery through AHX.

**Make and verify a complete backup of your own camera before any firmware
modification.** For GM1/GM5 this means the entire 32 MiB mapped flash, including
the body's settings, identity and calibration. Keep an untouched copy off the
camera's SD card. The desktop app's **Data backup / Resume** option reads that
window and retains checkpoints so interrupted acquisition can resume. Set
Sleep Mode to OFF as instructed by the app and verify acquisition is complete.
An official firmware BIN is not a substitute for a full same-body backup.

The recovery result is owner-reported. No post-recovery USB inspection or full
32 MiB readback has been performed for this GM5 case. Recovery does not establish
that every damaged camera can enter AHX: the path depends on surviving startup,
card and programming code in the installed firmware.

## What was restored

The source backup contains 33,554,432 bytes and was captured on November 6 UTC.
Its original internal revision is `0x0111/0x0111`. Before preparing the recovery
file, the internal serial in an original photograph from the affected camera
was matched to the backup's fixed calibration record. A filename or the displayed
firmware version alone was not used to identify the body. Serial values and
the photograph remain private.

The only changed payload byte is at flash offset `0x006b1bdc`, mapped address
`0x406b1bdc`: `01 → 00`. Original startup initializes the corresponding RAM
policy at `0x70a68490`. This policy concerns update acceptance; it is separate
from the programmer's range-selection mode below. The image comes from the
original backup and does not contain the later aspect-ratio or LUT patches.

Every other payload byte, including all 384 KiB of the settings/calibration
tail, was retained from that backup. **The calibration sectors were nevertheless
erased and rewritten by the stock full-image route. They were not skipped.**
The owner requested the SD copy after this limitation was explained.

| Artifact | SHA-256 |
| --- | --- |
| Original full backup | `c51dca467a8bd24c0be75915acb54692f9213a7d7b9896c5e50a010d830a35ca` |
| Policy-zero decoded image | `672d389bb8f09a551c0889e66d911ff307932768ed37221cd727d68abc28b67a` |
| Recovery `GM5.AHX`, 100,663,312 bytes | `14b5071b0c52a75e39ca7921f3fed56271068bfe190b26d0fe1c6959bab13aac` |

These identify this private experiment; they are not generic firmware downloads.
The backup, AHX file, calibration data, keys and raw captures are not published.
See the [sanitized case evidence](../evidence/gm5-ahx-recovery.json).

## How the updater modes work

The native GM5 programmer chooses fixed flash ranges from its mode argument.
All offsets below are hexadecimal and their ends are exclusive.

| Writer mode | Flash offsets programmed | Effect on the final data sectors |
| --- | --- | --- |
| 0: full image | `0x0000000..0x2000000` — all 32 MiB | Erases and rewrites them |
| 1: application prefix | `0x0000000..0x1fa0000` — first 31.625 MiB | Leaves the final 384 KiB unwritten |
| 2: data tail | `0x1fa0000..0x2000000` — final 384 KiB | Erases and rewrites only those sectors |

The tail includes settings/history and the fixed adjustment/calibration component
at `0x1fe0000..0x1fec000`. It is not the AHX updater itself. The updater's main
and secondary code lies in the application prefix, so even mode 1 rewrites the
firmware on which this recovery path depends.

**The stock `GM5.AHX` entry selects mode 0. An AHX file cannot select mode 1
by changing a header, its S3 addresses, its length or its filename.** At
`0x40133603` the normal caller clears the mode; `0x4013369f` passes it to the
wrapper at `0x7bd24722`. The mode is stored at `0x703690e9`. The writer's tail
gate at `0x7bd2507b` skips the tail only when that value is 1.

`GM5E.AHX` is a separate extended fallback. The caller tries it only when
opening `GM5.AHX` returns the file-open failure value `0xffffffff`; a parsing
failure does not select it. A successful extended fallback passes mode 3 and
skips the normal staging-preservation block. It does **not** select the
calibration-preserving application-only mode: mode 3 continues into the tail.
There is also a startup job mode 1 for a separate marker branch; that number
must not be confused with selecting programmer mode 1 through an AHX file.

Using application-only programming would require changing the updater code
that is already executing, or reaching another caller that actually supplies
mode 1. Putting such a change inside the incoming AHX image only affects later
runs; it does not change the writer currently installing that image.

The normal wrapper also copies selected live settings into staging before
programming: 20,480 bytes at offset `0x1fe0000` and 504 bytes each at
`0x1fa1e00` and `0x1fc1e00`. This is not sector exclusion. It also means the
input file's byte-for-byte verification must not be presented as a complete
post-recovery flash readback.

## File structure and entry

AHX is a raw flash-layout image represented by ASCII Motorola S3 records. It
is not the consumer BIN renamed or hex-encoded. Each 48-byte text record has
`S315`, an eight-digit image offset, sixteen data bytes as 32 hexadecimal
characters, a checksum and CRLF. Offsets begin at zero and advance by 16.
The checksum is the one's complement of the byte sum of the count, address
and data. The tested 32 MiB file has 2,097,152 data records, followed by
`S70500000000FA\r\n`. The S7 address is not executed by this route.

The decoded GM5 key predicate identifies **Playback + Q.Menu/Delete/Return +
UP held while switching on**, with the card/startup gates also satisfied; it
does not require a mode-dial position. The owner did not separately restate the
button sequence or LED timings for this GM5 recovery, so those details are not
recorded here as a new physical button/timing measurement. The same combination
was separately [physically demonstrated on GM1S](gm1s-ahx-policy.md).

The writer uses fixed ranges, not the decoded file length, to bound its source
reads. A shortened application-only file on an unmodified mode-0 camera can
therefore reach missing staging data after erasure has already begun. Omitting
records or supplying `ff` bytes is not a way to preserve flash sectors.

## Evidence and recovery limits

Before copying, both the policy-zero image and an unmodified backup encoding
were independently decoded and compared across all 32 MiB. Eleven focused native
cases checked the initialized policy, first/policy/last S3 records, normal and
extended caller modes, and the tail gate for modes 0/1/2/3. Earlier full virtual
NOR controls checked the complete fixed ranges for modes 0/1/2. The source
capture's framing/checkpoints and resumed prefix were also revalidated. The
completed SD file's SHA-256 matched the prepared candidate.

The owner then reported successful restoration. This is useful recovery
evidence for this body and failure case, but no independent processor-ROM or
blank-flash recovery has been demonstrated. The failure's exact corrupted
regions were not captured. The policy value and calibration contents after
recovery have not been read back. A backup improves recovery options while
the relevant entry still works; it cannot make that entry survive every
possible firmware failure.
