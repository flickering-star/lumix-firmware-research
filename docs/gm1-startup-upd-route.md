# Successful GM1 startup UPD flashing

On November 28, 2026, the owner confirmed successful GM1 flashing through the
startup `.upd` route, using the existing GM1 LUT update renamed to **`GM1.upd`**.
The camera was already running LUT firmware with unsigned-update policy disabled.
This is separate from normal Playback-menu updating and the ASCII AHX loader.

It provides a potential recovery route when the normal UI cannot start, while
allowing an update package to exclude body calibration. Recovery of an actually
bricked GM1 through this route has not yet been demonstrated. **Make and verify
a full same-body backup before firmware modification.**

## Filename and entry

The owner's reported entry combination is **Q.Menu + UP + Playback held while
switching on**, with the file in the SD card root. The final filename must be
`GM1.upd`. The first unsuccessful attempt actually used `GM1.upd.bin`, which
does not match the startup lookup. Check the full filename, including extensions
hidden by a file manager.

The normal BIN is renamed without converting its contents: `.upd` uses the
normal update container, not Motorola S-record text. The firmware searches for
`GM1e.upd` first, then `GM1.upd`. The extended name selects a different request;
the reviewed package fails its early header gate under that selector. The
successful route uses the plain name.

No LED timing or new readback was recorded for the successful attempt. The
earlier brief blinking/normal-boot observation belongs to the incorrectly named
file and is not evidence of a signature rejection.

## Calibration depends on the package's write ranges

The reviewed last released GM1 LUT package has three update components:

| Component | Flash offset start | End, exclusive |
| --- | --- | --- |
| `program` | `0x0000000` | `0x0880000` |
| `guires` | `0x0900000` | `0x1400000` |
| `program2` | `0x1400000` | `0x1760000` |

These writes exclude the final 384 KiB settings/calibration area at
`0x1fa0000..0x2000000`. The shortened main component also excludes saved LUT
banks. The reviewed container's SHA-256 is
`a528d4f7c873d10be9a0bd57d50f86b97b2dadfdbbb7920ab993977fa509f900`.
The owner's on-card hash and post-update calibration were not independently
read back; package identity follows the description of the last released LUT BIN.

**The `.upd` extension does not enforce calibration preservation.** A different
package containing `eep` or another entry targeting that area could overwrite
it. Renaming an arbitrary official BIN does not make it application-only.
In contrast, the demonstrated stock GM5 [AHX recovery](gm5-ahx-recovery.md)
selects full-image mode 0 and rewrites calibration from that body's backup.

## Startup position and validation

GM1 startup calls AHX job `40158fe8` at `4005000a`. **If that job returns**, the
next call at `40050011` enters UPD wrapper `7bd97b79`. Model getter `4028bb25`
supplies `GM1`. After lookup, call `7bd97cc1` enters normal update job
`7bd4a254`. An AHX operation that programs and resets does not reach this
continuation.

This runs before ordinary UI startup, but still needs surviving main/secondary
firmware, SD access, decoding and flash-programming code. It is not independent
processor-ROM recovery and cannot recover blank flash by itself.

The filename does not disable authentication. The shared job reads policy byte
`70903814`; zero enables the unsigned allowance at context offset 92. The
reviewed LUT package also has a zero inner marker, selecting the existing ECDSA
skip branch. Stock policy rejects that unsigned format, and a nonzero signed
marker still follows verification. Model/header/CRC and component decoding
remain relevant. This success does not establish unsigned flashing on stock
firmware.

Four offline native calls totaling 1,160 instructions pass the released package
through the early header gate under normal selector 2, reject extended selector
3 and a wrong model, and show signature processing is later. They are separate
from the owner report. See the [case evidence](../evidence/gm1-startup-upd-route.json).

## Other cameras and evidence limits

GM5 has a separately traced wrapper `7bda76c8`, reached at `4001d701` after AHX
job `40133485` returns. It searches `GM5e.upd`, then `GM5.upd`, and calls normal
update job `7bd4fb93` with its shared signature policy. **GM5 startup UPD flashing
has not been physically confirmed in this record.** No GM1S or GX9 success is
inferred from the GM1 test.

The agent performed no camera, USB, SD-card or flash operation while documenting
this result. Firmware binaries, backups, calibration and raw captures remain
unpublished.
