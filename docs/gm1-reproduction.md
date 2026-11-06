# GM1: findings and reproduction

The owner identifies the tested DMC-GM1 as a Japanese-market body running
firmware 1.1. The owner had already used a service-based
English-language change and reported a persistent service indication. Its
startup transition was not reproduced. Record your own camera's state rather
than treating that indication as a universal service-entry procedure.

## Established results

The live service interface is `04da:2370`, configuration one, interface zero,
alternate zero, class/subclass/protocol `ff/a0/b0`. It has bulk OUT `01`, bulk IN
`82` and interrupt IN `83`. Settings word reads, program-relative word reads
and aligned 1 KiB absolute block reads were demonstrated. Both forward/reverse
controls and packet-verified acquisition/resume are recorded in
[USB findings](gm1-usb-service.md).

| Component | Mapped interval | Exact plaintext SHA-256 |
| --- | --- | --- |
| Main, 9 MiB | `40000000..40900000` | `a96fb6da618b33207db0d357ac5e2513583aaa71dd01df44bed498e63992fabe` |
| Secondary, 3.375 MiB | `41400000..41760000` | `7e8c7d96a95a505d5500fafbd076a56e95f27267708c1f02deb2606fcd304968` |

These complete physical reads equal the independently decoded official
components. They are not a complete physical flash backup. All six official
components decode correctly; their individual hashes, key derivation and native
consumers are documented in [program analysis](gm1-program-analysis.md).

GM1 selector three uses five-round AES-128-CBC with per-entry IVs. It has outer
CRC32, per-plaintext-component SHA-256 and a separate directory ECDSA P-256
signature. The native verifier's public-key/signature fields **and hash integer**
use little-endian conventions; ordinary big-endian ECDSA API assumptions give
the wrong verification result. Independent Python arithmetic and OpenSSL/LibreSSL
checks verify the official signature and reject altered controls.

The static consumer has an unsigned-marker allowance associated with runtime
byte `0x70903814`. Its complete lifetime and a physical GM1 bypass/install were
not demonstrated. The GM1 factory `GM1.AHX` / `GM1E.AHX` S3 parser reaches NOR
writer code, but entry, full acceptance and physical programming remain untested.
See [factory-programming findings](factory-programming.md). GM5 flashing success
must not be reported as a GM1 flashing result.

## Acquire your own controls

The following commands access a connected GM1 on macOS. Start with registry
inspection and the short control before a long acquisition. The wrappers compile
locally and retain source, binary hashes and transfer transcripts in ignored
`captures/`. Their `flash` mode is a read operation, not a flash writer.

```sh
sh tools/run_gm1_usb_probe.sh inspect
sh tools/run_gm1_usb_probe.sh settings
sh tools/run_gm1_usb_probe.sh window
```

Only after those controls identify the expected model and stable reads:

```sh
sh tools/run_gm1_usb_probe.sh program
sh tools/run_gm1_usb_probe.sh secondary
python3 tools/gm1_capture_verify.py captures/YOUR-MAIN-CAPTURE
python3 tools/gm1_capture_verify.py captures/YOUR-SECONDARY-CAPTURE
```

Keep the camera awake. An early fast acquisition froze the research GM1; the
established reader uses 100 ms pacing and stops at the first unexpected response.
After a sleep/disconnection, use the verified-prefix resume tool; it checks
retained packets and three live anchors before appending. Resume only within the
same installed-firmware epoch, never across an update.

```sh
python3 tools/gm1_program_resume.py captures/YOUR-INCOMPLETE-CAPTURE
```

## Decode and independently authenticate

Obtain the official `GM1__V11.bin` locally. Its expected whole-file SHA-256 is
`3e8b4aab23f79db160cd016af0e466011f047add07bb7441c642f6b70df30d90`.
Put it under ignored `firmware/official-gm1-v11/`. Substitute your own verified
capture paths below; no researcher's raw dump is included in this repository.

```sh
mkdir -p work
cc -O2 -std=c11 -Wall -Wextra -Werror tools/panasonic_aes5.c -o work/panasonic-aes5
work/panasonic-aes5 --selftest
python3 tools/panasonic_v2_decode.py firmware/official-gm1-v11/GM1__V11.bin --key-source captures/YOUR-MAIN-CAPTURE/result/program-main.bin --physical-secondary captures/YOUR-SECONDARY-CAPTURE/result/program2.bin --out work/gm1-decoded
python3 tools/panasonic_signature_verify.py firmware/official-gm1-v11/GM1__V11.bin --secondary captures/YOUR-SECONDARY-CAPTURE/result/program2.bin --key-model GM1 --out work/gm1-signature.json
```

Every decoded component must match its directory digest; both acquired programs
must match byte-for-byte. A wrong key, incomplete input or unsupported build is
a failed control, not a reason to remove the digest guard.

For native traces, build the [MN103 disassembler](../tools/mn103_adapter/README.md),
then run `gm1_update_verify.py`, `gm1_startup_verify.py` and
`gm1_factory_verify.py` against your verified programs. These are static/offline
verifiers, not a physical factory loader or interactive debugger.

The [other-model guide](porting-to-other-models.md) explains which protocol
observations transfer and which addresses, key material and policies must be
rediscovered.
