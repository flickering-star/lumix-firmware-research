#!/usr/bin/env python3
"""Collect native-emulator control reports and hashes without firmware bytes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from gm5_emulator import sha

SUITES = (
    ("updater", "work/gm5-emulator-updater-release", 16),
    ("initializers", "work/gm5-emulator-initializers-release", 3),
    ("sha256", "work/gm5-emulator-sha-final", 9),
    ("ecdsa", "work/gm5-emulator-signatures-release", 3),
    ("decoder", "work/gm5-emulator-full-decoder-final", 6),
    ("settings_merge", "work/gm5-emulator-settings-merge-final", 7),
)


def collect(output: Path) -> dict:
    build_path = Path("work/toolchain/gdb-mn10300-build/gm5-emulator-build.json")
    build = json.loads(build_path.read_text())
    executable = Path(build["executable"]["path"])
    if sha(executable.read_bytes()) != build["executable"]["sha256"]:
        raise ValueError("Native backend differs from recorded build")
    for field in ("harness_source", "build_driver"):
        if sha(Path(build[field]["path"]).read_bytes()) != build[field]["sha256"]:
            raise ValueError(f"Build source differs: {field}")
    suites = []
    driver_digest = sha(Path("tools/gm5_emulator.py").read_bytes())
    for name, directory, expected in SUITES:
        path = Path(directory)
        summary = json.loads((path/"summary.json").read_text())
        if summary["passed"] != expected or summary["camera_contacted"]:
            raise ValueError(f"Incomplete or unexpected native suite: {name}")
        records = []
        for run_path in sorted(path.glob("*/report.json")):
            record = json.loads(run_path.read_text())
            if record["backend"]["sha256"] != build["executable"]["sha256"] or record["driver_sha256"] != driver_digest:
                raise ValueError(f"Execution used different backend/driver: {run_path}")
            for filename, field in (("scenario.json", "scenario_sha256"), ("trace.jsonl", "trace_sha256")):
                if sha((run_path.parent/filename).read_bytes()) != record[field]:
                    raise ValueError(f"Execution artifact changed: {run_path.parent/filename}")
            records.append(record)
        if len(records) != expected:
            raise ValueError(f"Native execution report count differs: {name}")
        suites.append({"name": name, "summary": summary, "executions": records})
    log = Path("work/gm5-emulator-unittest-final.log")
    if "Ran 61 tests" not in log.read_text() or not log.read_text().rstrip().endswith("OK"):
        raise ValueError("Expected completed repository test log")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Offline GM5 native CPU milestone; no complete camera hardware model",
              "native_controls_passed": sum(item[2] for item in SUITES), "suites": suites,
              "build": build, "driver_sha256": driver_digest,
              "collector_sha256": sha(Path(__file__).read_bytes()),
              "repository_tests": {"passed": 61, "log": str(log), "log_sha256": sha(log.read_bytes()),
                                   "command": "python3 -m unittest discover -s tests -v"},
              "camera_contacted": False, "physical_flash_written": False,
              "limits": ["Preset routines use official decoded GM5 programs, not yet the complete installed Japanese build.",
                         "No full boot, ASIC/display/sensor/USB/SD device model, or NOR command model.",
                         "No installation job or physical flash acceptance demonstrated by these CPU controls.",
                         "Signed library validation executes native SHA/ECDSA; unsigned component hashes are independently checked afterward by the host."]}
    with output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.out)
    print(f"Recorded {report['native_controls_passed']} native controls and 61 repository tests: {args.out}")


if __name__ == "__main__":
    main()
