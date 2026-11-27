# Lumix Firmware Research
**Recording-limit removal is withdrawn.** The owner reports corrupt SD video files after recording beyond30 minutes. Rebuild and install firmware with native recording limits to remove an already installed limit patch.

**GM1: use the current desktop release. Earlier LUT builds with Opacity can cause severe UI lag.
The current GM1 patch uses fixed 100% LUT strength; brief colored lines after
Import/No LUT remain unresolved.**
**All original project code was written by a chatbot. Flashing Panasonic
cameras is risky because recovery options are limited. No independent GM1/GM5
processor-ROM recovery procedure is validated here; a bad update can leave a camera unusable.**

An unmaintained reference archive of Panasonic Lumix firmware research, USB
service protocols, update authentication, native-code emulation and a tested
GM5 Japanese-language unlock. **No contributions, pull requests or support
requests are accepted.** Reproduce or extend the work in your own fork; see
[archive policy](CONTRIBUTING.md).

The repository contains source, patch recipes, documentation and summarized
evidence. Obtain firmware and device backups yourself. Firmware binaries,
patched update files, raw USB/memory captures, compiled tools and private
connection files are excluded from Git history.

## GM5 AHX recovery and backups

**Make and verify a complete same-body backup before any firmware modification.**
For GM1/GM5, retain the entire 32 MiB flash image, including identity, settings
and calibration, and keep an untouched copy off the camera's SD card.

On November 26 the owner reported successful recovery of a bricked GM5 using
`GM5.AHX` built from its own full backup, with one policy byte changed. The
stock route selected full-image mode 0, which rewrites the calibration sectors;
application-only mode 1 cannot be selected by editing an AHX file. See
[the recovery case, updater modes and file structure](docs/gm5-ahx-recovery.md).
Recovery is owner-confirmed; post-recovery policy/calibration readback has not
been performed. AHX still requires surviving startup/card/programmer code.

## GM1S AHX installation

The owner successfully activated the GM1S SD AHX updater with **Playback +
Q.Menu/Delete/Return + UP held while switching on**. Read-only inspection after
its automatic restart confirms stored policy `1 → 0` at `0x40692634` and RAM
policy `1 → 0` at `0x70a4ebc4`. The full same-body image changed only one intended
payload byte. See [the procedure, image format and evidence](docs/gm1s-ahx-policy.md).
This route requires working startup firmware; independent ROM recovery and a
complete post-update flash readback have not been demonstrated. GM1S desktop
patch support remains separate from this result.

## GM1/GM5 desktop updater

Version **0.2.12** removes the firmware revision/build override and adds **Data backup / Resume**. Patching requires an exact reviewed profile: GM1 internal0110, or GM5 internal0110/0111. The displayed1.1 version is not a unique build identity.

Data backup saves a complete camera backup for later recovery if something goes wrong. It reads the full32MiB mapped flash window even when patch inspection refuses a build. It saves verified checkpoints, supports pause/disconnect/resume, checks camera identity and source anchors, and verifies the final saved image. The app displays instructions to turn Sleep Mode OFF before reconnecting in service mode. Select the same backup folder to resume. Full-backup AHX restoration is now owner-confirmed for one GM5 case; see the recovery guide above for its mode selection and limits.

Both apps include all26 native firmware languages on GM1 and GM5, including
Korean and Middle East languages in the same catalog. The language-only and
LUT options use this catalog. See
[complete-language findings](docs/lumix-all-languages.md).

Both apps are compiled from source on their target systems. The Windows build uses the previously tested USB library. The read-only backup workflow has full-window and interruption/integrity controls; these offline checks do not replace testing the new workflow on the camera.

