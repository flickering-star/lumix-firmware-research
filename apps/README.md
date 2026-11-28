# Lumix Firmware Updater

Version **0.2.14** restores GM1 LUT Opacity control with the blend cache by
[ShawnMayer](https://github.com/ShawnMayer/gm1-lut-opacity-cache).
The owner reports responsive controls with slight overhead compared with the
fixed-strength patch. Brief colored lines after Import/No LUT remain unresolved;
complete recording-format and long-session coverage is not established.
GM5 keeps its previous released LUT implementation. Its separate cache
experiment is excluded after a recording/menu regression.

- [macOS Apple Silicon and Windows x64 downloads, checksums and release notes](https://github.com/flickering-star/lumix-firmware-research/releases/tag/updater-v0.2.14)
- [Credits and the upstream add-on usage notice](../CREDITS.md)
- [GM1 LUT details and component reproduction](../docs/gm1-luts.md)

The application prepares SD updates from the exact official GM1/GM5 1.1 input.
It includes all26 native firmware languages, persistent custom-update access,
ten saved LUT cells, FAT32 VLT/CUBE import, Opacity control and stock program
restore. Native recording limits are retained. Existing LUT banks survive a
LUT update; no cell-format migration or clearing is needed for the GM1 cache.
The withdrawn recording-limit removal, exFAT,23-cell and65:24 experiments are
excluded. Stock restore and the language-only option clear experimental LUTs.

Original project code was written by a chatbot; the GM1 cache add-on is credited
separately. Make and verify a full same-body backup before any firmware
modification. A bad update can leave a camera unusable. The owner has recovered
one GM5 through AHX from its full same-body backup, but that route depends on
surviving startup/card/programmer code. It is not independent processor-ROM
recovery. See [the recovery case and updater modes](../docs/gm5-ahx-recovery.md).

## Supported firmware

Patching requires an exact reviewed GM1 internal0110/0111 or GM5 internal0110/0111
profile. Displayed firmware1.1 is not a unique internal build identifier.
Revision/build skips are removed; unknown or mixed layouts are refused. GM1S is
unsupported. A shared USB product ID does not establish camera compatibility.

The GM1 factory0111 profile uses its own complete-page fingerprints, relocated
key and service offsets. The app still constructs reviewed0110-based GM1 patch
components from the same official1.1 BIN and installs those through SD; it does
not apply0110 patch addresses to the relocated installed0111 image. This changes
the internal revision to0110 while displayed firmware remains1.1. GM1 factory0111
installation was subsequently owner-tested. A separately prepared Stock Program
Restore reproduces the detected starting profile. Keep that restore file.
Settings/body calibration are excluded from ordinary patch and program-restore
updates. See [the GM1 profile review](../docs/gm1-0111-updater-profile.md).

## Data backup / Resume

**Data backup / Resume** on the Camera tab saves the complete32MiB mapped flash
window (`40000000–41ffffff`) for later recovery, even if patch inspection refuses
the installed build. It reads fixed1KiB blocks without changing the camera or
enabling updates. Choose an empty folder for a new copy or the same folder to
resume. Completed blocks are flushed before durable checkpoints; resume verifies
local hashes, camera identity and source anchors. Disconnect, Pause and window
close preserve completed work. Corrupt data or changed anchors are refused.

Before reconnecting in service mode, set **MENU/SET → Setup (wrench) → Economy →
Sleep Mode → OFF** in normal camera mode. The app shows these instructions and
does not change the setting. Keep the computer awake and camera power stable.
See the [GM1 advanced manual, page49](https://help.na.panasonic.com/wp-content/uploads/2023/02/DMCGM1_VQT5D68_ENG.pdf)
and [GM5 advanced manual, page69](https://www.panasonic.com/content/dam/Panasonic/support_manual/Digital_Still_Camera/English/DMC-GM5_Operating_Instructions_for_advanced_features.pdf).

The completed file is `flash32m.bin`, exactly33,554,432 bytes, with a final disk
read verification, SHA256 and report. Keep the entire folder while copying;
partial data uses `flash32m.bin.part`. A raw backup needs a model-appropriate AHX
conversion before recovery; it is not directly installable as BIN/AHX. It may
include camera identity, settings and calibration, so keep it private.

## Using the app

1. Extract the Mac app or the entire Windows folder. Keep Windows `_internal`
   beside its EXE. End users need neither Python nor a compiler.
2. Connect an awake supported camera in service mode and choose **Read camera**.
   Select the language/update-access patch, Experimental LUTs or stock restore.
3. Prepare the update in a new folder. The app downloads the hash-pinned official
   input or accepts the matching official local BIN/ZIP. Other hashes are refused.
   Keep the prepared folder and its separate `stock-restore` file.
4. Copy `GM1__V11.bin` for GM1 or `GM5__V11.bin` for GM5 to the root of a
   camera-formatted FAT32 card. Select Standard, switch the camera off, then
   insert the card. Use a fully charged battery.
5. Follow the app's instructions. A stock update policy needs the app's checked
   temporary service-USB change through **Enable this update**. If the camera
   sleeps/restarts/disconnects, reconnect and use the button again; each attempt
   repeats the compatibility and file checks. Compatible patched firmware needs
   no temporary change.
6. **Disconnect USB before pressing Playback**, keeping the awake camera powered
   on. Confirm the update on the camera and keep power stable until completion.

Windows needs WinUSB on the exact service interface (`04DA:2370`); the app does
not install a driver. The app does not select Yes or flash firmware over USB.
Before Stock Program Restore, reset camera settings while patched firmware is
still running. Ordinary stock restore requires the working camera updater.

## Desktop builds

The Mac ZIP contains a standalone Apple Silicon `.app`; Windows x64 contains a
standalone folder and EXE. Neither is notarized/code-signed for public distribution;
the Mac application has an ad-hoc signature. No Intel Mac build is provided.
Packages contain application/native libraries and bounded patch deltas, with no
full Panasonic firmware, raw backup or camera encryption key.

Build on each target OS using64-bit Python3.11+, Tk, a C compiler and
`requirements-updater.txt`. macOS uses clang; Windows uses the Visual Studio x64
Native Tools environment or64-bit MinGW. The Windows release is built from
source by the pinned GitHub workflow with the previously tested USB library.

```sh
python -m pip install -r apps/requirements-updater.txt
python -m unittest tests.test_lumix_backup tests.test_lumix_updater tests.test_lumix_updater_release
python tools/lumix_updater_bundle.py --assets apps/lumix_updater/patches --out /private/new-updater-build
```

The bundler verifies frozen codec, patch hashes, native USB-library loading and
TLS roots, then opens the actual GUI for a layout check. These checks do not open
a camera or validate its complete USB workflow. Windows headless source builds
package with `--skip-checks`; their executable/catalog/source audit is separate
from Windows runtime testing. The GM1 firmware output is the same cache target
supplied for the owner's responsive-controls test, with current language/bank/
recording-limit preservation. Full camera-mode coverage is not implied.

This is an unmaintained reference archive. Contributions and support requests
are not accepted; see the [archive policy](../CONTRIBUTING.md).
