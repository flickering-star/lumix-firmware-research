# GM5 native RTOS and UI extension

The emulator now executes the installed firmware's synchronization routines
instead of replacing their returns. The complete UI-startup wrapper returns,
and the exact three-byte language candidate completes its 8 MiB virtual
programming job. The [verified evidence](../evidence/gm5-native-rtos.json)
records 13 native API/writer controls, three full programming-job controls and
88 passing repository tests. These are offline results; the language patch
has not been installed on the camera.

## Native initialization and execution

The retained firmware selects a context using the word at `0x8050` and the
table at `0x93f0003c`. Native startup assigns CPU0 context `0x7be41c10` and
CPU1 context `0x7be41d9c`. The harness executes both context prefixes and their
empty lock-owner initialization serially, then initializes CPU0 queues, objects,
fixed pools and idle-task state. The object stage executes 104,443 instructions.

The CPU-index value, uncontended shared bit-lock storage and zero backing for
ROM-selected control blocks/pools are explicit fixtures. The full RTOS entry
still reaches a peer handshake at `0x8950`; that handshake is not fabricated.
The bounded sequence excludes controller setup, automatic task activation and
scheduler start. Task7 is activated through native `0x7be02b38`, then selected
explicitly as the serial current-task fixture. Its actual task entry does not run.

| Native path | Verified result | Remaining scope |
| --- | --- | --- |
| Mutex6, `0x7be027a7` / `0x7be0805d` | Owner becomes task7, release clears it, recursive/unowned operations return -28 | No preemption or contending task |
| Semaphore18, `0x7be0826e` / `0x7be0629d` | Token 1→0→1, overflow returns -43, invalid IDs return -18 | Blocking/scheduler paths are not complete |
| Range writer `0x7bd4eb0d` | Native synchronization and complete virtual-image checks pass for success, program error and power cut | Deterministic NOR timing/cache assumptions remain |
| Exact region programming job | 64 sector erases and 8,192 buffer programs; complete 32 MiB result differs at exactly the three language bytes | Two earlier explicit board/shutdown skips remain; stops before final cleanup/restart |
| UI startup `0x40211a38` | Complete wrapper returns after 4,675 instructions with caller stack restored | Logical initialization, without display/sensor tasks |

The writer's older checked synchronization model remains in its historical
experiments. These newer tests run unchanged semaphore/mutex instruction bytes
and configure no return-stub service model.

## Coherent RAM views and calling conventions

Main startup at `0x40003144` explicitly translates addresses from the
`0x70000000` RAM range to the corresponding `0xb0000000` view. Optional
`RAM_ALIAS` uses GNU's shared-buffer memory alias support, so native writes
through either view are immediately visible through the other. This represents
coherent storage, without modeling cache latency or hardware cache maintenance.

JSON scenarios pair an existing exact RAM map with:

```json
"ram_aliases": [
  {"address": "0x70000000", "size": "0x1000000", "alias": "0xb0000000"}
]
```

The frontend requires an exact matching map and rejects overlaps or other
address translations. The backend independently restricts aliases to bounded
`0x70` RAM and matching `0xb0` views. Four native tests cover both write/read
directions, fast/step equality, RAM observations and invalid mappings.

The UI callback at `0x400ea07a` allocates its own `movm`/local frame and must be
entered with `CALLS`. A first experimental trampoline also allocated a `CALL`
frame, causing a stale return address after correctly selecting English. This
was a harness error, not a firmware or hardware finding. Three regression tests
now distinguish both calling conventions and detect that double-frame error.

## Current larger-menu boundary

The complete Language entry `0x400eb4d3` returns and initializes its logical
menu state. Its button-event handler receives event family `0x0f000002`:
parameter 6 advances to English, and parameter 7 confirms. Native traces identify
the pending-language store at `0x4012878e` and confirmation stores at
`0x400ea1f0` / `0x400ea1f6`.

Full confirmation also restores the parent menu. The actual setup dispatcher
saves that context through `0x40130a85` before entering Language. Initializing
the natural parent menu at `0x4010876d` now exposes more of the application
service layer. Its native prefix `0x7bc15b13..0x7bc15b3e` sets the context at
`0x93f0000c` and its registration table; the prefix stops before controller setup.
The first service notification masks at `0x93f01004/08/0c` have explicit shared
storage, without a peer consuming requests or delivering interrupts.

The published 88-test parent-menu probe stops at a **2-byte write of 2 to `0x9c013004`**,
instruction **`0x7bc7a63f`**. The same routine selects `0x9c013002` for the other
CPU index, suggesting a software-interrupt/notification request. Delivery and
the register's complete hardware behavior remain unmodeled. The exception
vector reported by GNU is `0x40000008`; it is not the faulting instruction.
The complete entry/event/confirmation/save/reload UI flow is therefore still
incomplete. The earlier bounded native menu-navigation/save/reload proof
remains valid and separately documented in the [region research](gm5-region-lock.md).

