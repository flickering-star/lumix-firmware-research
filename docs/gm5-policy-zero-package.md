# Persistent policy-zero test package

The next package requested by the owner is prepared and validated offline. It
changes exactly **one byte** in this camera's installed main program: the ROM
initializer for the unsigned-update policy becomes zero. No language, region,
aspect-ratio or other code patch is included. **Physical installation and normal
power-cycle persistence are now verified**, with a complete 8 MiB readback
matching the exact candidate. See the [physical proof](../evidence/gm5-policy-zero-physical-proof.json).

The [readiness record](../evidence/gm5-policy-zero-readiness.json) links the
[complete package/native evidence](../evidence/gm5-policy-zero-package.json)
and 71 passing repository tests.
The later main-reader boundary/resume extension brings the passing repository
suite to 73 tests; its [reader record](../evidence/gm5-main-readback-reader.json)
retains the build target, sanitizer checks and test-log hash.

| Property | Prepared value |
| --- | --- |
| Local file | `work/gm5-policy-zero-1/GM5__V11.bin` |
| Encoded file size | 8,390,144 bytes |
| File SHA-256 | `86832e6eafa90b453894237805dafe128f61d346066f73a3752a8071d8286f16` |
| Only component | Installed `program`, 8,388,608 bytes, NOR offset zero |
| Plaintext change | Offset `0x6b1bdc`, flash address `0x406b1bdc`, byte `01` → `00` |
| Resulting main SHA-256 | `c918553771018e171605ecb1f177a4d64bc94b221fe5304b8ff419f4509d208d` |
| Expected RAM policy after fresh initialization | Halfword zero at `0x70a68490` |
| Container advertising halfwords | Both `0x0113` |
| Installed version/build bytes | Preserved from this camera's backup |
| Native programming scope | 64 complete 128 KiB sector erases; 8,192 buffers of 1 KiB |
| Excluded components | `guires`, `program2`, `armcode`, `other`, both settings banks, fixed adjustment |

The new container version keeps the test distinct from the prior `0x0112`
control. It does not claim that the camera's displayed firmware version becomes
1.3: the actual installed version fields are unchanged. The plaintext is the
Japanese camera's retained installed main, rather than the different official
download.

## What this changes

The native startup initializer copies ROM `0x406b1bdc` to RAM `0x70a68490`.
The updater samples that RAM flag; zero enables the zero-marker unsigned-input
path. This package uses that path and has no valid directory signature. The
existing camera therefore still needs the temporary RAM flag set to zero for
this first installation. If the patch installs and survives a fresh start,
future uses of this unsigned path should not need that USB policy write.

The package does not modify the verification key or the ECDSA routine. It sets
the existing unsigned-policy initializer. Normal signed-input handling is a
separate branch.

## Completed validation

The recovered five-round AES encoder, already checked against every official
GM5 ciphertext, encodes the patched main. The retained original decoder
recovers the exact expected main byte for byte. The complete plaintext diff
against the protected backup contains only `0x6b1bdc: 1 → 0`.

Eight controls execute installed native instructions:

| Control | Result |
| --- | --- |
| Exact package, allowance 1 | Decodes successfully; host verifies every plaintext byte against the exact patch |
| Exact package, default allowance 0 | Rejects with `0x80000065` |
| Corrupted CRC | Rejects with `0x80000064` |
| Exact native installation into virtual NOR | 64 erases/8,192 programs; full 32 MiB differs from the backup by precisely the policy byte |
| First programming operation fails | Incomplete first sector detected by full readback |
| Power cut after first erase and buffer | Exact predicted partial image detected by full readback |
| Key initializer reloaded from programmed NOR | Entire copied region matches expected ROM; recovered cipher key is unchanged |
| Policy initializer reloaded from programmed NOR | Entire copied region matches expected ROM; RAM policy is zero and the only changed initializer byte is at `0x70a68490` |

Settings/calibration and every component outside main remain byte-identical in
all virtual programming outputs. All mutation commands stay within main.
**All 71 repository tests pass**, including new guards against a different or
already patched source, redirecting the main payload, and mixing readback
component/resume intervals.

These tests retain the existing explicit board/handshake, RTOS and cache
abstractions. Copy-loop tests establish initialization behavior from the exact
programmed image; they do not execute full hardware boot or exclude another
boot-time authentication check. The main program includes boot code, and the
whole 8 MiB interval is programmed despite the intended one-byte difference.
Physical recovery remains unvalidated.

## Physical proof criteria

A camera attempt is separate from the offline preparation. The owner responded
to the exact main/boot test request by connecting the card, then confirmed it
inserted with the camera awake and connected. Preparation for that agreed
attempt is recorded below.

For an agreed attempt, copy and verify this exact file to the identified card,
then start the camera with the card already inserted before applying English
and the one-time RAM policy change. Keep power stable through the camera's
completed update procedure.

After completion, perform a normal off/on cycle. Before sending **any** USB
policy write, use the read-only service probes to check both locations:

