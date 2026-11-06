#!/usr/bin/env python3
"""Execute native GM5 RTOS initialization with an explicit single-CPU fixture.

This offline probe retains faults at unknown addresses. The CPU-index register
and interprocessor lock latch are assumptions, not physical measurements.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from gm5_emulator import REGISTERS, number, put, run_scenario, sha, word
from gm5_reflash_control import save_json
from gm5_region_emulator import candidate, inputs
from gm5_region_persistence import call, from_state


STATE = Path("work/gm5-region-package-native-2/region_programmed_settings_boot")
BACKEND = Path("work/toolchain/gdb-mn10300-build/gm5-mn103-sim-rtos_aliases")
CPU_INDEX = 0x8050
CONTEXT_TABLE = 0x93F0003C
CPU0_CONTEXT = 0x7BE41C10
ENTRY = 0x7BE0309B
BEFORE_SCHEDULER = 0x7BE0319B
RTOS_STORAGE = [("rtos-shared.data", 0x93F00000, 0x44),
                ("rtos-lock.data", 0x93E00000, 4),
                ("service-notification.data", 0x93F01000, 0xE10),
                ("rtos-fixed-pools.data", 0x98E35F40, 0x1980),
                ("rtos-structures.data", 0x98E3CD40, 0x98E3EA94-0x98E3CD40),
                ("rtos-local.data", 0x98E3EA94, 0x98E5D0F0-0x98E3EA94)]


def initialization_scenario() -> dict:
    main, secondary, _ = inputs()
    spec = from_state("native_cpu0_rtos_initialization", STATE/"virtual-nor.bin", main, STATE)
    # Remove the older function harness's explicit synchronization return
    # stubs. This probe executes the unchanged RTOS instruction bytes.
    spec["memory"] = []
    spec.pop("single_thread_sync", None)
    spec["ram_aliases"] = [{"address": 0x70000000, "size": 0x1000000, "alias": 0xB0000000}]
    spec["maps"] += [[CPU_INDEX, 4]]+[[at, size] for _, at, size in RTOS_STORAGE]
    initialized = secondary[0x7BE41FC8-0x7BC00000:0x7BE42830-0x7BC00000]
    shared_word = secondary[0x7BE42830-0x7BC00000:0x7BE42834-0x7BC00000]
    if len(initialized) != 0x868 or shared_word != b"\0\2\0\0":
        raise ValueError("Retained native secondary startup data differs")
    spec["memory"] += [word(CPU_INDEX, 0), put(0x98E3EA94, initialized), put(0x93F00000, shared_word)]
    spec["registers"] = {"pc": ENTRY, "sp": 0x700F0000, "psw": 0}
    spec["stops"] = {"before_scheduler_start": BEFORE_SCHEDULER}
    spec["budget"], spec["trace_every"] = 2000000, 100
    spec["watchpoints"] = {"native_mutex_initialization": 0x7BE0366C,
                          "native_mutex_tcb_initialization": 0x7BE017A2}
    spec["dumps"] += [{"name": name, "address": at, "size": size} for name, at, size in RTOS_STORAGE]
    spec["assumptions"] = [
        "The exact encoded-and-virtually-programmed region candidate and completed native settings/language RAM snapshot are restored.",
        "Native CPU0 RTOS entry is executed unchanged, stopping before its scheduler-start call; no RTOS return stubs remain.",
        "The firmware reads0x8050 as a CPU-context index; this single-CPU fixture explicitly supplies0, not a measured hardware value.",
        "The interprocessor bit-lock word0x93e00000 is a zero-initialized RAM latch with no second CPU or external contention.",
        "The context table/shared counters and context-selected128-byte lock-owner array are modeled as ordinary storage.",
        "ROM-selected shared task control blocks at0x98e3cdd0 and following use zero-initialized backing storage up to the next known startup-data interval0x98e3ea94.",
        "Three ROM-selected fixed pools0x802b..0x802d each contain16blocks of128bytes plus8bytes per-block metadata, covering0x98e35f40..0x98e378c0; their backing storage starts zero.",
        "Secondary startup initialized bytes are copied to0x98e3ea94 and0x93f00000; its documented BSS interval begins zero.",
        "Other device addresses remain unmapped, and full camera boot, scheduling, interrupts and display output are not modeled.",
        "The firmware's0x70/0xb0 RAM views share one backing buffer; cache timing/coherence are not modeled.",
        "The first three application-service notification masks at0x93f01004/08/0c use zero-initialized shared storage; no peer consumes notifications or delivers interrupts.",
    ]
    return spec


def restored_scenario(name: str, state: Path, *, cpu_index=0) -> dict:
    if cpu_index not in (0, 1):
        raise ValueError("Only the two native context indices are supported")
    spec = initialization_scenario()
    spec["name"] = name
    spec["memory"] = [word(CPU_INDEX, cpu_index)]
    # Keep the pinned code images, then replace every previous RAM/shared
    # snapshot. No context table or control block is manufactured here.
    spec["images"] = spec["images"][:2]
    preceding_spec = json.loads((state/"scenario.json").read_text())
    newly_zeroed = []
    storage_sizes = {name: size for name, _, size in RTOS_STORAGE}
    for filename, at in [("ram.data", 0x70000000), ("settings.data", 0x7BFB0000)]+[
            (name, at) for name, at, _ in RTOS_STORAGE]:
        path = state/filename
        if not path.exists() and filename == "service-notification.data":
            if any(number(start) < at+storage_sizes[filename] and at < number(start)+number(size) for start, size in preceding_spec["maps"]):
                raise ValueError("Preceding mapped service notifications have no retained dump")
            newly_zeroed.append(hex(at))
            continue
        raw_image = path.read_bytes()
        if filename == "service-notification.data" and len(raw_image) < storage_sizes[filename]:
            previous_extent = (at, len(raw_image))
            previous_maps = [(number(start), number(size)) for start, size in preceding_spec["maps"]]
            if (previous_extent not in previous_maps or any(start < at+storage_sizes[filename] and at+len(raw_image) < start+size
                                                          for start, size in previous_maps if (start, size) != previous_extent)):
                raise ValueError("Cannot extend service-ring storage over a previous mapped region")
            newly_zeroed.append(hex(at+len(raw_image)))
        spec["images"].append({"path": str(path), "address": at, "sha256": sha(raw_image)})
    source = state/"virtual-nor.bin"
    raw = source.read_bytes()
    main, _, _ = inputs()
    if len(raw) != 32*1024*1024 or raw[:len(main)] != candidate(main):
        raise ValueError("Native RTOS snapshot must retain the exact three-byte region candidate")
    spec["nor"].update(path=str(source), sha256=sha(raw))
    preceding_report = json.loads((state/"report.json").read_text())
    preceding = preceding_report["result"]["registers"]
    if any(int(value, 0) for value in preceding[14:]):
        raise ValueError("Snapshot contains nonzero registers beyond the frontend's supported register set")
    spec["registers"] = {name: int(preceding[index], 0) for name, index in REGISTERS.items()}
    spec["assumptions"] = list(preceding_report["assumptions"])
    spec["assumptions"].append(f"RAM, settings, shared RTOS storage and supported registers are restored from{state}; context index{cpu_index} is supplied explicitly.")
    if newly_zeroed:
        spec["assumptions"].append(f"Previously unmapped service-notification storage at{newly_zeroed} starts zero in this extended fixture; no earlier accesses are inferred.")
    if "command_controller" in preceding_spec:
        if any(preceding_report["result"]["command_controller"]["pending"]):
            raise ValueError("Cannot resume a snapshot with a pending command-controller operation")
        spec["command_controller"] = dict(preceding_spec["command_controller"])
    return spec


def object_probe(output: Path, backend: Path) -> dict:
    """Run only reviewed initialization subsequences, excluding the peer handshake."""
    output.mkdir(parents=True, exist_ok=False); output.chmod(0o700)
    executions = {}
    prefix = output/"context_prefix"
    spec = initialization_scenario()
    spec["name"] = "native_cpu0_context_prefix"
    spec["stops"] = {"before_peer_handshake": 0x7BE03103}
    executions["context"] = run_scenario(spec, backend, prefix)
    if executions["context"]["result"]["stop"] != "before_peer_handshake":
        raise ValueError("Native context prefix failed")
    owners = output/"lock_owners"
    spec = restored_scenario("native_lock_owner_initialization", prefix)
    spec["registers"]["pc"] = 0x7BE03108
    spec["stops"] = {"lock_owners_initialized": 0x7BE0313D}
    executions["owners"] = run_scenario(spec, backend, owners)
    if executions["owners"]["result"]["stop"] != "lock_owners_initialized":
        raise ValueError("Native lock-owner initialization failed")
    peer = output/"inactive_peer_context"
    spec = restored_scenario("native_inactive_cpu1_context_prefix", owners, cpu_index=1)
    spec["registers"].update(pc=0x7BE03F83, sp=0x700F0000, psw=0)
    spec["stops"] = {"before_peer_handshake": 0x7BE03FEB}
    executions["peer_context"] = run_scenario(spec, backend, peer)
    if executions["peer_context"]["result"]["stop"] != "before_peer_handshake":
        raise ValueError("Native inactive-peer context prefix failed")
    peer_owners = output/"inactive_peer_lock_owners"
    spec = restored_scenario("native_inactive_cpu1_lock_owners", peer, cpu_index=1)
    spec["registers"]["pc"] = 0x7BE03FF0
    spec["stops"] = {"lock_owners_initialized": 0x7BE04025}
    executions["peer_owners"] = run_scenario(spec, backend, peer_owners)
    if executions["peer_owners"]["result"]["stop"] != "lock_owners_initialized":
        raise ValueError("Native inactive-peer lock-owner initialization failed")
    objects = output/"kernel_objects"
    spec = restored_scenario("native_kernel_object_initialization", peer_owners)
    code = b""
    for target, mask, frame in [(0x7BE06D2D, 0x30, 8), (0x7BE03A0F, 0xA0, 12),
                                (0x7BE033E9, 0, 4), (0x7BE033D4, 0, 0),
                                (0x7BE032B7, 0, 0), (0x7BE03296, 0, 0),
                                (0x7BE03317, 0x30, 12)]:
        code = call(code, target, mask, frame)
    code += b"\xff"
    spec["memory"].append(put(0x70008000, code))
    spec["registers"]["pc"] = 0x70008000
    spec["stops"] = {"kernel_objects_initialized": 0x70008000+len(code)-1}
    spec["assumptions"].append("This bounded subsequence omits the CPU-peer handshake, interrupt-controller setup, task auto-activation and scheduler start.")
    spec["assumptions"].append("CPU1's native context/empty lock-owner initialization has run serially using context index1; the fixture then returns to index0. No concurrent CPU, peer tasks or interrupts execute.")
    executions["objects"] = run_scenario(spec, backend, objects)
    completed = executions["objects"]["result"]["stop"] == "kernel_objects_initialized"
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Bounded native CPU0 context, lock-owner and kernel-object initialization",
              "executions": executions, "completed_objects": completed,
              "inactive_peer_context_initialized_natively": True,
              "peer_handshake_executed": False, "scheduler_started": False,
              "camera_contacted": False, "driver_sha256": sha(Path(__file__).read_bytes())}
    save_json(output/"summary.json", report)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps({"completed_objects": completed, "result": executions["objects"]["result"]}), flush=True)
    return report


def probe(output: Path, backend: Path) -> dict:
    spec = initialization_scenario()
    record = run_scenario(spec, backend, output)
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Native CPU0 RTOS initialization before scheduler start",
              "execution": record, "completed_initialization": record["result"]["stop"] == "before_scheduler_start",
              "camera_contacted": False, "unknown_accesses_remain_faults": True,
              "driver_sha256": sha(Path(__file__).read_bytes())}
    save_json(output/"boundary-report.json", report)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps({"stop": record["result"]["stop"], "pc": record["result"]["pc"],
                      "steps": record["result"]["steps"], "completed_initialization": report["completed_initialization"]}), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", type=Path, default=BACKEND)
    parser.add_argument("--stage", choices=("boundary", "objects"), default="boundary")
    args = parser.parse_args()
    if args.stage == "objects":
        object_probe(args.out, args.backend)
    else:
        probe(args.out, args.backend)


if __name__ == "__main__":
    main()
