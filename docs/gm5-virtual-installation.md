# GM5 virtual NOR installation tests

The emulator now runs the installed GM5's native decoder, post-decode settings
merge and component-programming loop against a disposable 32 MiB NOR image.
The original physical backup is read-only and remains byte-identical. The
[result record](../evidence/gm5-virtual-installation.json) contains 23 passing
native controls, exact backend/scenario/trace hashes and a passing 63-test
repository run. No camera was accessed during this work.

## What executes

The installed programs are pinned to the verified backup's main and secondary
hashes. The actual installed decoder accepts the raised-version unsigned
candidate with unsigned allowance enabled, decodes every component correctly,
and rejects the complete same candidate with allowance disabled as `0x80000065`.
This stage executes the in-memory library, not the UI or file-opening part of
the update job. Its allowance is an explicit function input corresponding to
the separately tested native policy initialization.

The successful native decode context and plaintext are then loaded into the
post-decode job at `0x7bd4fd8a`. Native code performs the settings merges,
enumerates and selects components for job kind two, computes destinations,
calls the range writer and iterates through programming. The run stops at
`0x7bd50074`, before final job cleanup and reset handling.

The [native writer evidence](../evidence/gm5-native-nor-writer.json) verifies
nine instruction regions and seven relative call edges. Its geometry descriptor
specifies 32 MiB and 128 KiB sectors. The erase helper issues the native
unlock/erase command sequence. The program helper loads 512 halfwords,
confirms the buffer and polls DQ7/DQ5/DQ1. These instructions execute in the GNU
AM33-2 core; they are not replaced with direct Python writes to an image.

The virtual device implements the command subset actually used: unlock cycles,
sector erase, buffered programming, busy/status reads, reset and the buffered
error reset sequence. Erase sets a complete sector to `0xff`; programming applies
bitwise AND so zero bits cannot be restored without an erase. Read views at
`0x40000000` and the writer's `0x80000000` alias share the same virtual backing
data. Their correspondence is inferred from software and layout, not a physical
write-bus measurement.

