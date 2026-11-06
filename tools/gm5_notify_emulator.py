#!/usr/bin/env python3
"""Record reviewed native notification writes without interrupt delivery.

This is a bounded, offline peripheral model using native stop/resume stages.
It consumes only the exact MOVHU stores below. Other device accesses remain
faults, and no reply, callback execution or peer acknowledgement is fabricated.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from gm5_emulator import number, run_scenario, sha
from gm5_reflash_control import save_json
from gm5_region_emulator import SECONDARY, SECONDARY_SHA
from gm5_rtos_emulator import restored_scenario
from gm5_task_emulator import execute_switch


STORES = {0x7BC7A63F: (0x9C013004, 2), 0x7BC7A654: (0x9C013002, 2),
          0x7BC15408: (0x9C013006, 1)}


def request(result: dict, secondary: bytes) -> dict:
    """Validate an intercepted write against pinned instruction/operands."""
    pc = number(result["pc"])
    if (sha(secondary) != SECONDARY_SHA or pc not in STORES
            or secondary[pc-0x7BC00000:pc-0x7BC00000+2] != b"\xf0\x70"):
        raise ValueError("Notification write is outside the reviewed native MOVHU profile")
    regs = [number(value) for value in result["registers"]]
    address, value = STORES[pc]
    if regs[4] != address or regs[0] != value:
        raise ValueError("Notification write operands differ from the reviewed register/value")
    return {"instruction_pc": hex(pc), "register": hex(address), "bytes": 2, "value": value,
            "interrupt_delivered": False, "peer_acknowledgement_supplied": False,
            "continuation_pc": hex(pc+2)}


def run_notifications(spec: dict, backend: Path, output: Path, *, allow_same_context=False,
                      run_ready_tasks=False, max_task_switches=8) -> dict:
    if run_ready_tasks and (not allow_same_context or not 1 <= max_task_switches <= 16):
        raise ValueError("Native task execution requires conditional switches and a limit from1..16")
    output.mkdir(parents=True, exist_ok=False); output.chmod(0o700)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    secondary = SECONDARY.read_bytes()
    original = copy.deepcopy(spec)
    events, stages, switches, suspended = [], [], [], {}
    remaining = number(spec.get("budget", 1000000))
    stops = dict(spec["stops"])
    for pc in STORES:
        if pc in [number(value) for value in stops.values()]:
            raise ValueError("Scenario stop overlaps a notification interception point")
        stops[f"pending_notification_{pc:x}"] = pc
    # Default probes retain the pre-switch boundary. The opt-in extension
    # permits checked native activation frames and previously saved frames;
    # it still refuses uninitialized idle stacks or invented task completions.
    if not allow_same_context:stops["native_context_switch"] = 0x7BE02F19
    stops["native_task_entry"] = 0x7BE02F22
    current = copy.deepcopy(spec)
    guarded_stops = [{"label": "native_context_switch", "address": 0x7BE02F19, "left": "a0", "right": "a1"}] if allow_same_context else []

    def restored(directory: Path) -> dict:
        continuation = restored_scenario(original["name"], directory)
        for key in ("trace_every", "memory_observations", "watchpoints", "execution_mode"):
            if key in original: continuation[key] = original[key]
        return continuation

    def finish(directory: Path, record: dict, *, blocked_reason=None) -> dict:
        report = {"schema": 2, "model": "recorded_native_notification_writes_without_delivery",
                  "native_stages": stages, "requests": events, "delivered_interrupts": 0,
                  "task_switches": switches, "task_switch_blocked_reason": blocked_reason,
                  "native_ready_tasks_enabled": run_ready_tasks,
                  "last_directory": str(directory), "last_execution": record,
                  "native_instructions": sum(stage["execution"]["result"]["steps"] for stage in stages),
                  "modeled_store_instructions": len(events), "camera_contacted": False,
                  "other_device_accesses_remain_faults": True,
                  "driver_sha256": sha(Path(__file__).read_bytes())}
        save_json(output/"notification-report.json", report)
        return report

    for index in range(64):
        current["stops"], current["budget"] = stops, remaining
        current["stops_if_registers_differ"] = list(original.get("stops_if_registers_differ", []))+guarded_stops
        directory = output/f"native_{index:02d}"
        record = run_scenario(current, backend, directory)
        result = record["result"]
        stages.append({"directory": str(directory), "execution": record})
        remaining -= result["steps"]
        if result["stop"] == "native_context_switch" and run_ready_tasks:
            if len(switches) >= max_task_switches or remaining < 4:
                return finish(directory, record, blocked_reason="Native task-switch or instruction-budget limit reached")
            switch_directory = output/f"stack_switch_{len(switches):02d}"
            try:
                event, switch_record = execute_switch(directory, result, secondary, backend,
                                                      switch_directory, suspended,
                                                      execution_mode=original.get("execution_mode", "fast"))
            except ValueError as error:
                # Preserve the real stopped CPU state when an incoming stack
                # is unsupported, rather than manufacturing a continuation.
                if switch_directory.exists(): raise
                return finish(directory, record, blocked_reason=str(error))
            switches.append(dict(event, directory=str(switch_directory)))
            stages.append({"directory": str(switch_directory), "execution": switch_record,
                           "kind": "native_stack_switch"})
            remaining -= switch_record["result"]["steps"]
            current = restored(switch_directory)
            continue
        if not result["stop"].startswith("pending_notification_"):
            return finish(directory, record)
        event = request(result, secondary)
        if result["nor"]["pending"] or result["nor"]["phase"]:
            raise ValueError("Cannot resume a notification snapshot with an unfinished NOR command")
        if remaining < 1:
            raise ValueError("No remaining instruction budget for modeled notification store")
        remaining -= 1
        events.append(dict(event, after_native_stage=index))
        # MOVHU d0,(a0) changes memory only. Its complete modeled side effect
        # is the pending-request ledger above; registers/PSW are preserved,
        # and execution resumes at the following two-byte instruction.
        current = restored(directory)
        current["registers"]["pc"] = number(event["continuation_pc"])
        current["assumptions"].append("A verified notification-register MOVHU write records a pending request and advances PC by2; no interrupt is delivered and no peer response is supplied.")
    raise ValueError("Notification probe exceeded its64-request limit")
