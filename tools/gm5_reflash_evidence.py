#!/usr/bin/env python3
"""Verify and publish minimal-reflash evidence without firmware/calibration bytes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from gm5_emulator import sha
from gm5_prompt_package import artifact
from gm5_reflash_control import DESTINATION, LENGTH, validate_scope, save_json
from gm5_virtual_install import BACKUP, BACKUP_SHA, BUFFER, SECTOR, SECONDARY_SHA


def checked(item: dict) -> None:
    raw = Path(item["path"]).read_bytes()
    if len(raw) != item["bytes"] or sha(raw) != item["sha256"]:
        raise ValueError(f"Recorded artifact changed: {item['path']}")


def collect(build: Path, native: Path, log: Path, output: Path) -> dict:
    built = json.loads((build/"build-report.json").read_text())
    suite = json.loads((native/"summary.json").read_text())
    for item in (built["package"], built["backup"], built["official_template"], built["codec"],
                 built["original_decoder"], *built["retained_sources"], *suite["retained_helpers"]):
        checked(item)
    package = Path(built["package"]["path"])
    entry = validate_scope(package.read_bytes())
    if built["package"] != suite["package"] or suite["passed"] != 7 or len(suite["controls"]) != 7:
        raise ValueError("Exact-package build/native suite mismatch")
    if built["camera_contacted"] or suite["camera_contacted"] or suite["physical_flash_written"]:
        raise ValueError("Expected offline-only controls")
    if (sha((build/"builder-source.py").read_bytes()) != built["builder_sha256"]
            or sha((native/"driver-source.py").read_bytes()) != suite["driver_sha256"]
            or built["builder_sha256"] != suite["driver_sha256"]):
        raise ValueError("Build/test source snapshots do not match")
    backup = BACKUP.read_bytes()
    if sha(backup) != BACKUP_SHA or sha(backup[DESTINATION:DESTINATION+LENGTH]) != SECONDARY_SHA:
        raise ValueError("Protected backup/installed payload differs")
    if (build/"host-decoded-program2.data").read_bytes() != backup[DESTINATION:DESTINATION+LENGTH]:
        raise ValueError("Original-decoder round trip changed")
    retained_backend = Path("work/gm5-emulator-nor-release-backend/gm5-mn103-sim")
    backend_sha = sha(retained_backend.read_bytes())
    controls = []
    for case in suite["controls"]:
        name, record = case["name"], case["execution"]
        directory = native/("startup_copy" if name == "installed_program2_startup_copy" else name)
        if json.loads((directory/"report.json").read_text()) != record:
            raise ValueError("Execution summary differs from its original report")
        if record["backend"]["sha256"] != backend_sha:
            raise ValueError("Native execution has no matching retained backend")
        for filename, field in (("scenario.json", "scenario_sha256"), ("trace.jsonl", "trace_sha256")):
            if sha((directory/filename).read_bytes()) != record[field]:
                raise ValueError("Native scenario/trace changed")
        if "nor_source" in record:
            if record["nor_source"]["sha256"] != BACKUP_SHA:
                raise ValueError("Unexpected native NOR source")
            actual = (directory/"virtual-nor.bin").read_bytes()
            if (sha(actual) != record["nor_output_sha256"]
                    or sha((directory/"nor-events.jsonl").read_bytes()) != record["nor_event_sha256"]):
                raise ValueError("Native NOR image/transcript changed")
            expected = bytearray(backup)
            if name != "minimal_native_install":
                expected[DESTINATION:DESTINATION+SECTOR] = b"\xff"*SECTOR
                if name == "minimal_native_power_cut":
                    expected[DESTINATION:DESTINATION+BUFFER] = backup[DESTINATION:DESTINATION+BUFFER]
            if actual != expected:
                raise ValueError("Whole-flash independent operation oracle differs")
        compact = {k: v for k, v in case.items() if k != "execution"}
        compact["run"] = {"directory": str(directory), "stop": record["result"]["stop"],
                          "native_return_d0": record["result"]["registers"][0],
                          "instructions": record["result"]["steps"],
                          "wall_seconds": record["execution_wall_seconds"],
                          "backend_sha256": backend_sha,
                          "scenario_sha256": record["scenario_sha256"],
                          "trace_sha256": record["trace_sha256"]}
        if "nor_source" in record:
            compact["run"].update(nor=record["result"]["nor"], nor_output_sha256=record["nor_output_sha256"],
                                  nor_event_sha256=record["nor_event_sha256"])
        controls.append(compact)
    test_text = log.read_text()
    if "Ran 68 tests" not in test_text or not test_text.rstrip().endswith("OK"):
        raise ValueError("Repository regression suite incomplete")
    if built["codec"]["sha256"] != sha((build/"codec").read_bytes()):
        raise ValueError("Retained encoder changed")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Prepared unchanged-program2 GM5 control; physical installation remains untested",
              "build": built, "component": entry, "native_controls_passed": len(controls), "controls": controls,
              "native_driver_sha256": suite["driver_sha256"], "retained_native_helpers": suite["retained_helpers"],
              "retained_backend": artifact(retained_backend),
              "repository_tests": {"passed": 68, "log": artifact(log)},
              "status": {"package_built": True, "all_official_ciphertexts_reproduced": True,
                         "original_decoder_roundtrip_matches_backup": True,
                         "installed_native_decoder_accepts_with_allowance": True,
                         "installed_native_decoder_rejects_default_policy": True,
                         "virtual_installation_leaves_whole_flash_identical": True,
                         "settings_and_calibration_payloads_excluded": True,
                         "camera_contacted": False, "sd_card_written": False, "physical_installation_tested": False},
              "success_criterion_limit": "Unchanged physical readback alone cannot distinguish successful identical reprogramming from rejection/no write. It is a preservation control, not final proof of a flashing route. A separately reviewed distinguishable modification or direct programming evidence is still required.",
              "limits": suite["limits"], "collector_sha256": sha(Path(__file__).read_bytes())}
    save_json(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--test-log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.build, args.native, args.test_log, args.out)
    print(f"Recorded {result['native_controls_passed']} exact-package native controls and 68 repository tests")


if __name__ == "__main__":
    main()