The [Micron M29EW manufacturer datasheet](https://www.mouser.com/datasheet/2/671/m29ew_256mb_2gb-1282221.pdf)
documents compatible x16 command/status behavior and 512-word buffer boundaries.
It is a command-semantics reference, not identification of the GM5's exact part.
Geometry and command sizes used here are independently taken from the installed
firmware. Identification, protection, ECC, suspend/resume and analog timing are
outside this model.

## Explicit abstractions

| Boundary | Treatment | Limit |
| --- | --- | --- |
| RTOS mutex calls at `0x7be0826e` / `0x7be0629d` | Two explicit virtual return stubs, with a checked single-thread mutex model for ID `0x12` | Does not execute the task scheduler or test contention |
| Cache controls `0x8070` and `0x9c01202c` | Register latches; cache-tag reads begin empty | Does not prove physical cache coherence or write protection behavior |
| Calls at `0x7bd4fe14` | Explicit virtual branch to `0x7bd4fe23`, bypassing board-control helpers | Register I/O roles and physical effects are not fully modeled |
| Calls at `0x7bd4ff0d` | Explicit virtual branch to `0x7bd4ff17`, bypassing a request/poll handshake at `0x93f00030` and interrupt setup | Assumes a quiescent single-thread machine |
| Current settings RAM | Test fixture seeded from backup slot A and the adjustment area | Not a complete measured live-RAM snapshot or proof of all calibration preservation |
| UI callbacks and final cleanup | UI callbacks disabled; stop before cleanup/reset | No complete Yes-to-restart execution or full camera boot claim |

Signature decisions, component selection, settings-merge instructions, range
checks and NOR command/polling instructions are not patched out. All virtual
code overrides are retained in private scenarios and identified by address in
the public native-writer record. Unmodeled accesses and malformed bus commands
stop execution.

## Results

The complete successful installation cases each erase **244 sectors** and
program **31,152 buffers**, writing **31,899,648 payload bytes**. All eight native
writer returns are zero, no zero-to-one programming requests occur, and the
modeled mutex is released. Every byte of the resulting 32 MiB image matches an
independent expected image, including native settings-preservation changes and
unchanged gaps. The final 48 KiB adjustment payload shares a 128 KiB sector;
its remaining 80 KiB are already all `0xff` in this backup and remain so.

One successful case uses stock plaintext. The other changes only the virtual
program's policy-source byte at `0x406b1bdc` to zero before programming. Reloading
each resulting image and executing its actual initializer produces RAM policy
one for stock and zero for the virtual patch. This tests loading from programmed
bytes. It does not execute a full reset sequence or exclude a separate boot-time
authentication check. The plaintext patch is not an encoded camera update file.

| Control | Observed result |
| --- | --- |
| Erase busy/success and injected erase error | Exactly one sector changes on success; error status leaves the source image unchanged |
| Buffered-program success and injected error | Exact 1 KiB data on success; native error path/reset runs on failure |
| Programming over non-erased data | Zero-to-one requests remain masked; DQ7 polling can still appear successful, so full readback is necessary |
| Cross-sector writes | Correct erase boundaries and both cached/bus read views match |
| Misalignment, bounds, unknown commands and bus width | Rejected before an accepted write plan |
| Wrong modeled mutex identifier | Stops before NOR writes |
| Simulated power interruption | Preserves only completed operations; saved output matches the expected partial image |
| Sub-buffer declared length | Exposes the helper's implicit 1 KiB assumption and a partial overrun; never reported as success |

The programming-error installation control exposes an important caller behavior:
the range writer returns **`0x8000000c`**, but the outer job immediately overwrites
its return register at `0x7bd50035` and continues with later components. A
watchpoint records the error and subsequent calls. The test classifies that
image as incomplete using full readback comparison, even though the outer loop
reaches the modeled endpoint. This does not establish what the real final UI or
cleanup would report. Reaching a progress endpoint alone is insufficient.

The native buffer helper subtracts 1024 after every buffer; its range wrapper
checks only halfword alignment. The test harness therefore requires complete
1 KiB units for installation components. Every current GM5 component satisfies
that restriction; it must be retained when building future candidates.

## Reproduce

From the `gm5` checkout with the verified backup and private extracted installed
programs available:

```sh
python3 tools/mn103_simulator/build.py
python3 tools/gm5_virtual_install.py controls --out work/nor-controls-new
python3 tools/gm5_virtual_install.py install-tests --out work/virtual-install-new
python3 tools/gm5_writer_verify.py --out work/native-writer-new.json
python3 -m unittest discover -s tests -v
```

Each output directory must be new. `controls` runs 15 native device/writer
controls; `install-tests` runs eight decoder, installation and reloaded-initializer
controls. The latter includes two complete successes, an injected programming
failure and an interrupted write. It decodes the candidate using this camera's
installed programs before exercising the post-decode job.

Each scenario retains its explicit RAM/maps/overrides, trace, NOR event transcript,
backend hash and new private `virtual-nor.bin`. NOR input is opened read-only;
output uses exclusive file creation. Source hashes are checked again afterward.
ASan/UBSan tests additionally cover command-state boundaries and memory bounds.
The earlier verified CPU backend and the pilot backend are archived privately;
per-run hashes distinguish the installed decode that began before the buffered
error-reset model was extended.

## Next camera checkpoint

The [minimal control package](gm5-minimal-reflash-control.md) is now prepared.
It contains only unchanged installed `program2`, excluding main/boot code and
every settings/calibration payload. The encoder reproduces all eight official
ciphertexts exactly; the retained original decoder recovers the new component
byte for byte. Seven installed-native controls pass for this exact file,
including default-policy rejection, virtual installation and failure/readback
controls. The complete successful virtual NOR is identical to the backup;
all 68 repository tests pass. The exact control file has since been copied to
the identified SD card, verified and safely ejected. After the owner returned
the card, the installed updater matched the backup, English was set and
temporary policy zero was verified. The owner reported complete progress and
automatic restart; a fresh complete 3.375 MiB target readback matches the backup.
Policy returned to one and the installed version fields are unchanged. This
is preservation evidence, not conclusive erase/program proof.

The requested [one-byte main policy-zero package](gm5-policy-zero-package.md)
is now prepared separately. Eight additional exact-package native controls
verify its decoding, virtual write plan, failure detection and both initializer
loops reloaded from the programmed image. The RAM policy then becomes zero;
the complete virtual NOR has exactly one changed byte. All 71 repository tests
pass at package preparation. The new candidate is now physically installed:
ROM and RAM policy zero were measured after the owner's normal off/on cycle,
and the complete 8 MiB main readback matches the exact candidate, differing
from the original main by only the policy byte. The
[physical proof](../evidence/gm5-policy-zero-physical-proof.json) is independent
of the virtual model. The repository suite now has 73 passing tests, including
the bounded main-reader and resume checks.

The [exact-package evidence](../evidence/gm5-minimal-reflash-control.json) and
prepared camera procedure record the scope and remaining physical conditions.
Unchanged physical readback alone would not prove identical reprogramming
occurred; that was a preservation control. The subsequent distinguishable
policy change and complete main readback establish the flashing route.
The older official-payload candidate differs from the installed Japanese code.

The [handoff review](../evidence/gm5-update-handoff.json) verifies nine installed
dispatch/cleanup regions and seven call edges. The reviewed confirmation handler
calls the bridge and updater directly; the full decoder precedes programming,
and cleanup returns the saved job status. No reboot-before-verification step
was found in that reviewed local path. This does not exclude asynchronous
hardware effects or a separate boot-time check.

The remaining unmodeled work includes file opening, board/handshake/cache
behavior, a complete current settings-RAM state, final cleanup/restart execution,
and any boot-time authentication. Physical unsigned main flashing is now
verified for this candidate; a recovery procedure remains unproven.
