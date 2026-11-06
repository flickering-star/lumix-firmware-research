#!/usr/bin/env python3
"""Run the connected GM5 build's native initializer loops from a verified backup.

All execution and the one-byte policy patch are virtual. This does not produce
an update package, contact the camera or model its complete boot sequence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gm5_backup_analyze import analyze
from gm5_emulator import DEFAULT_BACKEND, base_scenario, put, run_scenario, sha


def installed_tests(capture: Path, backend: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    extraction = analyze(capture, output/"private-inputs")
    images = [{"path": item["path"], "address": item["linked_address"], "sha256": item["sha256"]}
              for item in extraction["components"]]
    main = Path(images[0]["path"]).read_bytes()
    controls = []
    for name, entry, end, source, source_end, destination, patched in (
        ("installed_key_initializer", 0x4000018F, 0x400001AD, 0x40643B7C, 0x4064B5B8, 0x70000000, False),
        ("installed_policy_stock", 0x40003000, 0x4000301E, 0x4064B5B8, 0x406DD76C, 0x70A01E6C, False),
        ("installed_policy_virtual_patch", 0x40003000, 0x4000301E, 0x4064B5B8, 0x406DD76C, 0x70A01E6C, True),
    ):
        spec = base_scenario(name)
        spec["images"] = images
        spec["registers"]["pc"] = entry
        spec["stops"] = {"copy_finished": end}
        spec["budget"] = 2000000
        spec["trace_every"] = 1000
        spec["assumptions"] = ["Installed native copy loops only; hardware initialization prefix is not executed.",
                               "Actual Japanese build's second initializer ends four bytes later than the official image."]
        expected = bytearray(main[source-0x40000000:source_end-0x40000000])
        if patched:
            if expected[0x406B1BDC-source] != 1:
                raise ValueError("Installed ROM policy byte is not the expected one")
            spec["memory"] = [put(0x406B1BDC, b"\0")]
            expected[0x406B1BDC-source] = 0
        spec["dumps"] = [{"name": "initialized.data", "address": destination, "size": len(expected)}]
        record = run_scenario(spec, backend, output/name)
        actual = (output/name/"initialized.data").read_bytes()
        if record["result"]["stop"] != "copy_finished" or actual != expected:
            raise ValueError(f"Installed native initializer differs: {name}: {record['result']}")
        item = {"name": name, "source": hex(source), "end_exclusive": hex(source_end),
                "destination": hex(destination), "bytes": len(actual), "sha256": sha(actual),
                "entire_destination_matches_expected_rom": True, "virtual_patch": patched,
                "execution": record}
        if name == "installed_key_initializer":
            if actual[0x7950:0x7960].hex() != "f630c6cfad87f78031327ba55193fa4c":
                raise ValueError("Installed native key copy does not match recovered GM5 key")
            item["recovered_key_matches"] = True
        else:
            item["ram_policy_value"] = actual[0x70A68490-destination]
        controls.append(item)
    stock = (output/"installed_policy_stock/initialized.data").read_bytes()
    changed = (output/"installed_policy_virtual_patch/initialized.data").read_bytes()
    differences = [hex(0x70A01E6C+i) for i, (a, b) in enumerate(zip(stock, changed)) if a != b]
    if differences != ["0x70a68490"]:
        raise ValueError("Virtual patch changed other installed initializer bytes")
    report = {"schema": 1, "scope": "Native initializer tests using this GM5's complete packet-verified installed programs",
              "passed": len(controls), "controls": controls, "backup_extraction": extraction,
              "virtual_patch_ram_differences": differences, "source_sha256": sha(Path(__file__).read_bytes()),
              "camera_contacted": False, "physical_firmware_modified": False,
              "limits": ["Does not execute full boot, hardware setup, installed update decoder or NOR programming.",
                         "A one-byte virtual ROM patch proves initializer behavior, not safe installation or recovery."]}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--backend", type=Path, default=DEFAULT_BACKEND)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = installed_tests(args.capture, args.backend, args.out)
    print(f"Passed {report['passed']} installed-build native initializer controls; evidence {args.out}")


if __name__ == "__main__":
    main()
