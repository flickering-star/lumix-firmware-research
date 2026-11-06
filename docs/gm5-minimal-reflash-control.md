# Unchanged installed-program control

The next camera control is prepared and has passed offline validation. It
contains only this GM5's unchanged installed `program2`. It has now been copied
to the identified SD card, verified and safely ejected. **No physical
installation has yet been verified.** This is a preservation control before introducing a
persistent policy/language change.

The [verified evidence](../evidence/gm5-minimal-reflash-control.json) records
the exact file, source snapshots, cipher oracles, native runs and test log.

| Property | Prepared value |
| --- | --- |
| Local package | `work/gm5-reflash-control-2/GM5__V11.bin` |
| File length | 3,540,480 bytes |
| File SHA-256 | `f978123c4eafb4a8bd0961c46ee013eb161babda6020eb1e3cbd0c68833dc4c8` |
| Only component | `program2`, 3,538,944 bytes |
| Component SHA-256 | `d3953f29553723e7375c537f2cf8e673ade4924e6c0de161243cf106575a74e7` |
| NOR interval | Offset `0x1400000..0x1760000`, end exclusive |
| Native write plan | 27 complete 128 KiB sectors; 3,456 buffers of 1 KiB |
| Advertised header halfwords | Both `0x0112`; installed executable/version bytes unchanged |
| Authentication | Zero unsigned marker; signature field explicitly zeroed |
| Required temporary state | RAM `0x70a68490 = 0`, which creates decoder allowance 1 |

Main/boot code, GUI resources, ARM code, `other`, both settings banks and the
fixed adjustment payload are absent. No permanent patch is included. Reusing
the installed Japanese bytes avoids replacing them with the different official
download. The advertising fields are container metadata; this package has no
payload that changes the installed version words in main flash.

## What passed

The host codec now supports encryption as well as the existing decoding CLI.
Its forward and inverse routines pass the standard AES-128 vector and an
independent physical GM1 five-round block. More decisively, re-encrypting all
eight previously verified official GM5 plaintext components reproduces every
original ciphertext byte. The new package then decodes to the exact installed
secondary program using the retained original decoder, predating the encoder.

Seven controls execute this camera's installed native instructions:

| Control | Result |
| --- | --- |
| Startup copy snippet | Copies all of installed `program2` from `0x41400000` to `0xbbc00000` |
| Exact package, allowance 1 | Decoder returns zero; host compares every decoded payload byte with the backup |
| Exact package, default allowance 0 | Rejected with `0x80000065` |
| Damaged CRC, allowance 1 | Rejected with `0x80000064` |
| Native post-decode installation | 27 erases and 3,456 programs; complete 32 MiB result equals the original backup |
| First program operation fails | Native writer returns `0x8000000c`; full readback detects the erased, incomplete sector |
| Power cut after first erase and buffer | Stops at that operation boundary; full readback matches the independently predicted partial image |

Every modeled mutation remains inside `program2`, including both failure
controls. The native job leaves the decoded package unchanged. All bytes
outside that component, including settings/calibration, match the original in
all three virtual programming outputs. The original protected backup remains
unchanged. **All 68 repository tests pass**, including exclusive-output/range
guards and rejection of altered destinations, flags, hashes and hidden entries.

The unsigned native decoder skips component SHA verification. The host's exact
comparison supplies that check; native return zero alone does not establish it.

## What this control can establish

An unchanged physical readback is necessary for this control, but cannot
distinguish successful identical programming from rejection or no write. A
progress bar and ordinary restart cannot resolve that ambiguity either. This
test can check behavior and preservation while exercising the proposed entry
state, but **cannot alone prove an accepted flashing route**. Final proof will
need a separately reviewed distinguishable modification or direct programming
evidence. That follow-up is not included in this file.

