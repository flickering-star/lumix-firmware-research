# Lumix Firmware Research

An unmaintained reference archive of Panasonic Lumix firmware research, USB
service protocols, update authentication, native-code emulation and a tested
GM5 Japanese-language unlock. **No contributions, pull requests or support
requests are accepted.** Reproduce or extend the work in your own fork; see
[archive policy](CONTRIBUTING.md).

The repository contains source, patch recipes, documentation and summarized
evidence. Obtain firmware and device backups yourself. Firmware binaries,
patched update files, raw USB/memory captures, compiled tools and private
connection files are excluded.

| Model / area | Demonstrated result | Boundary |
| --- | --- | --- |
| **GM1 Japanese-market 1.1** | Service USB word/block reads; complete 9 MiB main and 3.375 MiB secondary acquired; both match official plaintext. All six update components decoded, ECDSA independently verified. | No complete physical NOR backup or modified-firmware installation demonstrated. Factory-loader analysis is static. |
| **GM5 Japanese 1.1** | 32 MiB NOR mapping backed up; modified unsigned installation proven; persistent policy zero; three-byte language unlock installed in normal mode. English survives manual off/on. | Language installation checked with three exact ROM windows, settings/UI and policy reads. Its full main readback was stopped at the owner's request. |
| **GX9 / Japanese DC-GX7MK3, reported 1.4** | All 35 components of 1.4/1.5 decode; ten captured components match 1.4. P-256 signatures verify. USB policy `0 → 1 → 0` and exact restoration are physically proven. Native fixed-bank preparation/transfer/reload tests support a locally rebuilt policy-one candidate. | NAND controller completions are simulated. No physical modified update or candidate boot has been tested. SD autorun, external shell delivery and additional protocol routes remain under investigation. |
| **GH2** | Static service-dispatch, startup, update, signature and factory-input analysis provided controls for the later USB work. | GH2 addresses and algorithms must not be assumed for GM1/GM5 or newer models. |
| **Emulator** | Native MN103 updater/decode/NOR tests, bounded RTOS/task execution and ARM/Thumb startup/queue transport. | No complete camera boot, display/sensor model or integrated worker/reply path. |

The public snapshot covers reproduced firmware-access, update-authentication,
flashing and language-patch results. Ongoing feature research and unvalidated
model ports are kept outside this archive.

Start with the guide for your model:

- [GM1: USB acquisition, complete decoding and signature verification](docs/gm1-reproduction.md)
- [GM5: reproduce the exact tested policy/language patch and package](docs/gm5-reproduction.md)
- [GX9: full firmware decryption, key recovery and 1.4/1.5 comparison](docs/gx9-firmware-decryption.md)
- [GX9: update signatures, emulated policy control and Windows-local USB test](docs/gx9-update-authentication.md)
- [GX9: fixed-bank policy persistence, prepared candidate and SD/protocol research](docs/gx9-flashing-research.md)
- [GX9: Windows helper to enable and restore the live updater policy](docs/gx9-policy-helper.md)
- [GX9: alternate update filenames and native entry predicate](docs/gx9-sd-update-route.md)
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
