#!/usr/bin/env python3
"""Compare native ARM and MN103 service routing without servicing any request."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import gm5_arm_emulator as arm_cpu
from gm5_emulator import DEFAULT_BACKEND, number, put, run_scenario, sha
from gm5_reflash_control import save_json
from gm5_region_emulator import SECONDARY, SECONDARY_SHA
from gm5_region_persistence import call


IDS = (0, 1, 30, 31, 0x3FFF, 0x4000, 0x4001, 0x400B, 0x400C,
       0x7FFF, 0x8000, 0x8001, 0x800F, 0x8016, 0x8017, 0xBFFF, 0xC000, 0xFFFF)


def mn103_spec(identifier: int, *, validate=False) -> dict:
    target = 0x7BC15308 if validate else 0x7BC152E5
    code = call(b"", target, 0x80 if validate else 0, 8 if validate else 0)
    return {"name": "native_mn103_service_routing", "maps": [[0x70000000, 0x10000], [0x7BC00000, 0x360000]],
            "images": [{"path": str(SECONDARY), "address": 0x7BC00000, "sha256": SECONDARY_SHA}],
            "memory": [put(0x70008000, code+b"\xff")],
            "registers": {"pc": 0x70008000, "sp": 0x7000E000, "d0": identifier},
            "stops": {"returned": 0x70008000+len(code)}, "budget": 1000, "trace_every": 1,
            "assumptions": ["Only the unchanged native destination decoder or ID validator is called; no task, peripheral or IPC response is supplied."]}


def controls(output: Path) -> dict:
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    cases = []
    for identifier in IDS:
        for validate in (False, True):
            name = f"{'validate' if validate else 'destination'}_{identifier:04x}"
            native = run_scenario(mn103_spec(identifier, validate=validate), DEFAULT_BACKEND, output/(name+"_mn103"))
            spec = arm_cpu.scenario("native_arm_service_routing", 0x23E3C if validate else 0x23D22)
            spec["registers"]["r0"] = identifier
            counterpart = arm_cpu.run_scenario(spec, output/(name+"_arm"))
            expected = (0 if (1 <= identifier <= 30 or 0x4001 <= identifier <= 0x400B
                               or 0x8001 <= identifier <= 0x8016) else 0xFFFFFFFF) if validate else (
                                   (identifier & 0xC000) >> 14 if identifier & 0xC000 != 0xC000 else 0xFFFFFFFF)
            if (native["result"]["stop"] != "returned" or counterpart["result"]["stop"] != "returned"
                    or number(native["result"]["registers"][0]) != expected
                    or number(counterpart["result"]["registers"]["r0"]) != expected
                    or number(counterpart["result"]["registers"]["sp"]) != 0x7000E000):
                raise ValueError(f"Native ARM/MN103 service-routing control differs: {name}")
            cases.append({"name": name, "service_id": hex(identifier), "expected": hex(expected),
                          "mn103_directory": str(output/(name+"_mn103")), "mn103_execution": native,
                          "arm_directory": str(output/(name+"_arm")), "arm_execution": counterpart})
    spec = arm_cpu.scenario("native_arm_reset_vector", 0, thumb=False)
    spec["stops"] = {"native_reset_handler": 0x20}
    vector = arm_cpu.run_scenario(spec, output/"reset_vector")
    spec = arm_cpu.scenario("native_arm_system_boundary", 0, thumb=False)
    boundary = arm_cpu.run_scenario(spec, output/"system_boundary")
    if vector["result"]["stop"] != "native_reset_handler" or number(vector["result"]["pc"]) != 0x20:
        raise ValueError("Native ARM vector did not select the image's reset handler")
    if boundary["result"]["stop"] != "unmodeled_system_instruction" or number(boundary["result"]["pc"]) != 0x268:
        raise ValueError("Native ARM startup did not retain its explicit CP15 boundary")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(), "passed": len(cases)+2,
              "scope": "Native ARM/MN103 destination and service-ID comparison, ARM reset-vector and system-control boundary",
              "cases": cases, "reset_vector": vector, "system_boundary": boundary,
              "arm_source_sha256": arm_cpu.ARM_SHA, "source_is_original_physical_backup": True,
              "service_destination_800f": 2, "arm_dispatch_accepts_destination": 2,
              "camera_contacted": False, "complete_arm_boot_or_ipc_delivery": False,
              "driver_sha256": sha((output/"driver-source.py").read_bytes()),
              "limits": ["Cortex-A9 is an explicit Thumb-2-capable CPU fixture, not identified camera silicon.",
                         "The ARM service dispatcher at0x23e82/0x23f6e accepts destination2; its context/callbacks have not been booted or connected to the stopped MN103 application.",
                         "No request, interrupt, reply or acknowledgement is delivered by these pure-function comparisons.",
                         "Startup stops before the first cache/system-control instruction rather than assuming its effects."]}
    save_json(output/"summary.json", report)
    print(json.dumps({"passed": report["passed"], "camera_contacted": False}), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(); controls(args.out)


if __name__ == "__main__": main()
