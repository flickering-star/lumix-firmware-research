# GM5 native-code emulator and flash backup

The first emulator milestone is an offline function harness around GNU's
AM33-2 CPU simulator. It executes the GM5's actual instruction bytes. This directly serves
the current flashing investigation and provides a base for later device models.
A [virtual NOR model and native installation-write tests](gm5-virtual-installation.md)
now extend that base. Full camera boot, display, sensor, USB and SD-controller
models remain outside the implemented scope.

The [region/language extension](gm5-region-lock.md) now executes native settings
A/B load and selection, language normalization, menu construction/visibility,
menu navigation, NOR-backed settings save and fresh reload. It reproduces the
stock English-to-Japanese reset and retains English with the three-byte
candidate. Optional RAM change observations identify the exact resetting and
hiding stores without changing native execution. This milestone's frozen suite
passes 81 tests; the [readiness evidence](../evidence/gm5-region-readiness.json)
also records 1,756 region controls and the exact encoded package checks.

The later [native RTOS extension](gm5-native-rtos.md) raises the repository
suite to 88 tests. It executes real semaphore/mutex code, coherent `0x70`/`0xb0`
RAM views, the full UI-startup wrapper and the exact 8 MiB programming job.
The subsequent [cooperative/ARM extension](../evidence/gm5-cooperative-arm-extension.json)
passes all 105 repository tests and executes the two ready worker tasks. Its
separate [ARM backend](gm5-arm-emulator.md) compares the processors' native
service routing and extends direct receiver/callback probes. The later
[native ARM runtime](../evidence/gm5-native-arm-runtime.json) passes 111 tests
and executes native initialization, queue construction and FIFO transport.
Interrupt delivery, the ARM worker/reply path and full machine boot remain
incomplete.

## Build and run

From the `gm5` checkout, with the verified decoded official main and secondary
programs already available in `work/gm5-v11-decoded-verified/`:

```sh
python3 tools/mn103_simulator/build.py
python3 tools/gm5_emulator.py updater-tests --out work/emulator-headers-new
python3 tools/gm5_emulator.py initializer-tests --out work/emulator-initializers-new
python3 tools/gm5_emulator.py signature-tests --out work/emulator-signatures-new
python3 tools/gm5_emulator.py sha-tests --out work/emulator-sha-new
python3 tools/gm5_emulator_merge.py --out work/emulator-merge-new
python3 tools/gm5_emulator.py decoder-tests --out work/emulator-decoder-new
python3 tools/gm5_emulator.py full-decoder-tests --out work/emulator-full-new
python3 -m unittest discover -s tests -p test_gm5_emulator.py -v
```

Each output directory must be new. The full decoder suite additionally requires
the previously validated raised-version candidate at
`work/gm5-updater-prompt-0112/advertised-0112/GM5__V11.bin`; its SHA-256 is pinned.
The small `.data` decoder fixtures are emulator inputs only, never camera update
files. No emulator command enumerates or communicates with a USB device.