The startup copy uses `0xbbc00000`, while the linked entry and updater execute
at `0x7bc00000`. Native arithmetic supports a runtime alias, but that hardware
alias has not been independently measured. The copy test begins after board
setup; it is not a complete boot. Virtual installation still explicitly bypasses
two board/handshake call regions, models RTOS locking with checked stubs and
uses simplified cache behavior. Final cleanup, restart and any additional
boot-time authentication are not modeled. A backup is not a tested recovery
writer.

## Live preparation

After the owner replied “Connected” to the control-readiness request, both the
GM5 and the original LUMIX card were visible. A fresh read-only USB capture
verified the policy halfword is still **one**; its packet replay is complete
without errors. The [preparation flag record](../evidence/gm5-minimal-reflash-before-flag.json)
identifies that capture. No camera RAM writes were made during that initial check.

The card was identified afresh as removable external FAT32, UUID
`PRIVATE_CARD_UUID`. Its earlier 31,901,184-byte candidate
matched the known `45a7da84…` hash and was preserved privately before replacement.
The fixed-scope [copy tool](../tools/gm5_reflash_sd.py) staged the exact new
3,540,480-byte control, flushed it, compared both staging and final readbacks
byte for byte, then safely ejected the card. Other files were left in place;
the card was not formatted. The [SD preparation record](../evidence/gm5-minimal-reflash-sd.json)
contains the complete package hash and previous-file provenance.

The owner then confirmed the card was inserted and the GM5 awake and connected.
A fresh 16 KiB updater-window acquisition matched the protected backup exactly,
with complete packet replay; see the [installed-build guard](../evidence/gm5-minimal-reflash-installed-guard.json).
The guarded language tool wrote the English settings shadow and active UI cache,
both verified as bytes `00 01`. The guarded RAM tool then made one fixed-address
policy write and verified the halfword at `0x70a68490` is **zero**.

The [arm record](../evidence/gm5-minimal-reflash-arm.json) preserves both captures,
their transcript hashes and the exact package hash. No EEPROM commit or host
NOR-writing command was sent. The owner has been instructed to unplug without
powering off, enter Playback and confirm the agreed unchanged-program control,
keeping power stable through completion. The physical result was pending at
that stage; no accepted installation was claimed.

On the first attempt the owner saw ordinary playback. A read after reconnecting
verified the policy was still zero, with the owner reporting that the camera
had stayed awake; see the [no-prompt flag record](../evidence/gm5-minimal-reflash-no-prompt-flag.json).
The owner subsequently reported the update prompt in both service and standard
mode, suggesting the card/power transition affected discovery. The owner proposed
inserting the card while the camera is off. This is a repeatability measure,
not an established firmware requirement. The [prompt observation](../evidence/gm5-minimal-reflash-prompt-observation.json)
keeps those reports distinct from a verified installation.

After that transition the fresh policy read was one and the active UI was
Japanese. English was written and verified again, followed by a guarded
**one → zero** policy write/readback. The [latest arm record](../evidence/gm5-minimal-reflash-rearm.json)
supersedes the earlier arm for proceeding. The owner asked how an unchanged
package could prove programming; the preservation-only limitation above was
explained. The owner then explicitly asked to proceed and was instructed to run
this same control, leaving the camera powered through completion. Its physical
result was pending at that point.

The owner then reported full progress, an automatic restart and no message.
The [post-restart service check](../evidence/gm5-minimal-reflash-postrestart-version.json)
verified policy **one** and unchanged version fields `0x0111 / 0x0111`; the
8 KiB main prefix matched the backup in forward and reverse reads. This reads
the fields consumed by the native identity getter; no dedicated version-query
opcode was sent.

A fresh, packet-verified acquisition of the entire targeted `program2`
(`0x41400000..0x41760000`, 3,538,944 bytes) matches the retained installed backup
exactly, SHA-256
`d3953f29553723e7375c537f2cf8e673ade4924e6c0de161243cf106575a74e7`.
The [post-test record](../evidence/gm5-minimal-reflash-posttest.json) distinguishes
that measured preservation from the owner's screen observations. The initial
readback attempt found no service interface and sent no transfer; after the
owner woke/reconnected the GM5, a fresh acquisition completed without resume.
No host RAM or NOR write was sent after restart. The complete 32 MiB NOR was
not reread, so physical calibration preservation is not independently claimed.

