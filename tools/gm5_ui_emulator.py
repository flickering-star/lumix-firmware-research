#!/usr/bin/env python3
"""Probe a larger native GM5 UI-startup boundary from verified virtual settings.

Unknown accesses remain faults. No default-zero MMIO or unreviewed hardware
responses are supplied, and no camera is contacted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from gm5_emulator import run_scenario, sha
from gm5_reflash_control import save_json
from gm5_region_emulator import inputs
from gm5_region_persistence import call, from_state
from gm5_rtos_emulator import BACKEND, restored_scenario


def probe(output: Path, backend: Path, rtos_state: Path | None = None, *, entry="startup") -> dict:
    main, _, _ = inputs()
    state = Path("work/gm5-region-package-native-2/region_programmed_settings_boot")
    if rtos_state:
        prior = json.loads((rtos_state/"report.json").read_text())
        expected = "kernel_objects_initialized" if entry == "startup" else "ui_startup_returned"
        if prior["result"]["stop"] != expected:
            raise ValueError(f"Requires a completed{expected} snapshot")
        spec = restored_scenario("native_expanded_ui_startup_with_rtos_objects", rtos_state)
        spec["registers"]["sp"] = 0x700F0000
    else:
        if entry != "startup":
            raise ValueError("Language-menu entry requires a completed UI-startup snapshot")
        spec = from_state("native_expanded_ui_startup", state/"virtual-nor.bin", main, state)
    target, mask, frame, stop = ((0x40211A38, 0, 4, "ui_startup_returned") if entry == "startup"
                                else (0x400EB4D3, 0x80, 8, "language_entry_returned"))
    spec["name"] = "native_ui_"+entry
    code = call(b"", target, mask, frame)+b"\xff"
    spec["memory"].append({"address": 0x70008000, "hex": code.hex()})
    spec["registers"]["pc"] = 0x70008000
    spec["stops"] = {stop: 0x70008000+len(code)-1}
    if entry == "language": spec["registers"]["d0"] = 0
    spec["budget"], spec["trace_every"] = 1000000, 100
    spec["memory_observations"] = [{"label": "saved_language", "address": 0x7BFB01B9, "size": 1},
                                   {"label": "ui_language", "address": 0x701AF239, "size": 1},
                                   {"label": "language_item_visibility", "address": 0x70A0E912, "size": 1}]
    spec["assumptions"].append(f"Calls the complete native{entry} function{target:#x}; full board/task startup is not supplied.")
    result = run_scenario(spec, backend, output)
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Larger native UI-startup boundary probe, with explicit unresolved state retained",
              "execution": result, "entry": entry, "completed_entry": result["result"]["stop"] == stop,
              "completed_ui_startup": entry == "startup" and result["result"]["stop"] == stop,
              "camera_contacted": False, "unknown_accesses_remain_faults": True,
              "native_rtos_state": str(rtos_state) if rtos_state else None,
              "driver_sha256": sha(Path(__file__).read_bytes())}
    save_json(output/"boundary-report.json", report)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps({"stop": result["result"]["stop"], "pc": result["result"]["pc"],
                      "steps": result["result"]["steps"], "completed_ui_startup": report["completed_ui_startup"]}), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", type=Path, default=BACKEND)
    parser.add_argument("--rtos-state", type=Path, help="Completed native RTOS kernel_objects snapshot")
    parser.add_argument("--entry", choices=("startup", "language"), default="startup")
    args = parser.parse_args()
    probe(args.out, args.backend, args.rtos_state, entry=args.entry)


if __name__ == "__main__":
    main()
