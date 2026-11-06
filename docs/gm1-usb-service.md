# GM1 service USB observation and bounded probe — 2026-11-05

The connected **DMC-GM1 exposes `04da:2370`, `ff/a0/b0`**, and its complete
39-byte service configuration matches the GH2 model exactly. The corrected probe
has read **settings matching the saved export, the complete 9 MiB main program
and complete 3.375 MiB secondary program**. Both program SHA-256 hashes equal
their official GM1 1.1 directory fields. A block reader and resume after sleep
and a battery restart are demonstrated. The recovered code also enabled
[decoding all six official GM1 components](gm1-program-analysis.md).
A complete GM1 physical flash backup and an interactive debugger remain
unverified. Later work independently verified GM5 service reads and modified
installation; see the [GM5 findings](gm5-flashing.md). The GM1
[readback evidence](../evidence/gm1-usb-readback.json)
supersedes the initial access failure below.

The owner identifies this GM1 as a Japanese-market camera and reports an
earlier service-based change to English and a persistent service indication. The camera was already in that state when connected through
a USB hub; the startup transition was not reproduced. The mechanism of the
language change has not been independently established. The device disappeared
from the registry when the owner reported sleep, then returned with the same
service identity.

## What was measured

The [evidence record](../evidence/gm1-usb-service.json) preserves sanitized
properties, source hashes and the access-attempt result. Raw captures are in
ignored `captures/gm1-usb-access-tGyiv56t/`.

| Registry property | Live GM1 observation |
| --- | --- |
| Product name / vendor | `DMC-GM1` / `Panasonic` |
| VID / PID | `04da:2370` |
| USB version / descriptor release | `0x0200` / `0x0100` |
| Configuration / interface / alternate setting | `1` / `0` / `0` |
| Interface class / subclass / protocol | `ff/a0/b0` |
| Endpoint count | Three |
| Serial-string index | Zero |

The descriptor release `0x0100` is not a measurement of the installed firmware
version. The [GH2 service builder](gh2-usb-maintenance-entry.md) sets that value
independently of the normal camera-version helper.

The follow-up obtained these exact configuration bytes:

```text
09022700010100c0010904000003ffa0b000070501020002000705820200020007058303000208
```

The measured endpoints are bulk OUT `0x01`, bulk IN `0x82` and interrupt IN
`0x83`, all with 512-byte maximum packets; the interrupt interval is eight.
These GM1 descriptors were not themselves proof of GM5 service behavior; later
GM5 measurements are recorded separately.

## Initial restricted-session access failure

The existing device-level cached-descriptor tool failed at
`IOCreatePlugInInterfaceForService` with **`0xe00002be`**, defined by the installed
Apple SDK as `kIOReturnNoResources`. A separately compiled interface-level
probe found exactly one matching GM1 interface, but its equivalent user-client
creation failed with the same result. The interface was never opened:

```json
{
  "interface_opened": false,
  "control_requests_attempted": 0,
  "bulk_writes_attempted": 0,
  "validated_word_responses": 0
}
```

