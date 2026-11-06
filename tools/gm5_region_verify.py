#!/usr/bin/env python3
"""Publish native region/language and virtual persistence evidence; no camera I/O."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from gh2_debug_verify import checked_disassembly
from gm5_emulator import sha
from gm5_prompt_package import artifact
from gm5_reflash_control import save_json
from gm5_region_emulator import MAIN, MAIN_SHA, INTERNATIONAL_LIST, candidate, inputs, patches, table

REGIONS = (
    ("native_boot_language_calls", 0x40211A38, 0x40211A4D),
    ("language_normalizer_region_dispatch", 0x40211EC6, 0x40211F1A),
    ("language_normalizer_store", 0x40211FB3, 0x40211FFD),
    ("language_menu_region_dispatch", 0x400A8427, 0x400A847B),
    ("language_menu_default_and_copy", 0x400A858F, 0x400A85A5),
    ("japanese_setup_language_hider", 0x400AA012, 0x400AA033),
    ("setup_item_dispatch_bounds", 0x40109F0E, 0x40109F3A),
    ("setup_language_entry", 0x4010A126, 0x4010A13D),
    ("language_list_membership", 0x40126FCE, 0x40126FFE),
    ("native_selection_store_and_flag", 0x400EA1EA, 0x400EA204),
    ("settings_load_and_bank_selection", 0x401E3051, 0x401E315F),
    ("normal_settings_save", 0x401E3382, 0x401E34C0),
)


def checked_run(directory: Path, record: dict) -> dict:
    if json.loads((directory/"report.json").read_text()) != record:
        raise ValueError("Native run receipt differs")
    for filename, field in (("scenario.json", "scenario_sha256"), ("trace.jsonl", "trace_sha256")):
        if sha((directory/filename).read_bytes()) != record[field]:
            raise ValueError("Native run scenario/trace changed")
    backend = Path("work/gm5-emulator-nor-release-backend/gm5-mn103-sim")
    if sha(backend.read_bytes()) != record["backend"]["sha256"]:
        raise ValueError("Native run has no matching retained backend")
    if "nor_source" in record:
        if (sha((directory/"virtual-nor.bin").read_bytes()) != record["nor_output_sha256"]
                or sha((directory/"nor-events.jsonl").read_bytes()) != record["nor_event_sha256"]):
            raise ValueError("Native NOR output or event transcript changed")
    return {"directory": str(directory), "stop": record["result"]["stop"],
            "instructions": record["result"]["steps"], "backend_sha256": record["backend"]["sha256"],
            "scenario_sha256": record["scenario_sha256"], "trace_sha256": record["trace_sha256"]}


def collect(matrix: Path, stock: Path, unlocked: Path, decoder: Path, output: Path) -> dict:
    main, _, _ = inputs()
    changed = candidate(main)
    data = json.loads((matrix/"summary.json").read_text())
    if data["passed"] != 1756 or not data["exhaustive_regions"]:
        raise ValueError("Full native region controls are not complete")
    if sha((matrix/"driver-source.py").read_bytes()) != data["driver_sha256"]:
        raise ValueError("Region controller source snapshot changed")
    checks = []
    for case in data["controls"]:
        checks.append(dict({k: v for k, v in case.items() if k != "execution"},
                           run=checked_run(matrix/case["name"], case["execution"])))
    persistence = []
    for directory, want, patch in ((stock, 0, False), (unlocked, 1, True)):
        result = json.loads((directory/"summary.json").read_text())
        if (result["patch"] != patch or result["final_settings_language"] != want
                or result["final_ui_language"] != want
                or sha((directory/"driver-source.py").read_bytes()) != result["driver_sha256"]):
            raise ValueError("Native settings persistence result/source differs")
        records = []
        for stage, record in result["executions"].items():
            # Directory names are retained in the scenario's name, independent
            # of dictionary key spelling and source-image location.
            records.append(dict(stage=stage, run=checked_run(directory/record["name"], record)))
        persistence.append({"patched": patch, "final_language": want,
                            "settings_save_changed_bytes": result["settings_save_changed_bytes"], "executions": records})
    before_save = (stock/"native_save/virtual-nor.bin").read_bytes()
    after_save = (unlocked/"native_save/virtual-nor.bin").read_bytes()
    save_diff = [i for i, (a, b) in enumerate(zip(before_save, after_save)) if a != b]
    if save_diff != sorted(p["offset"] for p in patches(main)):
        raise ValueError("Stock/patched save results differ beyond the three language bytes")
    regions = []
    for name, first, last in REGIONS:
        disassembly, count = checked_disassembly(MAIN, main, decoder, 0x40000000, first, last)
        regions.append({"name": name, "start": hex(first), "end_exclusive": hex(last),
                        "instruction_count": count, "native_sha256": sha(main[first-0x40000000:last-0x40000000]),
                        "disassembly": disassembly, "raw_annotations_match_source": True})
    result = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Installed GM5 region-language lock and native virtual settings save/reload",
              "main": artifact(MAIN), "original_policy_zero_main_sha256": MAIN_SHA,
              "candidate_main_sha256": sha(changed), "patches": patches(main),
              "regions": regions, "matrix_controls_passed": len(checks), "matrix_controls": checks,
              "region_inputs": "All0x0000..0x0121 plus0xffff; Japanese8language cases, others3cases; stock and candidate",
              "persistence": persistence, "persistence_stock_vs_patched_nor_differences": [hex(i) for i in save_diff],
              "candidate_language_ids": [r["id"] for r in table(main, INTERNATIONAL_LIST)],
              "supported_findings": ["Region0x100 selects a Japanese-only language table at startup and during menu construction.",
                                     "The existing native settings save can persist English, but stock native startup normalizes it back to Japanese.",
                                     "Redirecting the two region0x100 language dispatch entries preserves English through native save and fresh reload.",
                                     "The setup-item dispatcher maps ID143 to language-menu entry; Japanese-specific code separately hides that item.",
                                     "A third byte skips only that Japanese hide operation; native tests verify the Language item retains visible state4.",
                                     "The candidate menu uses23existing choices, including English1 and Japanese0; it does not expose all26resource IDs.",
                                     "All other tested region settings and language behavior remain unchanged; persistent policy0 is retained."],
              "camera_contacted": False, "physical_region_patch_installed": False,
              "limits": ["Only bounded native startup/selection/save functions execute; full display/scheduler/hardware boot is not modeled.",
                         "Virtual RTOS/cache/NOR timing assumptions remain; physical language persistence is not established yet.",
                         "The scope is Japanese language availability, not changing regional video standards, factory identity or calibration."],
              "collector_sha256": sha(Path(__file__).read_bytes())}
    save_json(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--unlocked", type=Path, required=True)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.matrix, args.stock, args.unlocked, args.decoder, args.out)
    print(f"Verified {result['matrix_controls_passed']} native region controls and native stock/patched save/reload")


if __name__ == "__main__":
    main()