- [Mac and Windows apps, checksums and release notes](https://github.com/flickering-star/lumix-firmware-research/releases/tag/updater-v0.2.12)
- [Instructions, build source and limitations](apps/README.md)
- [Recording-limit withdrawal](evidence/lumix-recording-limit-withdrawal.json)

Supported profiles are GM1 firmware1.1/internal0110 and GM5 internal0110/0111.
**GM1S is unsupported** and is rejected. GM1 uses fixed100% LUT strength and
blocks invisible adjustment rows. GM5 retains Opacity. GM1 can remain slightly
slower than native styles and may show brief colored lines after Import/No LUT.
The [previous v0.2.4 release](https://github.com/flickering-star/lumix-firmware-research/releases/tag/updater-v0.2.4)
includes GM1 Opacity and its severe-delay warning. See
[GM1 LUT instructions and limitations](docs/gm1-luts.md).

**Disconnect USB before pressing Playback** to obtain the camera's update
prompt. Insert the prepared card with the camera switched off.

The apps contain patch deltas and recover the required key from the connected
service camera. They download or accept only the hash-checked official input.
The camera installs from SD after manual confirmation. Windows requires WinUSB
on the exact model's service interface; the app does not install a driver.
Before returning to stock firmware, reset settings while the patch is running.
A working ordinary updater is required; stock restore is not independent recovery.
Compiled apps are release assets; full firmware, captures and keys stay outside Git.

The original [v0.1.1 GM5-only release](https://github.com/flickering-star/lumix-firmware-research/releases/tag/updater-v0.1.1)
was owner-tested on Japanese and global GM5 bodies with both desktop versions.

| Model / area | Demonstrated result | Boundary |
| --- | --- | --- |
| **GM1 Japanese-market 1.1** | Service USB word/block reads; complete 9 MiB main and 3.375 MiB secondary match official plaintext. All six update components decoded, ECDSA independently verified. The owner reports the language/LUT patch installed and working. | Transient colored lines remain after Import/No LUT. Full recording-format coverage and independent recovery are unproven. |
| **GM5 Japanese 1.1** | 32 MiB NOR mapping backed up; modified unsigned installation proven; persistent policy zero; three-byte language unlock installed in normal mode. English survives manual off/on. | Language installation checked with three exact ROM windows, settings/UI and policy reads. Its full main readback was stopped at the owner's request. |
| **GX9 / Japanese DC-GX7MK3, reported 1.4** | All 35 components of 1.4/1.5 decode. The owner reports successfully installing the policy-one candidate and a working camera. Subsequent physical USB inspection verifies policy `1` at the unchanged address through both access paths, with matching code and normalized metadata guards. | Installation/boot is owner-reported; policy readback is independently verified. Full installed-image readback and an additional controlled power-cycle test have not been performed. SD autorun, external shell delivery and other protocol routes remain under investigation. |
| **GH2** | Static service-dispatch, startup, update, signature and factory-input analysis provided controls for the later USB work. | GH2 addresses and algorithms must not be assumed for GM1/GM5 or newer models. |
| **Emulator** | Native MN103 updater/decode/NOR tests, bounded RTOS/task execution and ARM/Thumb startup/queue transport. | No complete camera boot, display/sensor model or integrated worker/reply path. |
| **GM5 experimental LUTs** | Ten-cell SD import, native Photo Style/Quick Menu selection, opacity and internal storage. The owner confirms LUT video and Library/Playback afterward on `fa17315e…`. | Exact reviewed GM5 build only; recording-format and long-session coverage is incomplete. No independent recovery. |

The public snapshot covers reproduced firmware-access, update-authentication,
flashing, language-patch and the tested experimental GM5 LUT results. Ongoing
feature research and unvalidated model ports are kept outside this archive.
The tested GM1 LUT port is now included, with its remaining limitation stated.

Start with the guide for your model:

- [GM1: USB acquisition, complete decoding and signature verification](docs/gm1-reproduction.md)
- [GM1: experimental LUT port, reproducible components and limitations](docs/gm1-luts.md)
- [GM5: reproduce the exact tested policy/language patch and package](docs/gm5-reproduction.md)
- [GM5: experimental real-time LUT patch, reproducible package and limitations](docs/gm5-luts.md)
- [GX9: full firmware decryption, key recovery and 1.4/1.5 comparison](docs/gx9-firmware-decryption.md)
- [GX9: update signatures, emulated policy control and Windows-local USB test](docs/gx9-update-authentication.md)
- [GX9: fixed-bank policy persistence, prepared candidate and SD/protocol research](docs/gx9-flashing-research.md)
- [GX9: Windows helper to enable and restore the live updater policy](docs/gx9-policy-helper.md)
- [GX9: successful installation report, verified post-flash policy and CHECK fix](docs/gx9-postflash-policy.md)
- [GX9: alternate update filenames and native entry predicate](docs/gx9-sd-update-route.md)
- [GX9: Bluetooth GATT definitions and factory counter callbacks](docs/gx9-bluetooth-protocol.md)
- [GX9: native Wi-Fi HTTP mode decoder](docs/gx9-wifi-mode-decoder.md)
- [GX9: native USB dispatcher, saved-wire replay and settings-bank selectors](docs/gx9-usb-native-protocol.md)
- [GX9: measured RAM write and exact restoration](docs/gx9-ram-write.md)
- [GX9: recovered components and complete filesystem contents](docs/gx9-recovered-components.md)
- [GX9: measured USB memory reads](docs/gx9-memory-reads.md), [Linux runtime](docs/gx9-linux-runtime.md), [internal command-handler analysis](docs/gx9-linux-command.md)
- [Other models: protocol and updater investigation method](docs/porting-to-other-models.md)
- [Public inputs, evidence and reproducibility](docs/reproducibility.md)
- [Native emulator](docs/gm5-emulator.md), [RTOS](docs/gm5-native-rtos.md), [ARM backend](docs/gm5-arm-emulator.md)

## Offline setup

Run from the checkout root, using Python 3.10+ and a C compiler for the native
controls. Physical USB tools include macOS IOKit readers and the
[Windows GX9 WinUSB/libusb capture workflow](docs/gx9-windows-local-capture.md).
Decoding and ordinary Python analysis do not require a connected camera. The
optional GX9 native command-handler verifier uses Unicorn 2.1.4 and mocks all
process, file and IPC operations.

```sh
git clone https://github.com/flickering-star/lumix-firmware-research.git
cd lumix-firmware-research
python3 -m unittest discover -s tests -v
```

Tests requiring privately acquired images or locally built emulator backends
skip when those inputs are absent. A clean checkout therefore has a different
coverage count from the original research environment. Historical full-suite
counts and native execution receipts are labeled by milestone in the evidence.
Build instructions retain pinned source hashes and the GNU simulator license;
see [simulator build](tools/mn103_simulator/README.md).

The supplied GM5 recipes accept only two exact installed-main hashes and require
an exact output hash. They are not generic patch offsets for every GM5 build or
another model. The package reproducer refuses anything except the exact tested
main and official template. It performs no camera or SD-card operation.
