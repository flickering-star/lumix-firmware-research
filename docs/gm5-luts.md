# Experimental GM5 real-time LUT patch

**All original project code was written by a chatbot. Flashing Panasonic
cameras is risky: there is no validated independent recovery path for this
GM5. A bad update or interrupted flash can leave the camera unusable. An
ordinary rollback file cannot recover a camera whose updater no longer runs.**

This patch targets only the reviewed Japanese DMC-GM5 factory 1.1 build
(internal version `0111`). It adds ten LUT cells, a Setup → LUT Library menu,
root-directory SD import, native Photo Style/Quick Menu selection and an
Opacity control. It includes the existing language unlock and permanent
custom-update policy. It does not add a separate EIR style: a channel-swap
LUT provides that transform.

The owner confirmed importing VLT and CUBE files, correct color output,
row touch, still JPEG operation and saved LUT restoration. On the latest
`fa17315e…` build, the owner also confirmed LUT video recording and working
Library/Playback afterward. No recording format, long-session duration or
complete compatibility sweep was specified. See the [owner result](../evidence/gm5-lut-adjacent-manager-camera-result.json).

## What it changes

- Ten saved LUT cells appear as Photo Styles after import. LUT Library uses
  native list behavior, row touch, Back, file selection and Standard confirmation.
- The picker lists compatible files in the SD card's root, without a full file
  browser. Use short ASCII 8.3 filenames (`SWAP.VLT`, `CYAN.CUB`, etc.).
- LUT data is resampled to the camera's 9×9×9 processing table with 6-bit output
  values. The existing native image processor consumes the resulting table.
  This is not a software pixel filter or a bit-for-bit port of newer Venus hardware.
- Opacity uses the native slider and 0–10 readout. Standard is selected before
  import or clearing a cell to avoid replacing an active LUT's data.
- Two internal 128 KiB banks hold saved LUT state. Startup restores these banks;
  it does not scan or parse LUT files from SD. The update excludes those banks.
- Controller, retained tables and processing frames use one owned allocation
  from the original general image-memory manager. Its 128 KiB request rounds to
  a native 2 MiB unit. Transient parser/directory workspaces use original region 1.
  Video buffer sizes and original allocator/filesystem implementations are unchanged.

The two image-memory managers both participate in recording setup. Earlier
retained-pool placements were overwritten during recording. This revision
uses the other manager's actual allocation record and passes the original
memory-plan checks; the later owner video result is separate camera evidence.
Neither native checks nor the owner report prove physical mapping for every
recording configuration.

## Reproduce the exact update locally

Obtain your own complete, packet-verified **32 MiB camera NOR backup**, the
official GM5 1.1 BIN/ZIP, and a local C compiler. Follow the existing
[backup and bootstrap guide](gm5-reproduction.md). Keep the body-specific
backup privately; do not use another body's settings or calibration.

The recipe accepts the three exact main baselines already documented in the
language guide: original factory, policy zero, or the tested language patch.
It also requires exact factory menu-resource and secondary-program hashes.
An unknown or already altered component is refused. Keep the original backup
even after installing custom firmware.

```sh
mkdir -p work
cc -O2 -std=c11 -Wall -Wextra -Werror tools/panasonic_aes5.c -o work/panasonic-aes5
python3 tools/gm5_lut_package.py --firmware /path/to/GM5__V11.bin --backup /path/to/your-flash32m.bin --codec work/panasonic-aes5 --out work/gm5-lut-update
```

Windows can build the same codec with a local C compiler and use its `.exe`
path. Python 3.10 or newer is required. ZIP input must contain the single
official `GM5__V11.bin`; member paths are never extracted to disk.

The official BIN SHA-256 is
`d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243`.
The generated update must be exactly **24,118,784 bytes**, SHA-256
`fa17315ef8527dfad4bd72444caac786fe0a2e96d85e4802e26c68995989597d`.
The tool checks every replacement preimage and full output hash, runs full
component codec round trips and verifies the final container directory.
It never contacts a camera, copies to an SD card or starts installation.

The key is recovered from the exact checked page in your backup; it is not
bundled in this patch or written into the result report. The local codec is
invoked as a subprocess, so its arguments are visible to local process-inspection
tools while it runs. Keep this preparation on a trusted machine.

## Installation boundary

This is an unsigned update. A stock running updater must first have its
reviewed temporary RAM policy enabled through service USB, as described in
the [GM5 guide](gm5-reproduction.md). The policy contained in the new firmware
cannot authorize its own initial installation. A camera already running
persistent policy zero normally needs no temporary change.

Confirm Standard, switch the camera off, copy the verified `GM5__V11.bin` to
the root of its camera-formatted card, verify the copied hash and safely eject.
Insert the card with the camera off. Use a fully charged battery, follow the
existing Playback updater procedure and keep power stable until completion.

Afterward, check restoration, Library import, row touch, a JPEG and normal
off/on. Then test LUT video, stop recording, and check Library and Playback.
The header advertises `1.1f`; the installed version remains `1.1`. A prompt
alone does not prove installation.

The main programming prefix ends at `0x7a0000`; saved banks at `0x7a0000`
and `0x7c0000` are excluded. The GUI and secondary program are included, but
settings, body calibration and ARM components are excluded. That separation
does not provide recovery if executable startup or update code is damaged.

## Source and evidence scope

The [guarded byte recipe](../recipes/gm5-v11-luts.json) is the exact reproducible
installation artifact. It contains bounded before/after replacements, not
complete firmware images. The offline builder starts from the owner's checked
components. Key native subsystems are supplied as [review sources](../research/gm5-luts/README.md).
These assembly files alone are not a complete stock-firmware build system;
the guarded recipe is authoritative for this exact release.

The private research environment checked ten-cell restoration, independent
processing-frame copies, transient allocation/release, row hit validation and
Back, real allocation exhaustion/recovery, three original recording memory
plans, and candidate/rollback installation with errors and interrupted writes.
Original UI-task execution reached its first receive after 101 stages and
48 checked native stack restores. Summaries are in the [release evidence](../evidence/gm5-lut-release.json).
The raw firmware/camera fixtures are withheld; these summaries are not a
public full-camera emulator or proof of complete cold boot/LCD/encoder behavior.

This remains an unmaintained research archive. Reproduce and extend it in
your own fork; contributions and support are not accepted.