The fixed secondary interval can now be acquired or resumed without reading the
preceding 20 MiB:

```sh
python3 tools/gm5_flash_backup.py --component program2
python3 tools/gm5_flash_backup.py --component program2 --resume captures/INCOMPLETE_SAME_FIRMWARE_CAPTURE
```

Resume replays the saved packets, checks the model/component and compares three
live anchors. Never reuse a prefix across an installation; unchanged anchors
can miss a difference elsewhere in an old image.

The owner requested a distinguishable next package with the policy already set
in firmware. That [one-byte main-program candidate](gm5-policy-zero-package.md)
passed eight native controls and was subsequently installed. Its complete
8 MiB main readback matches the one-byte-patched candidate, and ROM/RAM policy
zero persisted after the owner's normal off/on cycle. The
[physical proof](../evidence/gm5-policy-zero-physical-proof.json) establishes
modified unsigned programming. This earlier unchanged control's matching bytes
alone still do not prove that its identical programming occurred.

## Prepared camera procedure

The owner has now performed this agreed control and reported completion; the
steps below are retained for reproducibility. Physical programming remains
unproven by an unchanged readback, and recovery remains unverified.

1. Verify the camera is operating normally and has a fully charged battery.
   Check that the protected backup and exact package above remain available.
   Panasonic requires a full battery and USB/HDMI disconnected for the update
   prompt in its [official update procedure](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/step2.html).
2. With the camera's SD card in its reader, identify that card afresh. Copy only
   this `GM5__V11.bin` to its root, remove any older firmware candidate from the
   card after preserving it locally, verify the copied hash, and safely eject.
   No formatting is needed or authorized by this procedure.
3. Start with the camera off and the prepared card inserted, then turn it on
   and connect service USB. Keep the card inserted thereafter. This avoids the
   earlier hot-insertion discovery ambiguity before setting the RAM flag.
   Check the exact GM5
   identity and current policy. Apply the already requested temporary English
   setting, then use the fixed-address guarded RAM control to set the policy to
   zero and verify it. Keep the camera awake. A power cycle requires repeating
   this preparation; sleep continuity has not been established.
4. Unplug USB without switching off and enter Playback. Stop at the update
   confirmation and record its wording. The higher advertised words previously
   displayed as version 1.1; this is not a promise of a new installed version.
   Confirm Yes only as part of the agreed physical control.
5. Leave the camera powered and undisturbed through its update procedure. Record
   the duration and any message. Follow the camera's completed-update restart
   instruction; do not infer completion from a short progress bar.
6. Reconnect after normal operation resumes. Verify the policy has returned to
   one, and acquire a new read-only NOR capture with the resumable backup tool.
   Compare `program2` byte for byte with the retained installed payload and
   compare the other executable areas as well. Review settings-bank differences
   separately: ordinary use/restart can persist state, so physical settings
   changes must not automatically be attributed to this package.

There is no unattended retry or direct host NOR-write command. If canceled
before updating while still powered, restore and verify the original RAM
policy. A new physical attempt must not reuse an uncertain partial state.

## Reproduce the offline preparation

Run from the repository root with the private verified inputs and built
simulator present. Choose fresh output directories; existing outputs are
preserved.

```sh
clang -O3 -std=c11 -Wall -Wextra -Werror tools/panasonic_aes5.c -o work/panasonic-aes5-codec
python3 tools/gm5_reflash_control.py build --out work/gm5-reflash-control-new
python3 tools/gm5_reflash_control.py test --package work/gm5-reflash-control-new/GM5__V11.bin --out work/gm5-reflash-control-native-new
python3 -m unittest discover -s tests -v
```

The original decoder binary is checked against the prior official-decoding
receipt. Build/test runs retain their exact controller and helper sources.
The evidence collector checks those snapshots, traces, backend, protected input
and complete virtual images before publishing hashes and results.