A subsequent optional stop/resume model in `gm5_notify_emulator.py` records
the reviewed notification writes as pending requests. It validates the
exact native instruction, address and value, preserves registers/PSW, and
supplies no interrupt delivery or peer acknowledgement. Two additional targeted
tests verify the consumed `MOVHU` semantics and profile guards. The first probe
then reaches a **2-byte read of `0x9c010008` at `0x7bc8b9ea`**, after 53,481
native instructions. The following routine sets and polls **bit 4 (`0x0010`)**
in that register and `0x9c01000e`.

An optional `command_controller` fixture completes only those two reviewed
command words after a configurable number of busy reads. Other bits start zero;
the controller's identity, physical work and actual timing remain unknown.
Four tests cover several delays, stuck-busy behavior, unknown operations and
adjacent unmapped registers. At this historical milestone the original research
checkout passed 97 tests; the curated public suite is reported separately. The separate `command_latches`
binary preserves the previous releases.

Native `0x7bc1522e` initializes all six shared-ring capacities and empty offsets
in `0x93f01000..0x93f01e10`. The notification profile also records the native
`0x7bc15408` write of 1 to `0x9c013006`. There is still no interrupt delivery.

## Native cooperative task boundary

The optional `cooperative_stops` backend adds conditional instruction stops
without changing CPU instruction semantics. A stop at `0x7be02f19` applies only
when A0 and A1 differ, allowing same-task stack transitions to execute normally.
Two native tests check both branches and fast/step equality.

`gm5_task_emulator.py` checks the native kernel's selected task against the
pinned CPU0 task table, runnable state, saved-stack range and activation frame.
An already suspended task must match the frame saved by an earlier native
switch in the same run. The unchanged three-instruction stack helper saves SP,
loads the new SP and returns into its frame. The adapter checks restored
registers and every retained storage dump; only the outgoing SP slot may change.
It supplies no task selection, frame, reply or acknowledgement. Three additional
tests cover native fast/step execution and invalid code, device and frame cases.

`work/gm5-native-language-ready-tasks-2` executes **task7 → task60 → task61**,
including both workers' native entry at `0x40284f77`. The parent-menu probe totals
60,342 native instructions and records three pending notification writes. It
stops before switching to idle task0 (`0x70a01d70`), whose saved SP is zero in
this bounded initialization. Task7 and both workers are waiting; the adapter
does not invent an idle stack or mark the outstanding request complete.

The [cooperative/ARM evidence](../evidence/gm5-cooperative-arm-extension.json)
retains the source/build release, each native stage and the complete 105-test
repository run (109.159 seconds, no skips). The earlier 88-test publication and
81-test region readiness remain unchanged historical milestones.

The shared ring at `0x93f01110` contains two actual `0x800f` messages. Native
`0x7bc152e5` maps their high bits to destination 2. The separate ARM firmware
contains the corresponding ring/register references and a dispatcher for
destination 2; see the [ARM extension](gm5-arm-emulator.md). Its native
receiver/callback/kernel queue transport now passes ten controls following
native kernel/object initialization, with 111 passing repository tests. The
worker/reply path remains incomplete. The complete
entry/event/confirmation/save/reload UI flow is still incomplete.

## Reproduction and retained releases

Use new output directories from the checkout root:

```sh
python3 tools/mn103_simulator/build.py --variant rtos_aliases
python3 tools/gm5_rtos_emulator.py --stage objects --out work/rtos-objects-new
python3 tools/gm5_native_rtos_controls.py --state work/rtos-objects-new/kernel_objects --out work/rtos-api-new
python3 tools/gm5_native_rtos_install.py --state work/rtos-api-new/native_task7_activation --out work/rtos-install-new
python3 tools/gm5_ui_emulator.py --rtos-state work/rtos-objects-new/kernel_objects --out work/rtos-ui-new
python3 -m unittest discover -s tests -v
```

The larger-menu boundary can be reproduced with
`tools/gm5_native_language_flow.py --state work/rtos-ui-new --out work/rtos-language-new`;
it currently stops at the explicit unresolved notification-register access.
All commands are offline and contain no camera transport.

To reproduce the newer cooperative boundary, use the separately built backend:

```sh
python3 tools/mn103_simulator/build.py --variant cooperative_stops
python3 tools/gm5_native_language_flow.py --state work/gm5-ui-startup-with-native-rtos-3 --record-notifications --command-completion --cooperative --run-ready-tasks --out work/rtos-ready-tasks-new
```

That command retains its boundary report and exits with an incomplete-flow
error at the uninitialized idle stack. It is not a successful complete UI run.

The separately named executable/receipt preserves the old default and
`language_watch` releases. CPU-engine and linked GNU-library hashes remain
identical. The evidence retains the new build/source release, per-run scenario,
trace/input/output hashes and the unresolved fault. Historical language
readiness verifies its own frozen release, even as current emulator sources
advance. The encoded candidate remains
`4954b517462b8ee5f900945496b882ddfa45f97b540f0d1dad6dcdf706ea50c7`.