The builder downloads the official [GNU GDB 16.3 source archive](https://ftp.gnu.org/gnu/gdb/gdb-16.3.tar.xz)
into ignored `work/toolchain/`. The locally pinned archive SHA-256 is
`bcfcd095528a987917acf9fff3f1672181694926cc18d609c99d0042c00224c5`;
this is a sample-integrity pin, not a claim of a publisher-supplied checksum.
The build uses target `mn10300-elf` and CPU architecture `am33-2`. It installs
no system packages. A compiler, make, curl, tar and the host development headers
are required. The current build is validated on this Mac.

Two source-build recipes need a BSD sed portability fix: `;p}` becomes `;p;}`
in the module scanner. Without it, the generated module list was empty, and
the execution engine failed an assertion. The builder checks original/patched
hashes and requires engine registration before linking the harness.

GNU's decoder lists two short `swap`/`swaph` encodings that its CPU simulator
omits. The signed decoder reached short `swap` at `0x40273f84` and raised an
illegal-instruction exception. The local `short-swaps.igen` extension adds both
short aliases using the existing long-form operations. The builder pins the
original instruction-definition hash and records the extension and patched hash.
Tests compare short and long encodings, including flags and all register pairs.

Fast execution uses GNU's existing instruction-prefix hook in a separate copy
of the generated engine. The hook adds instruction budgets, stops and sampled
traces; this hook does not alter instruction semantics. Single stepping remains
available. A differential test compares the complete native header-call trace,
all reported registers and the stack between both modes. Both modes also test
host-syscall blocking, unmapped device faults and a bounded infinite loop.

The linked harness and GNU core are GPL-3.0-or-later. Notices remain in the
downloaded source; [COPYING](../tools/mn103_simulator/COPYING) is retained beside
the adapter. Exact source, build commands, libraries, instrumentation and
executable hashes are recorded in
`work/toolchain/gdb-mn10300-build/gm5-emulator-build.json`.

The [initial recorded milestone](../evidence/gm5-emulator-native-controls.json) contains
44 passing native controls, per-run scenario/trace/backend hashes, the build
receipt and a passing 61-test repository run. A separate [installed-build record](../evidence/gm5-emulator-installed-initializers.json)
adds three passing native initializer controls from this camera's verified dump. The collector verifies those
hashes before producing its report. Later [policy-lifetime controls](../evidence/gm5-update-policy-lifetime.json)
add four cases, and [virtual-installation controls](gm5-virtual-installation.md)
add 23 native cases plus a passing 63-test repository run.

## Native routines exercised

| Suite | Actual firmware execution | Check |
| --- | --- | --- |
| Header/policy | Header validator `0x7bd4fa18`, allowance initialization and inner-marker branches | Sixteen controls cover versions, model/selectors, call frames and both policy states |
| Initializers | Copy loops at `0x4000018f` and `0x40003000` | Complete destination buffers equal their ROM sources; recovered key and policy value agree |
| Virtual policy patch | Same second copy loop with simulated ROM byte `0x406b1bdc` changed from one to zero | The only changed initialized RAM byte is `0x70a68490` |
| SHA-256 | Wrapper `0x40274266`, native compression and padding | Nine inputs agree with Python hashlib, including empty input and 55/56/63/64/65-byte boundaries |
| Settings merge | Function `0x7bd4f7f7` and real helpers | Seven synthetic-buffer controls cover flags 0/1/2/4, branch arguments and region-dependent clearing; every candidate byte matches the expected result and source buffers stay unchanged |
| ECDSA | Wrapper `0x40273419` and native P-256 arithmetic | Original directory signature succeeds; altered digest/signature fail, agreeing with independent Python and LibreSSL |
| Decoder | Header reader `0x7bd4ed0a`, full library decoder `0x7bd4ee4a` | CRC, zero-marker policy and five-round AES decryption execute on the target CPU |

The full raised-version candidate completed native decoding in 2,310,979,844
instructions. All eight decoded component SHA-256 values matched the original
directory, including both programs and all settings/calibration payloads.
The initial fast run took about 83 seconds on this Mac. Timing is a measurement
of that run, not a general performance guarantee.

In the small decoder controls, unsigned allowance zero returned `0x80000065`
and a corrupted CRC returned `0x80000064`. Both rejected inputs stayed unchanged.
The complete candidate under default policy also returns `0x80000065` with its
input unchanged. The untouched signed official image completes the native
library with return zero after 6,351,693,539 instructions; all eight plaintext
hashes match. This signed run executes directory hashing, ECDSA and component
hash verification as well as decryption. A prompt on the physical camera is a
separate, earlier eligibility test.

The unsigned native branch skips component SHA verification; the harness checks
those hashes after native decryption. The separate ECDSA suite supplies its
SHA-256 digest as an input. These tests execute the decoding library; the
initial library suites do not execute the installation job. Later virtual NOR
tests execute its post-decode programming stage with explicit hardware
abstractions. The header/policy suite stops at the
signature-required branch; the signature suite executes P-256 beyond it.

## Extending a scenario

`tools/gm5_emulator.py run scenario.json --out work/scenario-new` accepts a JSON
description with explicit memory maps, hash-pinned images, initial registers,
memory overrides, stop addresses, dumps and an instruction budget. The generated
`scenario.protocol`, JSON input, trace, stdout/stderr and final register report
are retained. Use `execution_mode: "step"` for single stepping or `"fast"` for
the instrumented engine, and `trace_every` to sample long runs.

The preset maps official main ROM at `0x40000000`, secondary ROM at `0x7bc00000`,
16 MiB of virtual RAM at `0x70000000` and a zeroed settings-buffer region at
`0x7bfb0000`. These are mapped buffers, not flash or EEPROM device models.
Virtual memory overrides modify emulator state only. No physical patch file is
created by the initializer suite.

Unmapped device accesses stop with a target exception. The GNU host-syscall
instruction is intercepted before execution. Instruction budgets and wall-time
limits stop loops; firmware calls use native call frames and a mapped stack.
The presets initialize only the contexts required by the reviewed functions.
They do not fabricate successful replies from unmodeled hardware. These controls
do not certify every AM33 instruction or all firmware paths.

The complete installed Japanese programs are now extracted from the verified
physical backup and their hashes are pinned in its report. Three installed-build
initializer controls pass, including both native copy loops and the one-byte
virtual policy patch. Installed native decode acceptance/rejection and the
post-decode programming loop are also covered by the
[virtual-installation tests](gm5-virtual-installation.md). `tools/gm5_backup_analyze.py CAPTURE --out work/installed-new`
requires a complete packet-verified 32 MiB capture, compares four earlier physical
windows, and carves private main/secondary inputs with hashes. The installed
initializer regression suite accepts that capture directly:

```sh
python3 tools/gm5_emulator_installed.py captures/COMPLETE-CAPTURE --out work/installed-initializers-new
```

It tests both actual data-copy loops and the same virtual one-byte policy patch,
including the installed build's four-byte-longer second initializer. Official and
installed addresses cannot be interchanged by assuming a single global offset.
The native NOR writer now runs against a
disposable virtual image. The remaining full-machine work includes the UI/file
handoff, board/handshake/cache behavior and final cleanup/restart.

## Settings preservation is a separate stage

The normal installation bridge at `0x4023c141` supplies job kind two. The
post-decode job contains separate component-selection loops, a settings merge
and the later programmer. Its `eep_ow_a` / `eep_ow_b` merge function at
`0x7bd4f7f7` copies selected current settings ranges into the candidate buffer.
With container flags four, that includes the settings word containing the
language field. It also copies an 8 KiB current buffer returned by the native
helper at `0x40285000`. The seven synthetic merge controls verify the observed
copies and conditional word clearing; no real calibration contents are used.

This explains why byte-identical decoded payloads alone are not a complete
installation simulation. The eventual virtual installation model must account
for these mutations and the actual writer's component selection. The virtual-installation tests now exercise these merges before actual native
programming commands. Their current-settings RAM is an explicit fixture seeded
from backup storage. The merge controls do not prove that every physical
calibration value would survive a flash. No physical installation is performed
by the emulator.

## Read-only, resumable physical backup

On the connected Mac, one process at a time:

```sh
python3 tools/gm5_flash_backup.py --prepare-only
python3 tools/gm5_flash_backup.py
python3 tools/gm5_flash_backup.py --resume captures/PREVIOUS-CAPTURE
```

The fixed range is `0x40000000..0x42000000`, 32 MiB in 1 KiB blocks with the
proven 100 ms pacing. The native tool checks the exact GM5 service identity and
retained settings control, sends settings/memory reads only, and stops on the
first unexpected response. It issues no RAM-policy writes, NOR programming,
reset, configuration change or automatic retry. Do not run other camera USB
tools concurrently. Camera sleep can interrupt acquisition.

A resume first replays the saved packet transcript offline, verifies the saved
prefix hash, and copies it into a fresh capture without altering the original.
After wake/reconnect, three live anchors from the beginning, middle and end of
that prefix must match before continuing at the next address. Those checks
establish continuity across the restart; they do not make the acquisition
atomic. While active, the file is `result/program-main.bin`; after stopping it
is renamed `result/flash32m.bin`. The latter can still be partial: always check
`verification.json` for `complete` and its verified byte count.

The first live capture, `gm5-flash-backup-n_5fpkw_`, retained 22,987,776 verified
bytes, SHA-256
`fce983814656d8cd6cf549e2b6fdb0d48a9d4e73eeaa57fe3bd2406c50eff5a1`.
Its next address was `0x415ec400`. After replacing the battery, the owner
reconnected the GM5. Resume capture `gm5-flash-backup-9z320rtf` verified all three
live anchors and completed acquisition: **33,554,432 bytes**, SHA-256
`c51dca467a8bd24c0be75915acb54692f9213a7d7b9896c5e50a010d830a35ca`.
The [complete backup record](../evidence/gm5-flash-backup.json) includes both
packet verifications, four matching earlier physical windows and a fresh
readback of RAM flag one. The raw file is
`captures/gm5-flash-backup-9z320rtf/result/flash32m.bin`, protected read-only.
Raw flash/calibration material stays in ignored private captures; public
evidence contains hashes and verification summaries.

The original installed main slice is 8 MiB, SHA-256
`5316a6ff14152126a88ce02125e85d713e710c8dd1159dee2ab890e4ff345966`;
the secondary slice is 3.375 MiB, SHA-256
`d3953f29553723e7375c537f2cf8e673ade4924e6c0de161243cf106575a74e7`.
At identical offsets they differ from the official programs in 13,698 and
1,520,048 bytes respectively. Those counts include alignment shifts; they are
not counts of independent code changes. The installed second initializer
copies 598,452 bytes rather than the official 598,448. Its stock and virtual
policy-patched runs differ only at RAM `0x70a68490`, from one to zero.

This backup covers the mapped NOR range, not all RAM or any independent device
storage. Reading it is not a tested recovery method. No hardware programmer or
recovery writer has been established. A later
[modified unsigned main installation](gm5-policy-zero-package.md) is physically
verified: exactly one initializer byte changes, the complete 8 MiB main matches
the candidate, and ROM/RAM policy zero persists through a normal off/on cycle.
That physical validation does not turn the function harness into a complete
machine emulator. The bounded main-reader/resume extension has 73 passing
repository tests; the [physical proof](../evidence/gm5-policy-zero-physical-proof.json)
retains all readback and request-audit evidence.