```sh
sh tools/run_gm5_usb_probe.sh security-flag
sh tools/run_gm5_usb_probe.sh runtime-control
```

The ROM halfword at `0x406b1bdc` must now be zero rather than the old one, and
freshly initialized RAM `0x70a68490` must also be zero. That distinguishes an
installed change from the unchanged control. A complete main-program readback
must then match the expected SHA-256 above. The reader now supports the fixed
8 MiB main interval as well as whole NOR and `program2`:

```sh
python3 tools/gm5_flash_backup.py --component program
```

The main-only build records its target and compiler definition, bounds reads to
the known mapping, and supports packet-verified resume within the same
installation. Boundary checks run under address/undefined-behavior sanitizers.
The installed version fields should still be their original values and are not
the success marker.

Start a **fresh** acquisition after the installation. Never resume using a
prefix from a different firmware installation: three matching resume anchors
could miss a one-byte policy change elsewhere in an old prefix.

The [preceding unchanged control](gm5-minimal-reflash-control.md) now has a full
3.375 MiB target readback matching the backup. The owner reported full progress
and automatic restart without a message. The post-restart policy is one and
the version fields remain `0x0111 / 0x0111`. Those observations establish
preservation; they do not independently establish erase/program execution.

## Live preparation

The [SD receipt](../evidence/gm5-policy-zero-sd.json) verifies the exact
8,390,144-byte file and full SHA-256 above on the original LUMIX FAT32 card,
UUID `PRIVATE_CARD_UUID`. The previous unchanged control was
preserved locally. Staging and final copies were flushed and compared byte for
byte, then the card was safely ejected. No formatting was performed.

The owner then confirmed the card inserted with the GM5 awake and connected.
A [fresh read-only ROM baseline](../evidence/gm5-policy-zero-before-rom.json)
verified the halfword at `0x406b1bdc` is still **one**; the whole 1 KiB window
matches the protected backup. English was written and verified in the settings
shadow and active UI cache. The guarded policy tool then performed **one → zero**
in RAM and verified the readback.

The [arm record](../evidence/gm5-policy-zero-arm.json) pins both captures and the
exact package hash. No host NOR command or EEPROM commit was sent. The owner
was instructed to unplug without power-off, confirm the prepared file through
Playback and leave power stable until completion. After normal operation
resumes, one normal off/on cycle is requested before reconnecting service USB.
The first post-update operations must be read-only ROM and RAM checks; no
policy or language write may precede that persistence measurement. The physical
result is recorded next.

## Measured physical result

The owner reported that this attempt took longer and thought the camera
restarted before the progress bar reached its end. The owner subsequently
confirmed a normal off/on cycle before reconnecting. The first post-restart
operations were read-only service captures:

| Measurement | Result |
| --- | --- |
| ROM halfword `0x406b1bdc` | Zero; immediate pre-test value was one |
| Entire surrounding 1 KiB ROM window | Only byte `0x406b1bdc` changed, `01` → `00` |
| RAM halfword `0x70a68490` | Zero, with no post-restart policy write |
| Complete main readback | All 8,388,608 bytes match the candidate plaintext |
| Main SHA-256 | `c918553771018e171605ecb1f177a4d64bc94b221fe5304b8ff419f4509d208d` |
| Diff against original 8 MiB main | Exactly one byte, at offset `0x6b1bdc` |
| Installed version fields | Still `0x0111 / 0x0111` |

The fresh capture is `captures/gm5-program-readback-f61hhqc_`; all 8,192 block
responses are packet-verified, and its completed main file is protected
read-only. The [offline proof collector](../tools/gm5_policy_proof.py) checks the
exact SD/candidate hashes, outgoing pre-installation RAM request, pre/post ROM
and RAM captures, owner power-cycle confirmation and every main byte before
publishing the [result](../evidence/gm5-policy-zero-physical-proof.json).

This establishes a modified unsigned SD installation on this camera/build and
the persistent policy-zero initializer. The complete 32 MiB and other storage
were not reread after the test, so a complete physical calibration comparison
is not claimed. Full hardware boot is not emulated, broader camera-function
tests have not been performed, and no external recovery programmer is validated.
The original protected backup remains unchanged.

Recheck the saved physical evidence without contacting the camera, choosing a
fresh output file:

```sh
python3 tools/gm5_policy_proof.py --main-capture captures/gm5-program-readback-f61hhqc_ --out work/gm5-policy-proof-recheck.json
```

## Reproduce offline

Choose fresh output directories and retain the private verified inputs:

```sh
python3 tools/gm5_policy_package.py build --out work/gm5-policy-zero-new
python3 tools/gm5_policy_package.py test --package work/gm5-policy-zero-new/GM5__V11.bin --out work/gm5-policy-zero-native-new
python3 tools/gm5_policy_package.py publish --build-dir work/gm5-policy-zero-new --native-dir work/gm5-policy-zero-native-new --out work/gm5-policy-zero-evidence-new.json
python3 -m unittest discover -s tests -v
```
