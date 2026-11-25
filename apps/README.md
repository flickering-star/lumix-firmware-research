# Lumix Firmware Updater
**Recording-limit removal is withdrawn.** The owner reports corrupt SD video files after recording beyond30 minutes. Rebuild and install firmware with native recording limits to remove an already installed limit patch.


**All original project code was written by a chatbot. Flashing Panasonic
cameras is risky because recovery options are limited. No independent GM1/GM5
recovery procedure is validated; a bad update can leave a camera unusable.**

Desktop application for preparing an SD firmware update. The owner requested
removal of the faulty recording-limit option and publication of the replacements.
GM1S is unsupported and is rejected by the model-specific firmware guards.

## 0.2.13 — reviewed GM1 internal 0111 profile

GM1 internal `0111` is now recognized using the owner's complete32MiB backup.
Its service code and ROM data have small relocations: the dispatcher is at
`40369f78`, the key record at `405ab478`, and the ROM-policy initializer at
`405c5b58`. The one temporary RAM-policy address remains `70903814`. The app
uses separate complete-page fingerprints and revision-specific ROM/key offsets;
the revision/build bypass remains removed.

**Existing stable and LUT patch payloads are unchanged.** The app still reads
the same official GM1 1.1 BIN, constructs the reviewed `0110`-based components
and installs those as an SD update. It does not apply `0110` patch offsets to
the relocated installed `0111` image. Displayed firmware remains1.1; this path
changes the internal program revision from `0111` to `0110`. Stock Program
Restore separately reproduces the reviewed `0111` program components for a
camera initially detected with that profile. Settings/calibration are excluded.

Validation includes all32,768 backup block hashes, exact host profile/refusal
checks, original `0111` service-code read/store/ACK execution and complete
package encode/decode comparisons. Physical installation on this body has not
been tested. See the [GM1 profile review](../docs/gm1-0111-updater-profile.md).

## 0.2.12 — strict profiles and recovery backups

The revision/build skip has been removed. Patching requires the exact reviewed
GM1 internal `0110`/`0111` or GM5 internal `0110`/`0111` profile. Displayed firmware
"1.1" is not an internal build identifier. A dispatcher mismatch means required
code was not recognized at its expected address; it does not identify the cause
or establish that every possible patch is incompatible. The retained GM5 `0111`
reference passes the exact profile checks. GM1 `0111` support was added in0.2.13.

**Data backup / Resume** saves a complete camera backup for later recovery if
something goes wrong. It is available on the Camera tab even if firmware
inspection fails. It reads the entire mapped 32 MiB flash window, addresses
`40000000–41ffffff`, using fixed 1 KiB read requests. It does not change the
camera or enable updates. Choose an empty folder for a new backup, or the same
folder to resume. Verified blocks are flushed before their durable checkpoints;
resume checks local block hashes, camera identity and three source anchors.
Corrupt saved data or changed anchors are refused. Pause and window close save
the current block; a disconnect leaves the completed blocks available to resume.

