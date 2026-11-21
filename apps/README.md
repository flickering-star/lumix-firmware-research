# Lumix Firmware Updater

**All original project code was written by a chatbot. Flashing Panasonic
cameras is risky because recovery options are limited. No independent GM1/GM5
recovery procedure is validated; a bad update can leave a camera unusable.**

Desktop application for preparing an SD firmware update. The published 0.1.1
release supports the reviewed GM5 profiles described below.

## Development version 0.2.4

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
withdrawn. A separate
experimental option removes the reviewed regional 1,799-second recording policy
and selects the original longer fallback for a separate format-dependent cap.
It does not remove card-capacity, filesystem, encoder or thermal safeguards;
physical long-recording/file-segmentation testing is outstanding.

GM1's language patch exposes its existing 16-language list. Both LUT targets
restore their internal saved cells at startup without scanning the SD card.
Both LUT updates stop before their saved-bank sectors, preserving imported
cells and opacity. GM1 uses the native pool10 backing and the corrected
dispatcher/producer stack frames. GM5 retains its owner-tested adjacent-manager
build. Neither model changes settings/calibration components or installs an
independent recovery loader. The unfinished 65:24 work is excluded.

These desktop packages are local test candidates, separate from the published
0.1.1 release linked below. The owner reports the latest GM1 LUT firmware
working, with transient colored vertical lines after Import/No LUT remaining
an unresolved limitation. The GM5 LUT target was tested with video recording
and subsequent Library/Playback operation. Long-session and complete recording
format coverage remain incomplete. Use `GM1__V11.bin` for GM1 or `GM5__V11.bin`
for GM5, as selected by the app. Official BIN/ZIP input is model-specific and
hash checked; when download fails, select the matching official local file.

The Mac build runs frozen codec/library/TLS/catalog and GUI checks.
The Windows EXE candidate uses the owner-tested 0.1.1 Windows
bootloader, Python 3.12.3 runtime and native libraries, with matching 3.12.3
application bytecode and the same patch catalogs as Mac. Its independent
archive/PE/source audit is separate from Windows runtime testing; these new
Windows packages have not yet been launched on Windows. The original 0.1.1 owner
test does not validate new code. Nothing in this development section is a new
public GitHub release.

## Download version 0.1.1

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
