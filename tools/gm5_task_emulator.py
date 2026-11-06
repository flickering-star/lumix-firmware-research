#!/usr/bin/env python3
"""Validate and execute native cooperative stack switches, entirely offline.

The kernel has already selected the next task when it reaches SWITCH_PC.
This adapter never selects a task, constructs a stack, or acknowledges IPC.
It permits a reviewed native activation frame or an exact frame saved by an
earlier native switch in this run. Uninitialized idle stacks remain a boundary.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct

from gm5_emulator import number, run_scenario, sha
from gm5_region_emulator import SECONDARY_SHA
from gm5_rtos_emulator import CPU0_CONTEXT, restored_scenario


SWITCH_PC = 0x7BE02F19
SWITCH_CODE = bytes.fromhex("f8f500f8f000dff010")
FIRST_FRAME_PC = 0x7BE02CDA
CURRENT_TASK = 0x70A01D48


def snapshot_bytes(directory: Path, address: int, size: int) -> bytes:
    """Read retained ordinary storage; never turn an unknown address into zero."""
    spec = json.loads((directory/"scenario.json").read_text())
    for dump in spec.get("dumps", []):
        at, extent = number(dump["address"]), number(dump["size"])
        if at <= address and address+size <= at+extent:
            raw = (directory/dump["name"]).read_bytes()
            if len(raw) != extent:
                raise ValueError("Native task snapshot has a truncated ordinary-storage dump")
            return raw[address-at:address-at+size]
    raise ValueError(f"Native task address {address:#x}+{size:#x} is outside retained storage")


def u32(raw: bytes, offset=0) -> int:
    return struct.unpack_from("<I", raw, offset)[0]


def inspect_switch(directory: Path, result: dict, secondary: bytes,
                   suspended: dict[int, dict]) -> dict:
    """Reject unknown code, tasks and stacks before letting the CPU execute."""
    if (sha(secondary) != SECONDARY_SHA or number(result["pc"]) != SWITCH_PC
            or secondary[SWITCH_PC-0x7BC00000:SWITCH_PC-0x7BC00000+9] != SWITCH_CODE):
        raise ValueError("Task switch is outside the pinned native stack-helper profile")
    if result["nor"]["pending"] or result["nor"]["phase"]:
        raise ValueError("Cannot checkpoint a task switch with an unfinished NOR command")
    if any(result.get("command_controller", {}).get("pending", [])):
        raise ValueError("Cannot checkpoint a task switch with a pending controller command")
    regs = [number(value) for value in result["registers"]]
    if any(regs[14:]):
        raise ValueError("Task switch contains unsupported nonzero extra CPU registers")
    next_slot, previous_slot, outgoing_sp = regs[4], regs[5], regs[8]
    if next_slot == previous_slot or (next_slot | previous_slot | outgoing_sp) & 3:
        raise ValueError("Task switch requires distinct aligned stack slots and a stack")
    next_tcb, previous_tcb = next_slot-24, previous_slot-24
    context = CPU0_CONTEXT-0x7BC00000
    table, following = u32(secondary, context+204), u32(secondary, context+208)
    # The pinned CPU0 table occupies this exact ROM interval (151 entries).
    if (table, following) != (0x7BE410CC, 0x7BE41328):
        raise ValueError("Pinned native task table layout changed")

    def task(at: int) -> dict:
        data = snapshot_bytes(directory, at, 96)
        identifier, state = struct.unpack_from("<H", data, 16)[0], struct.unpack_from("<H", data, 12)[0]
        if identifier == 0:
            raise ValueError(f"Idle task at {at:#x} has no validated saved stack (SP={u32(data, 24):#x})")
        if not 1 <= identifier <= (following-table)//4:
            raise ValueError("Task has no reviewed CPU0 ROM-table identifier")
        if u32(secondary, table-0x7BC00000+4*(identifier-1)) != at:
            raise ValueError("Task control block differs from its pinned ROM-table entry")
        return {"tcb": at, "id": identifier, "state": state,
                "saved_sp": u32(data, 24), "entry": u32(data, 76),
                "stack_base": u32(data, 88), "stack_size": u32(data, 84)}

    incoming, outgoing = task(next_tcb), task(previous_tcb)
    if u32(snapshot_bytes(directory, CURRENT_TASK, 4)) != next_tcb or incoming["state"] != 1:
        raise ValueError("Native kernel has not selected this runnable incoming task")
    saved_sp = incoming["saved_sp"]
    if saved_sp & 3:
        raise ValueError("Incoming native task frame is not aligned")
    frame = snapshot_bytes(directory, saved_sp, 20)
    snapshot_bytes(directory, outgoing_sp, 20)
    if next_tcb in suspended:
        prior = suspended[next_tcb]
        if saved_sp != prior["saved_sp"] or sha(frame) != prior["frame_sha256"]:
            raise ValueError("Incoming suspended frame differs from its earlier native save")
        frame_kind = "previously_saved_by_native_switch"
    else:
        start, size = incoming["stack_base"], incoming["stack_size"]
        if not (0x70000000 <= start < start+size <= 0x71000000
                and saved_sp == start+size-20 and u32(frame, 16) == FIRST_FRAME_PC
                and u32(frame, 4) == incoming["entry"] and u32(frame) == 0 and u32(frame, 8) == 0
                and (0x40000000 <= incoming["entry"] < 0x40800000
                     or 0x7BC00000 <= incoming["entry"] < 0x7BF60000)):
            raise ValueError("Incoming task lacks a reviewed native activation or suspended frame")
        frame_kind = "native_activation_frame"
    return {"previous_task": outgoing, "next_task": incoming,
            "previous_stack_slot": previous_slot, "next_stack_slot": next_slot,
            "outgoing_sp": outgoing_sp, "incoming_sp": saved_sp,
            "frame_words": list(struct.unpack("<5I", frame)), "frame_sha256": sha(frame),
            "frame_kind": frame_kind, "continuation_pc": u32(frame, 16)}


def execute_switch(directory: Path, result: dict, secondary: bytes, backend: Path,
                   output: Path, suspended: dict[int, dict], *, execution_mode="fast") -> tuple[dict, dict]:
    event = inspect_switch(directory, result, secondary, suspended)
    spec = restored_scenario("native_cooperative_stack_switch", directory)
    spec["stops"] = {"native_stack_restored": event["continuation_pc"]}
    spec["budget"], spec["trace_every"] = 4, 1
    spec["execution_mode"] = execution_mode
    spec["assumptions"].append("The native kernel chose a runnable task with a checked activation/saved frame. The unchanged three-instruction stack helper executes; the adapter supplies no TCB, stack frame, task choice, interrupt or IPC reply.")
    record = run_scenario(spec, backend, output)
    (output/"task-driver-source.py").write_bytes(Path(__file__).read_bytes())
    actual = record["result"]
    if actual["stop"] != "native_stack_restored" or actual["steps"] != 3:
        raise ValueError("Native stack helper did not reach its checked frame continuation")
    registers = [number(value) for value in actual["registers"]]
    if registers[8] != event["incoming_sp"]+16 or registers[9] != event["continuation_pc"]:
        raise ValueError("Native stack helper restored an unexpected SP/PC")
    for index, value in zip((7, 6, 3, 2), event["frame_words"][:4]):
        if registers[index] != value:
            raise ValueError("Native stack helper restored unexpected callee-saved registers")
    for index in set(range(len(registers)))-{2, 3, 6, 7, 8, 9}:
        if registers[index] != number(result["registers"][index]):
            raise ValueError("Native stack helper changed an unexpected CPU register")
    # Only the outgoing stack-pointer slot may change in ordinary storage.
    previous_spec = json.loads((directory/"scenario.json").read_text())
    for dump in previous_spec.get("dumps", []):
        expected = bytearray((directory/dump["name"]).read_bytes())
        at, slot = number(dump["address"]), event["previous_stack_slot"]
        if at <= slot and slot+4 <= at+len(expected):
            struct.pack_into("<I", expected, slot-at, event["outgoing_sp"])
        if (output/dump["name"]).read_bytes() != expected:
            raise ValueError("Native stack helper changed storage beyond its outgoing SP slot")
    if (output/"virtual-nor.bin").read_bytes() != (directory/"virtual-nor.bin").read_bytes():
        raise ValueError("Native stack helper unexpectedly modified virtual flash")
    suspended.pop(event["next_task"]["tcb"], None)
    suspended[event["previous_task"]["tcb"]] = {
        "saved_sp": event["outgoing_sp"],
        "frame_sha256": sha(snapshot_bytes(output, event["outgoing_sp"], 20)),
    }
    event["task_driver_sha256"] = sha((output/"task-driver-source.py").read_bytes())
    return event, record
