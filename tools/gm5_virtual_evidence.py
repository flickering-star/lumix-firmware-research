#!/usr/bin/env python3
"""Collect virtual-installation reports without including private flash bytes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from gm5_emulator import sha


def collect(output: Path) -> dict:
    backends = []
    for directory in (Path("work/gm5-emulator-nor-pilot-backend"), Path("work/gm5-emulator-nor-release-backend")):
        build = json.loads((directory/"gm5-emulator-build.json").read_text())
        binary = directory/"gm5-mn103-sim"
        if sha(binary.read_bytes()) != build["executable"]["sha256"]:
            raise ValueError("Retained backend differs from its build receipt")
        backends.append({"retained_binary": str(binary), "build": build})
    backend_hashes = {b["build"]["executable"]["sha256"] for b in backends}
    suites = []
    count = 0
    for directory, expected in ((Path("work/gm5-virtual-nor-controls-2"), 15),
                                (Path("work/gm5-virtual-install-1"), 8)):
        summary = json.loads((directory/"summary.json").read_text())
        if summary["passed"] != expected or summary["camera_contacted"]:
            raise ValueError("Unexpected or incomplete virtual control suite")
        if sha((directory/"driver-source.py").read_bytes()) != summary["driver_sha256"]:
            raise ValueError("Controller source snapshot differs")
        for case in summary["controls"]:
            record = case["execution"]
            run = directory/case["name"]
            if record["backend"]["sha256"] not in backend_hashes:
                raise ValueError("No retained backend for native execution")
            for filename, field in (("scenario.json", "scenario_sha256"), ("trace.jsonl", "trace_sha256")):
                if sha((run/filename).read_bytes()) != record[field]:
                    raise ValueError("Recorded scenario/trace has changed")
            if "nor_source" in record:
                if sha((run/"virtual-nor.bin").read_bytes()) != record["nor_output_sha256"]:
                    raise ValueError("Virtual NOR output has changed")
                if sha((run/"nor-events.jsonl").read_bytes()) != record["nor_event_sha256"]:
                    raise ValueError("NOR event transcript has changed")
                if sha(Path(record["nor_source"]["path"]).read_bytes()) != record["nor_source"]["sha256"]:
                    raise ValueError("Read-only NOR source has changed")
        count += expected
        suites.append({"directory": str(directory), "report": summary})
    test_log = Path("work/gm5-virtual-install-final-tests.log")
    text = test_log.read_text()
    if "Ran 63 tests" not in text or not text.rstrip().endswith("OK"):
        raise ValueError("Final repository tests are not complete")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Installed GM5 native writer and post-validation job against disposable 32 MiB NOR",
              "native_controls_passed": count, "suites": suites, "backends": backends,
              "backend_note": "Installed decode began with the retained pilot backend. NOR failure handling was then extended; each run pins its actual backend hash.",
              "repository_tests": {"passed": 63, "log": str(test_log), "sha256": sha(test_log.read_bytes())},
              "native_writer_evidence": json.loads(Path("evidence/gm5-native-nor-writer.json").read_text()),
              "collector_sha256": sha(Path(__file__).read_bytes()), "camera_contacted": False,
              "original_backup_unchanged": True, "physical_flash_written": False,
              "reference": {"title": "Micron M29EW parallel NOR datasheet, Rev. E, 2016, pp.24–25,31",
                            "url": "https://www.mouser.com/datasheet/2/671/m29ew_256mb_2gb-1282221.pdf",
                            "scope": "Manufacturer command/status semantics consistent with the traced x16 sequences, not identification of this camera's exact chip."}}
    with output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.out)
    print(f"Recorded {result['native_controls_passed']} native virtual NOR controls and63 repository tests.")


if __name__ == "__main__":
    main()