Before starting in service mode, use normal camera mode and set
**MENU/SET → Setup (wrench) → Economy → Sleep Mode → OFF**. Then reconnect in
service mode. See Panasonic's [GM1 advanced manual, page 49](https://help.na.panasonic.com/wp-content/uploads/2023/02/DMCGM1_VQT5D68_ENG.pdf)
and [GM5 advanced manual, page 69](https://www.panasonic.com/content/dam/Panasonic/support_manual/Digital_Still_Camera/English/DMC-GM5_Operating_Instructions_for_advanced_features.pdf).
The app displays these instructions without changing the setting. Keep the
computer awake and use stable camera power. The copy can take an hour or more.

The completed file is `flash32m.bin`, exactly 33,554,432 bytes, with a final
disk-read verification, SHA-256 and report. Partial copies use
`flash32m.bin.part`; keep the whole folder for resume. This is a sequential
mapped-flash copy. Its intended recovery route is conversion to the camera's
AHX format; conversion and physical restoration have not yet been validated.
The raw backup is not directly installable as an update BIN or AHX file. It can
include camera-specific settings, calibration and identity data; keep it private.
The owner's GM1 `0111` backup is complete and all32,768 saved block hashes have
been checked. The app's firmware patch choices are unchanged.

## Previous release 0.2.10

Both apps are version0.2.10 and were compiled from source on their target
systems. The recording-limit checkbox, implementation and catalog variants
are removed. Newly prepared firmware preserves native recording limits.
Windows uses the exact USB library from the tested0.2.5 release. Camera read,
USB enable and retry behavior follows the0.2.5 workflow.

Both patch choices expose all26 native firmware languages on GM1 and GM5.
IDs and ordering come from the firmware. See
[implementation and validation](../docs/lumix-all-languages.md).

- [macOS Apple Silicon](https://github.com/flickering-star/lumix-firmware-research/releases/download/updater-v0.2.10/Lumix-Firmware-Updater-darwin-arm64.zip)
- [Windows x64](https://github.com/flickering-star/lumix-firmware-research/releases/download/updater-v0.2.10/Lumix-Firmware-Updater-win32-x86_64.zip)
- [Checksums and release notes](https://github.com/flickering-star/lumix-firmware-research/releases/tag/updater-v0.2.10)

After an unrecognized revision or build error, press and hold **Read camera**
for five seconds to check layout compatibility instead of matching the installed
build. A short click repeats the normal exact-build check. Releasing early or
moving the pointer off the button cancels the hold.

The retry ignores header metadata and unrelated bytes on firmware pages. It
checks the service dispatcher, the read/write dispatch entries, the memory-read
handler and the direct halfword-write path, including its addressing-mode
reference. It also checks the actual ROM-to-RAM policy mapping and the updater's
use of that policy. A small function shift in the reviewed GM5 updater window
is accepted without requiring a revision-specific header fingerprint.

Model, encryption-key record, policy values and service state are still checked.
Enable repeats layout validation before its one fixed RAM halfword write and
checks the complete RAM page and the actual ROM page afterward. It does not
compare the ROM page to a reviewed build when using this override.

The report records layout-only verification separately from an identified
build, both actual revision words and the reviewed source profile used for
preparation. The update and stock restore use that reviewed source; stock restore
does not reconstruct an unknown installed build. Offline controls cover109 cases
across three real private firmware inputs; no physical override result is
claimed. See the [compatibility evidence](../evidence/lumix-updater-layout-compatibility.json).

GM1 LUTs now always apply at100% with no adjustment rows. All opacity-only
hooks, settings handlers, numeric/scale drawing and blending are removed.
The owner found the no-opacity firmware usable, though slightly slower than
native styles. The new build also prevents button/touch navigation into an
invisible adjustment row. GM5 keeps its existing opacity control.

**Enable this update** remains available after each attempt. If the camera
sleeps, restarts or disconnects before installation, reconnect service USB and
use the same button again. The prepared firmware stays available; each attempt
rechecks the saved file and connected camera before any flag write. The button
is disabled while an operation is running. Disconnect USB before pressing
Playback to check for the update on the camera.

The new source adds **DMC-GM1 firmware 1.1/internal 0110**, alongside GM5
official 0110/factory 0111, with separate complete-page guards, encryption-key
locations, RAM policy addresses, component geometry and output filenames.
An identical USB product ID never establishes model compatibility.

Both model catalogs include language/update-access patches, experimental
LUTs with FAT32 import, and a stock-component restore. The exFAT overlays are
withdrawn. The recording-limit removal option has been withdrawn after the owner reported
corrupted video files beyond30 minutes. Version0.2.8 source removes its checkbox,
patch implementation and catalog variants. Newly prepared firmware preserves the
native recording limits. If the older patch is installed, prepare and install a
new language or LUT update to restore those native checks. Previously prepared
files keep their old contents and should be replaced.

Both models expose their complete existing26-language catalogs. Both LUT targets
restore their internal saved cells at startup without scanning the SD card.
Both LUT updates stop before their saved-bank sectors, preserving imported
cells and GM5 opacity. GM1 ignores the former saved opacity bytes and applies
full-strength tables. GM1 uses the native pool10 backing and the corrected
dispatcher/producer stack frames. GM5 retains its owner-tested adjacent-manager
build. Neither model changes settings/calibration components or installs an
independent recovery loader. The unfinished 65:24 work is excluded.

The owner requested direct publication after withdrawing the recording-limit
option. The0.2.4 apps retain the
GM1 opacity path with severe reported menu/control delays. Current GM1 firmware
uses fixed100% strength and may still show brief colored vertical lines after
Import/No LUT. GM5 retains the tested LUT implementation. Long-session and
complete recording-format coverage remain incomplete. Use the model-specific
filename selected by the app. Official BIN/ZIP inputs are hash checked; if the
download fails, select the matching official local file.

Runtime self-tests and GUI checks for these fresh source archives were skipped
at the owner's request. The source language patch has its separate native and
independent-decoder validation. The preceding Mac0.2.6 and Windows0.2.7 archives were accepted by the owner.
These0.2.10 archives have no new reported camera test. Exact body
identities and detailed per-language font/reboot coverage were not supplied.
See the [release record](../evidence/lumix-updater-0.2.10.json).

## Previous release0.2.7

- [Previous apps with recording-limit withdrawal warning](https://github.com/flickering-star/lumix-firmware-research/releases/tag/updater-v0.2.7)

Its recording-limit option is withdrawn after the corrupted-video report.
Use a newly prepared0.2.8 update to restore native limits on affected cameras.

## Previous release0.2.5

- [Previous app archives and test record](https://github.com/flickering-star/lumix-firmware-research/releases/tag/updater-v0.2.5)

This release introduced fixed100% GM1 LUT strength and retains the earlier
regional language subsets. The current release uses the complete26-language
catalog on both models.

## Previous release0.2.4 — GM1 performance warning

- [Mac and Windows archives, checksums and warning](https://github.com/flickering-star/lumix-firmware-research/releases/tag/updater-v0.2.4)

This previous release includes GM1 Opacity. The owner reports severe delays
with that path. Version0.2.5 removes opacity for GM1 and supersedes these apps.
GM5 retains opacity and its tested firmware target.

## Original GM5-only version 0.1.1

- [macOS Apple Silicon](https://github.com/flickering-star/lumix-firmware-research/releases/download/updater-v0.1.1/Lumix-Firmware-Updater-darwin-arm64.zip)
- [Windows x64](https://github.com/flickering-star/lumix-firmware-research/releases/download/updater-v0.1.1/Lumix-Firmware-Updater-win32-x86_64.zip)
- [Checksums and release notes](https://github.com/flickering-star/lumix-firmware-research/releases/tag/updater-v0.1.1)

The owner reports successful update workflows with both desktop versions on
Japanese and global GM5 models. The files published here are the exact version
0.1.1 archives supplied for those tests. See the
[validation and owner-test record](../evidence/lumix-updater-0.1.1.json).

Version 0.1.1 adds the official `0110` profile. Two owner-connected GM5 bodies,
one Japanese and one global, matched all six checked ROM pages of that official
build. Their key and update-policy addresses match the first research camera.
The previous app supported only `0111` and incorrectly refused these cameras.
Each revision has its own complete-page checks; unsupported or mixed builds
still fail without a camera write.

The app reads the connected service camera, validates the firmware profile,
recovers its update encryption key in memory and checks the ROM/RAM update
policy. It downloads the pinned official update or accepts an official BIN/ZIP
whose SHA-256 matches. It prepares the chosen update and a separate stock
program restore, with checksums and installation instructions.

Stable and LUT patches use the reviewed `0111` program components. Starting
from `0110` changes the internal program revision to `0111`; the displayed
firmware version stays 1.1. The separate stock restore prepared in that session
matches the detected starting profile (`0110` or `0111`). Keep that folder if
you want to return to the exact starting build; a later inspection identifies
the currently installed profile.

Choices are language unlock with permanent custom-update access, experimental
LUTs, and stock program restore. The LUT choice is currently the `fa17315e`
memory-allocation test. It has passed offline checks, and the owner confirmed
LUT video recording plus Library/Playback afterward. Recording-format and
long-session coverage remains incomplete. Detailed limitations are displayed
with the prepared update.

The app guides copying `GM5__V11.bin` to a camera-formatted card and inserting
it while the camera is off. If the ROM policy is stock, reconnecting service
USB allows one checked temporary RAM flag change. The owner then unplugs USB
and performs the update through Playback. An already modified ROM needs no
temporary change. The app does not select Yes or program camera flash over USB.

Stock restore reinstates the original language lock and signed-update policy
and clears saved experimental LUTs. It preserves camera settings/calibration
components. Reset the camera settings while patched firmware is still running,
before installing the stock restore. It requires the ordinary updater and is
not independent recovery.

## Desktop packages

The macOS package is a standalone `.app` in a ZIP. The Windows package is a
standalone application folder in a ZIP; extract the entire folder before
running its EXE. End users need neither Python nor a compiler.

Use an awake camera in service mode. Windows requires WinUSB on the exact
camera service interface (`04DA:2370`); the app does not change drivers. The first
inspection only reads camera memory. A camera profile is rechecked after
reconnection before the temporary policy change.

## Using the app

1. Extract the Mac app or the entire Windows application folder, then open it.
   Keep the Windows `_internal` directory beside the EXE. End users do not need
   Python or a compiler.
2. Connect an awake supported GM1/GM5 through service USB and choose **Read camera**. Select
   the stable language/update-access patch, experimental LUTs, or stock restore.
3. Prepare the update in a new folder. The app downloads the pinned official
   firmware; if unavailable, supply the matching official GM1/GM5 1.1 BIN/ZIP. Other hashes
   are refused. Keep the prepared folder and its separate `stock-restore` copy.
4. Copy the model-specific `GM1__V11.bin` or `GM5__V11.bin` to the root of a camera-formatted SD card. Select Standard
   on the camera, switch it **off**, and insert the card. Use a fully charged
   battery.
5. Follow the app's instructions. A stock camera needs service USB and
   **Enable this update** after inserting the card. Then unplug USB while
   keeping the camera awake and powered on. A compatible patched camera needs
   no temporary RAM change.
6. Press Playback and confirm installation on the camera. Keep power stable
   until it finishes and follow the camera's restart instruction.

The app relies on an already available service interface. See the
[GM5 USB research](../docs/gm5-flashing.md) and
[manual reproduction guide](../docs/gm5-reproduction.md) for the underlying
checks and limitations. These downloads cover Apple Silicon and Windows x64;
no Intel Mac build is provided. The Mac app has a local ad-hoc signature rather
than Apple notarization; the Windows app is not code-signed.

Packages contain the application, native libraries and bounded patch deltas.
They contain no full Panasonic firmware, camera backup, or camera encryption
key. Official input and reconstructed components are checked locally.

## Building

Build on the target OS with 64-bit Python 3.11 or newer, Tk, the dependencies
in `requirements-updater.txt`, and a C compiler. macOS uses clang; Windows uses
the Visual Studio x64 Native Tools prompt or 64-bit MinGW. The checked-in
`lumix_updater/patches` directory contains the same catalog and seven bounded
deltas as the tested apps. No complete firmware or camera key is included.

```sh
python -m pip install -r apps/requirements-updater.txt
python -m unittest tests.test_lumix_updater tests.test_lumix_updater_release -v
python tools/lumix_updater_bundle.py --assets apps/lumix_updater/patches --out /private/new-updater-build
```

On Windows, use a new Windows output path instead of `/private/...`, and run
the build in an interactive desktop session. The frozen GUI check must be
able to create real windows. Alternatively, `tools/lumix_updater_windows_kit.py`
can package a minimal build kit with its PowerShell build script. Tested
build environments used Python 3.14/Tk 9 on macOS and Python 3.12/Tk 8.6 on
Windows. Rebuilt binaries are not expected to have identical archive hashes.

The bundler runs the frozen codec, patch-hash, libusb-loading and TLS-root
self-tests, then opens the actual GUI for a layout smoke check. None of these
checks opens a camera or verifies the physical USB workflow. Native firmware
output verification and explicit fixture-camera workflow controls are separate
tools in the repository. The supplied
[portable workflow probe](../tools/lumix_updater_workflow_probe.py) needs private
firmware fixtures and accepts their paths explicitly. It uses a declared fake
camera peer; its memory operations are not physical USB measurements.

This is an unmaintained reference archive. Contributions and support requests
are not accepted; see the [archive policy](../CONTRIBUTING.md).