This is a host-API failure, not a negative response from the camera. Its exact
cause remains unresolved. Restricted session access is a candidate:
`/usr/bin/log` explicitly reports that it cannot run while sandboxed, and
[Apple's USB interface guide](https://developer.apple.com/library/archive/documentation/DeviceDrivers/Conceptual/USBBook/USBDeviceInterfaces/USBDevInterfaces.html)
documents the USB entitlement requirement for sandboxed applications. That does
not prove that every occurrence of this resource error has the same cause.
The subsequent normal-Terminal runs opened the interface successfully through
the same hub. After this session's restrictions were removed, the same API also
worked directly here. This resolves the original session access blocker.

## Correcting the receive sequence

The owner's original two attempts each completed preparation and sent one
settings read, but the first bulk IN transfer returned just `08`. The probe
incorrectly treated this response-type byte as an incomplete full frame.
The retained FZ30 host routine at `0x40ca2c` instead reads one byte through the
call at `0x40ca41`, selects the frame length, then requests the complete frame
through `0x40caf2`. Its read wrapper prepares each transfer separately.

The corrected probe reads the type byte, issues another index-one preparation,
then reads the whole frame including its type byte. This is a separate protocol
phase, not an error retry. All sixteen settings replies passed sequence,
complement, status and checksum checks. Their 32 decoded bytes exactly match
the saved fixed export at words `0x3f80..0x3f8f`, including `Panasonic` and
`DMC-GM1`.

The next run repeated that settings control and successfully read 32 words
through `0x70`. Its 64 bytes at the assumed base `0x40000000` decode as
MN103-family startup instructions; 54 bytes equal GH2's same-position prefix.
The sequence includes a secondary-code jump to `0x7bc00000`, differing from
GH2's target. This supports program-memory access at that base; it does not
establish the complete GM1 address map. Raw data, packet transcripts and native
disassembly are retained in `captures/gm1-usb-flash-TOsIFxZY/` and summarized in
[the reproducible evidence](../evidence/gm1-usb-readback.json).

## Program block reads and the interrupted acquisition

Further GH2 inspection identified operation **`0x5c`**, whose dispatch table
entry calls the range-copy handler at `0x401f0470`. Its request and response
are both class-one, 1,030-byte frames, with a 1,024-byte payload. Request bytes
4..7 contain the start address and bytes 8..11 the exclusive end address.
The response uses status `0x05`. The [offline verifier](../tools/gh2_block_read_verify.py)
checks the exact input hash, dispatch call, header classification and native
copy/response instructions; [its report](../evidence/gh2-usb-block-reader.json)
preserves those instructions.

The handler itself lacks an explicit 1,024-byte range bound. The host requires
an aligned interval of exactly that size and limits it to the candidate main
program, `0x40000000..0x40900000`. No oversized request was tested. The live
first block matched the independent 64-byte word-read prefix. Forward and
reverse-order 8 KiB captures then matched byte for byte.

A faster, 1 ms post-write acquisition retained **1,198 validated blocks,
1,226,752 bytes**, before `prepare_bulk_in` returned `0xe0004051`. Apple's
installed `USB.h` defines that error as **`kIOUSBTransactionTimeout`**. It is
not `kIOUSBPipeStalled` (`0xe000404f`); an initial conversation description was
corrected after checking the SDK. The owner reported that the camera froze and
required battery removal. The cause is unresolved. The incomplete capture
is `captures/gm1-usb-program-qUdxsgb3/`, with program SHA-256
`ae9ec5587e03aa57e68b61922bd9e516e90eabdf90eb23c29fc71c38db36e0d8`.
No comparison of this partial file to the complete official component hash is
meaningful.

The subsequent acquisition restores the historical host's 100 ms post-write
pause. This is a conservative timing change, not a demonstrated explanation
or cure for the first freeze. It acquired another 1,780 blocks after checking
three anchors, then stopped with `kIOReturnNotResponding` (`0xe00002ed`). The
owner reported sleep, not another freeze, for this second interruption. The
verified main prefix at that interruption was **3,049,472 bytes**, SHA-256
`c0354fe5c4df6a137b366b227d23fa9b682321d892d4e274cb63e91c197fbe08`,
and its next unread address was **`0x402e8800`**. This interrupted result is
preserved as acquisition history; the later complete captures are below.

## Completed main and secondary acquisition

The next main resume, `captures/gm1-usb-resume-3atwz8co/`, passed its live anchors
and completed `0x40000000..0x40900000`: **9,437,184 bytes**. Its SHA-256 is
`a96fb6da618b33207db0d357ac5e2513583aaa71dd01df44bed498e63992fabe`, exactly
the official `program` directory field. The
[main-program receipt](../evidence/gm1-main-program.json) records the source,
native probe and packet transcript hashes, plus recursive resume verification.

A separate 64 KiB secondary prefix at `0x41400000` established a matching
secondary reset entry. `captures/gm1-usb-resume-fveg1az5/` then checked three
anchors and completed `0x41400000..0x41760000`: **3,538,944 bytes**. SHA-256
`7e8c7d96a95a505d5500fafbd076a56e95f27267708c1f02deb2606fcd304968` exactly
matches official `program2`. The
[secondary receipt](../evidence/gm1-secondary-program.json) also verifies its
overlaps with the earlier 64 KiB prefix and independent 18 KiB data window.
Both complete captures passed the offline frame/data verifier with no errors.

These component identity results are separate from signature verification. The
subsequent [updater analysis](gm1-program-analysis.md) establishes the decoding
algorithm and verifies the normal update-directory signature independently.

## Resume after sleep, disconnect or battery restart

[The offline capture verifier](../tools/gm1_capture_verify.py) independently
checks the two-stage IN ordering, allowed read operations, frame sizes,
sequence/complement, status, checksums and every completed block against the
saved binary. An unfinished final transaction contributes no bytes to the
verified prefix. The prefix may therefore be resumed without trusting a
progress counter alone.

[The resume runner](../tools/gm1_program_resume.py) creates a new private
capture directory, copies the verified prefix, records its hash and parent
capture in `resume-manifest.json`, and compiles a fresh copy of the native tool.
The original capture is preserved. Before appending any new blocks, the native
tool repeats the public GM1 settings control and compares three complete live
blocks at the beginning, middle and end of the saved prefix. For this prefix
these are block indices **0, 599 and 1,197**. It continues at **`0x4012b800`**
only after they match. Future resume verification checks the entire lineage.

After the owner removed and reinserted the battery, all three live comparison
blocks matched and capture continued at that address. This directly confirms
address stability across that restart for the sampled program blocks. It does
not establish stability of RAM contents. The interrupted resumed capture is
`captures/gm1-usb-resume-e3ej38rd/`.

From the `gm5` checkout, the reproducible command is:

```sh
sh tools/run_gm1_usb_probe.sh resume captures/gm1-usb-resume-e3ej38rd
```

Use the newest successfully verified program/resume capture as the parent of a
later attempt. `--prepare-only` on the Python runner verifies and copies inputs,
compiles the tool and runs its self-test without enumerating USB:

```sh
python3 tools/gm1_program_resume.py captures/gm1-usb-program-qUdxsgb3 --prepare-only
python3 tools/gm1_capture_verify.py captures/gm1-usb-program-qUdxsgb3 --allow-incomplete
```

Each USB transfer retains a 1.5-second timeout. A failure stops acquisition and
saves an incomplete summary; there are no automatic retries, device resets or
driver recovery operations. A frozen camera requires owner intervention before
another attempt. An interrupted failed resume that has not passed its anchor
checks does not replace the last verified parent.

## Read probe modes

[The native probe](../tools/gm1_usb_probe_macos.c) uses Apple's existing USB
interface API without changing the selected configuration. Its experimental
framing comes from the retained [FZ30 host](service-software-findings.md) and
[GH2 camera handlers](gh2-debug-tools.md), not decoded GM1 code.

The native probe accepts these explicit modes:

| Mode | Actions |
| --- | --- |
| `inspect` | Registry identity only; no USB user client |
| `access` | Open the matching interface and inspect its three pipes; no explicit USB requests |
| `settings` | Read sixteen words, area `0x20`, indices `0x3f80..0x3f8f`, with operation `0x38` |
| `flash` | Complete `settings` first and require matching markers, then read 32 words with operation `0x70`, indices `0..31` |
| `block` | Complete `settings`, then read one 1 KiB block at `0x40000000` through `0x5c` |
| `window` | Complete `settings`, then compare forward and reverse-order reads of the first 8 KiB |
| `program` | Complete `settings`, then acquire the 9 MiB main-program interval |
| `resume` | Validate/copy the previous main prefix, check three live anchors and continue the main-program interval |
| `initializer` | Read the 32 KiB window at `0x405a3800` enclosing the main RAM initializer |
| `secondary-window` / `secondary` | Read the first 64 KiB / all 3.375 MiB at `0x41400000` |
| `secondary-data` | Read the 18 KiB window at `0x416c3000` enclosing the secondary RAM initializer |
| `resume-secondary` | Check three live secondary anchors and continue a verified secondary prefix |

The settings sample targets the public manufacturer and model strings found in
the saved GM1 fixed export. Their little-endian bytes begin `Panasonic\0` and,
sixteen bytes later, `DMC-GM1\0`. The program checks these values before it can
attempt its optional flash sample. The corresponding export coordinates are
already documented in [the settings evidence](../evidence/gm1-settings-backup.json).

For each word, the probe issues the reconstructed zero-length vendor request
`40/00`, index zero, sends a sixteen-byte read frame, waits 100 ms, then issues
request zero with index one and reads one response-type byte. It repeats the
index-one preparation and reads the entire sixteen-byte response. It accepts
only the reviewed type-eight, sequence-zero, status-`0x36` response with valid
complement, additive checksum, padding and terminator. It stops on a timeout,
USB error, short response or unexpected frame; there are no automatic retries.

The `0x70` operation uses GH2's program-relative read convention at `0x40000000`.
The recorded 64-byte GM1 sample supports that convention at index zero. This
remains a small sample rather than a full memory-map or firmware-dump validation.

The program has no settings-write or flash-write operation, arbitrary opcode or
address argument, reset, driver detach, seize, configuration change or alternate
setting change. USB OUT transfers carry read requests and transfer preparation.
The documented successful operations establish bounded GM1 compatibility; no
packet has been sent to a GM5 service interface.

## Run from the owner's Mac Terminal

With the GM1 awake and connected in the observed service state:

```sh
sh tools/run_gm1_usb_probe.sh settings
```

The runner compiles with warnings treated as errors, runs the socket/device-free
framing self-test, saves the exact source and executable hashes, and captures
the attempt in a fresh private directory under `captures/`. The result contains
`events.jsonl`, `summary.json` and, if reads succeed, `fixed-markers.bin`.
Partial results survive failures. Existing captures are never overwritten.

For an access-only comparison, replace `settings` with `access`. The `flash`
mode performs the now-recorded settings control and program-prefix read.
No root privileges, custom driver or Python package is required by the tool.

## Verification completed

The probe and shell runner compiled and passed syntax checks. The offline
self-test checks independent golden request/reply bytes, allowed address/opcode
bounds, every response truncation, an oversized response, all 128 single-bit
frame corruptions, error/status frames and unexpected padding with a valid
checksum. It also passed with address and undefined-behavior sanitizers.
Invalid CLI inputs and existing output directories were checked without USB
enumeration; earlier files were preserved. The prepared marker comparison was
independently checked against `PRIVATE.zip`.

The original tests checked frame integrity but omitted the two-stage transfer
behavior, which caused the initial normal-Terminal failure. The corrected
sequence is now demonstrated by live settings and program-prefix transcripts.
Block acquisition and both complete programs' verified resume lineages are
documented above.

Thirteen offline capture tests now check the two-stage sequence, corrupt/status
frames, rejection of write opcodes and oversized intervals, explicitly incomplete
captures, original-prefix preservation, changed live anchors, lineage cycles and
resume address advancement, nonzero-base dense/sparse coordinates, secondary
component bounds/resume and rejection of mixed-component captures. A separate
integration test exercises the actual C writer through a fake USB interface
under address/undefined-behavior sanitizers, including dense windows and both
program resume paths.
The extended word/block framing self-test also passed
under address and undefined-behavior sanitizers.

## Firmware coverage

The official GM1 1.1 directory describes six components: `program` (9 MiB),
`guires` (11 MiB), `program2` (3.375 MiB), `armcode` (3.25 MiB), `other`
(3.5 MiB) and `eep` (384 KiB), within a candidate 32 MiB layout with gaps.
The physical acquisition covers the complete main `program` and secondary
`program2` components. Offline update decoding now recovers all six component
payloads with their official hashes. This is not a physical backup of every
flash location, gap or body-specific record.

The acquired startup code at `0x400511d6..0x4005121a` supplies a concrete next
mapping: it copies flash **`0x41400000..0x41760000`**, exactly the directory's
`program2` interval, toward the secondary code's runtime space. Its linked entry
is **`0x7bc00000`**, also named by the initial reset jump. The precise alias
arithmetic and secondary initializer copies are documented in the
[secondary startup evidence](../evidence/gm1-secondary-startup.json). Both the
secondary program and its updater have now been recovered; see
[the current analysis](gm1-program-analysis.md).

## Acquired initializer and bounded key check

The [GM1 startup verifier](../tools/gm1_startup_verify.py) pins the original
physical prefix and checks the reset branch, initialized-data copy and secondary
copy directly against the MN103 instruction bytes. Its
[mapping evidence](../evidence/gm1-startup-mappings.json) establishes that
flash **`0x405a3884..0x405ab54c`** is copied to RAM **`0x70000000`**.

After another normal wake, a short acquisition read the enclosing 32 KiB window
`0x405a3800..0x405ab800`, with all 32 block replies and the settings control
validated. The raw capture is `captures/gm1-usb-initializer-RZ3N4qQ4/`.
The original native writer placed this nonzero-base window at its absolute file
offset, producing a sparse file. The verifier explicitly checks that layout
and extracts its populated interval; the original artifact is preserved. The
writer now stores such windows densely. The dense 32 KiB sample has SHA-256
`adc677a6184a3762271469a1c4ee52c109a6959f15df30fd68ff73538e22f349` and is
retained at `work/gm1-ram-initializer-window.bin`.

The initializer starts with GUI/font records. Its offset `0x28` does not hold
the GH2 key. The [bounded offline probe](../tools/gm1_initializer_key_probe.py)
tested 242 literal windows: explicit early offsets plus four-byte-aligned
16-/32-byte windows with at least 14/28 distinct bytes inside the initializer.
AES-128/256 CBC and ECB produced **no match** to the independently acquired
64-byte program prefix. CBC comparisons used later blocks so an unknown IV
would not cause a false negative for a candidate key. The
[key-check evidence](../evidence/gm1-initializer-key-check.json) records every
candidate coordinate, input hashes and OpenSSL version. This excludes that
candidate set and alignment only; it does not exclude transformed keys, other
locations or ciphers. This historical negative result is explained by the
later discovery that cipher selector three uses **five AES rounds**, whereas
the original candidate probe tested standard AES with ten/fourteen rounds.
The actual GM1 key lies at flash `0x405ab460`, mapping to RAM `0x70007bdc`,
near the end of this initializer. Its identity follows the updater's key-copy
call and complete successful decoding, not an offset guess. The GM5 key remains
unresolved.

## Sleep setting for subsequent acquisition

Panasonic's [GM1 advanced manual, page 49](https://help.na.panasonic.com/wp-content/uploads/2023/02/DMCGM1_VQT5D68_ENG.pdf#page=49)
provides **Setup (wrench) → Economy → Sleep Mode → OFF**. `Auto Monitor Off`
controls the display separately. The manual also says Economy is disabled
for ordinary PC/printer connections; behavior of this vendor service interface
is not documented there. Disabling Sleep Mode is a normal menu setting for the
owner to test, not a USB command added by this research. No packet-level
keep-awake mechanism is established.

## Update acceptance remains separate from USB readback

Panasonic supplies stock [GM1](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gm1.html)
and [GM5](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gm5.html)
update packages for the normal camera update procedure. Installing the untouched
package does not require the owner to recover its encoding key.

A modified image must reproduce the updater's accepted encoding and integrity
checks. The GM1 normal version-two path now has a traced **ECDSA P-256
directory-signature check**, independently verified against the official update.
The signed directory includes the decoded component SHA-256 fields and IVs.
The decryption key therefore does not provide the signing capability needed to
change this directory. The GM5 consumer and its key remain unestablished.
The [verified GH2 path](gh2-update-consumer.md) uses
AES-128-CBC and MD5, with no public-key signature check identified in that
reviewed path; its older format cannot be assumed to describe these cameras.
A separate [GM1 AHX path](factory-programming.md) reaches NOR programming code;
its physical entry and complete acceptance conditions need further tracing.
Only USB reads are implemented and validated. No modified package or flash
write was attempted.
