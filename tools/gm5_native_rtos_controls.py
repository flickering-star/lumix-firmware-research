#!/usr/bin/env python3
"""Exercise unchanged GM5 synchronization and NOR-writer code offline.

A native-activated task is selected explicitly as the current context. This
tests serial API calls, not task execution, preemption or concurrent CPUs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct

from gm5_emulator import put, run_scenario, sha, word
from gm5_reflash_control import save_json
from gm5_region_emulator import inputs
from gm5_region_persistence import call
from gm5_rtos_emulator import BACKEND, CPU0_CONTEXT, restored_scenario
from gm5_virtual_install import BUFFER, INPUT, SECTOR, erased


STATE = Path("work/gm5-native-rtos-objects-5/kernel_objects")
CURRENT_TASK = 0x70A01D48
TASK_ID, MUTEX_ID, SEMAPHORE_ID = 7, 6, 0x12


def u16(raw: bytes, at: int) -> int:
    return struct.unpack_from("<H", raw, at)[0]


def u32(raw: bytes, at: int) -> int:
    return struct.unpack_from("<I", raw, at)[0]


def callback_trampoline(target: int, stub=0x70008000) -> bytes:
    """CALLS for a callee that allocates its own MOVM/local frame."""
    return b"\xfc\xff"+struct.pack("<i", target-stub)+b"\xff"


def control_addresses() -> tuple[int, int, int]:
    _, secondary, _ = inputs()
    context = CPU0_CONTEXT-0x7BC00000
    values = []
    for offset, index in ((204, TASK_ID), (224, MUTEX_ID), (208, SEMAPHORE_ID)):
        table = u32(secondary, context+offset)
        values.append(u32(secondary, table-0x7BC00000+4*(index-1)))
    return tuple(values)


def control_scenario(name: str, state: Path, target: int, mask: int, frame: int, argument: int,
                     *, callback_abi=False) -> dict:
    spec = restored_scenario(name, state)
    task, mutex, semaphore = control_addresses()
    if callback_abi:
        if mask or frame:
            raise ValueError("CALLS callbacks allocate their own frame; CALL mask/frame must be zero")
        code = callback_trampoline(target)
    else:
        code = call(b"", target, mask, frame)+b"\xff"
    spec["memory"] += [put(0x70008000, code), word(CURRENT_TASK, task)]
    spec["registers"].update(pc=0x70008000, sp=0x700F0000, d0=argument)
    spec["stops"] = {"returned": 0x70008000+len(code)-1}
    spec["budget"], spec["trace_every"] = 1000000, 100
    spec["memory_observations"] = [
        {"label": "mutex_state", "address": mutex, "size": 40},
        {"label": "semaphore_state", "address": semaphore, "size": 32},
    ]
    spec["assumptions"].append("A native-activated CPU0 task7 is selected by the fixture as current; the scheduler and actual task entry do not execute. API calls run serially without preemption.")
    if callback_abi:
        spec["assumptions"].append("CALLS invokes a callback that saves its own registers/local frame; no automatic CALL frame is allocated.")
    return spec


def controls(output: Path, state: Path, backend: Path) -> dict:
    previous = json.loads((state/"report.json").read_text())
    if previous["result"]["stop"] != "kernel_objects_initialized":
        raise ValueError("Requires completed bounded native kernel-object initialization")
    output.mkdir(parents=True, exist_ok=False); output.chmod(0o700)
    task, mutex, semaphore = control_addresses()
    original_nor = (state/"virtual-nor.bin").read_bytes()
    cases = []

    def execute(spec: dict, expected_stop="returned", status: int | None = 0) -> Path:
        directory = output/spec["name"]
        record = run_scenario(spec, backend, directory)
        result = record["result"]
        if result["stop"] != expected_stop:
            raise ValueError(f"Native control stopped unexpectedly: {spec['name']}: {result}")
        if status is not None and int(result["registers"][0], 0) != status & 0xFFFFFFFF:
            raise ValueError(f"Native control status differs: {spec['name']}: {result}")
        if expected_stop == "returned":
            for name, index in (("sp", 8), ("d2", 2), ("d3", 3), ("a2", 6), ("a3", 7)):
                if int(result["registers"][index], 0) != spec["registers"][name]:
                    raise ValueError(f"Native control clobbered caller {name}: {spec['name']}")
        if result["services"] is not None:
            raise ValueError("Native controls unexpectedly used the older synchronization-stub model")
        cases.append({"name": spec["name"], "execution": record, "native_rtos_code_unchanged": True})
        return directory

    # Activate an already native-initialized private task. Its entry function
    # is not called; the API fixture explicitly selects its resulting TCB.
    spec = control_scenario("native_task7_activation", state, 0x7BE02B38, 0xE0, 16, 0)
    spec["registers"]["a0"] = task
    spec["memory"] = [item for item in spec["memory"] if int(item["address"], 0) != CURRENT_TASK]
    activated = execute(spec, status=None)
    ram = (activated/"ram.data").read_bytes()
    at = task-0x70000000
    if u16(ram, at+16) != TASK_ID or u16(ram, at+12) != 2 or u16(ram, at+8) != u16(ram, at+80):
        raise ValueError("Native task activation did not initialize ID, ready state and priority")

    acquired = execute(control_scenario("native_mutex_acquire", activated, 0x7BE027A7, 0xF0, 20, MUTEX_ID))
    if u16((acquired/"ram.data").read_bytes(), mutex-0x70000000+24) != TASK_ID:
        raise ValueError("Native mutex did not record the current task owner")
    execute(control_scenario("native_mutex_recursive_error", acquired, 0x7BE027A7, 0xF0, 20, MUTEX_ID), status=-28)
    released = execute(control_scenario("native_mutex_release", acquired, 0x7BE0805D, 0xF0, 24, MUTEX_ID))
    if u16((released/"ram.data").read_bytes(), mutex-0x70000000+24) != 0:
        raise ValueError("Native mutex did not clear its owner")
    execute(control_scenario("native_mutex_unowned_error", activated, 0x7BE0805D, 0xF0, 24, MUTEX_ID), status=-28)
    waited = execute(control_scenario("native_semaphore_wait", activated, 0x7BE0826E, 0xF0, 20, SEMAPHORE_ID))
    if u32((waited/"ram.data").read_bytes(), semaphore-0x70000000+24) != 0:
        raise ValueError("Native semaphore wait did not consume its token")
    signaled = execute(control_scenario("native_semaphore_signal", waited, 0x7BE0629D, 0xE0, 16, SEMAPHORE_ID))
    if u32((signaled/"ram.data").read_bytes(), semaphore-0x70000000+24) != 1:
        raise ValueError("Native semaphore signal did not restore its token")
    execute(control_scenario("native_semaphore_overflow_error", activated, 0x7BE0629D, 0xE0, 16, SEMAPHORE_ID), status=-43)
    for target, mask, frame, name in ((0x7BE027A7, 0xF0, 20, "mutex"), (0x7BE0826E, 0xF0, 20, "semaphore")):
        execute(control_scenario(f"native_{name}_invalid_id", activated, target, mask, frame, 0), status=-18)

    # Keep all ordinary synchronization calls above free of NOR changes.
    for item in cases:
        directory = output/item["name"]
        if (directory/"virtual-nor.bin").read_bytes() != original_nor:
            raise ValueError("Synchronization/activation changed virtual NOR")

    offset = 0x1E00000
    payload = bytes((i*29+7)%256 for i in range(SECTOR))
    for name, fail_program, cut_after, stop, status in (
            ("native_writer_rtos_success", 0, 0, "returned", 0),
            ("native_writer_rtos_program_error", 1, 0, "returned", 0x8000000C),
            ("native_writer_rtos_power_cut", 0, 2, "nor_power_cut", None)):
        spec = control_scenario(name, activated, 0x7BD4EB0D, 0xF0, 64, offset)
        spec["memory"] += [put(INPUT, payload), word(0x700F0004, 0)]
        spec["registers"].update(a0=0x70A92A94, a1=INPUT, d1=len(payload))
        spec["nor"].update(fail_program=fail_program, cut_after=cut_after)
        spec["budget"], spec["trace_every"] = 20000000, 1000
        directory = execute(spec, stop, status)
        wanted = erased(original_nor, offset, len(payload))
        if name.endswith("success"):
            wanted[offset:offset+len(payload)] = payload
        elif cut_after:
            wanted[offset:offset+BUFFER] = payload[:BUFFER]
        if (directory/"virtual-nor.bin").read_bytes() != wanted:
            raise ValueError(f"Native RTOS-backed writer readback differs: {name}")
        if stop == "returned" and u32((directory/"ram.data").read_bytes(), semaphore-0x70000000+24) != 1:
            raise ValueError("Native writer failed to restore its semaphore token")
        cases[-1]["complete_virtual_nor_matches_expected"] = True

    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Native task activation, mutex/semaphore controls and native NOR writer without RTOS return stubs",
              "cases": cases, "passed": len(cases), "camera_contacted": False,
              "task_fixture": {"id": TASK_ID, "tcb": hex(task), "native_activation": True,
                               "current_task_selected_by_fixture": True, "task_entry_or_scheduler_executed": False},
              "objects": {"mutex6_tcb": hex(mutex), "semaphore18_tcb": hex(semaphore)},
              "limits": ["Serial task-context fixture; no real preemption, interrupts or concurrent CPU behavior.",
                         "The peer context and empty owner array were initialized natively; its task runtime is inactive.",
                         "Existing deterministic NOR and cache-latch assumptions remain; full camera boot is not modeled."],
              "driver_sha256": sha(Path(__file__).read_bytes())}
    save_json(output/"summary.json", report)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    print(f"Passed{len(cases)} native RTOS/writer controls with no synchronization return stubs", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument("--backend", type=Path, default=BACKEND)
    args = parser.parse_args()
    controls(args.out, args.state, args.backend)


if __name__ == "__main__":
    main()
