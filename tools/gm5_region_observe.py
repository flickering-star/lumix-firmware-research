#!/usr/bin/env python3
"""Locate actual native RAM stores responsible for Japanese language resets."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from gm5_emulator import DEFAULT_BACKEND, run_scenario, sha
from gm5_reflash_control import save_json
from gm5_region_emulator import inputs, scenario

BACKEND = Path("work/toolchain/gdb-mn10300-build/gm5-mn103-sim-language_watch")


def observe(output: Path, backend: Path) -> dict:
    main, _, flash = inputs()
    output.mkdir(parents=True, exist_ok=False);output.chmod(0o700)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    controls = []
    for patched in (False, True):
        name = "candidate_language_stores" if patched else "stock_language_stores"
        spec = scenario(name, main, flash, region=0x100, language=1, patched_rom=patched)
        spec["memory_observations"] = [{"label": "saved_language", "address": 0x7BFB01B9, "size": 1},
                                       {"label": "ui_language", "address": 0x701AF239, "size": 1},
                                       {"label": "language_item_visibility", "address": 0x70A0E912, "size": 1}]
        directory = output/name
        record = run_scenario(spec, backend, directory)
        if record["result"]["stop"] != "returned":
            raise ValueError("Observed native language run failed")
        changes = [json.loads(line) for line in (directory/"trace.jsonl").read_text().splitlines()
                   if '"event":"memory_change"' in line]
        by_label = {item["label"]: item for item in changes}
        if patched:
            if set(by_label) != {"ui_language"} or by_label["ui_language"]["after"] != "01":
                raise ValueError("Candidate changed the saved English value or hid the Language menu")
        else:
            expected = {"saved_language": ("0x40211fe0", "01", "00"),
                        "ui_language": ("0x40211fe6", "a5", "00"),
                        "language_item_visibility": ("0x40127221", "04", "00")}
            if set(by_label) != set(expected): raise ValueError("Stock native write trace lacks an expected language/visibility store")
            for label, wanted in expected.items():
                actual = by_label[label]
                if (actual["instruction_pc"], actual["before"], actual["after"]) != wanted:
                    raise ValueError("Stock language reset store differs from native analysis")
        # A second run without observation must have identical state/outputs.
        plain_spec = dict(spec);plain_spec.pop("memory_observations")
        plain = run_scenario(plain_spec, backend, output/(name+"_unobserved"))
        if record["result"] != plain["result"]:
            raise ValueError("RAM observations changed CPU execution")
        for filename in ("settings.data", "ui-language.data", "menu.data", "setup-menu.data"):
            if (directory/filename).read_bytes() != (output/(name+"_unobserved")/filename).read_bytes():
                raise ValueError("RAM observations changed a native output")
        legacy_dir = output/(name+"_legacy_unobserved")
        legacy = run_scenario(plain_spec, DEFAULT_BACKEND, legacy_dir)
        if legacy["result"] != plain["result"] or (legacy_dir/"trace.jsonl").read_bytes() != (
                output/(name+"_unobserved")/"trace.jsonl").read_bytes():
            raise ValueError("Optional observation backend changed unobserved native execution")
        for filename in ("settings.data", "ui-language.data", "menu.data", "setup-menu.data"):
            if (directory/filename).read_bytes() != (legacy_dir/filename).read_bytes():
                raise ValueError("Optional observation backend changed native output versus the retained backend")
        controls.append({"name": name, "patched": patched, "changes": changes,
                         "execution": record, "unobserved_execution": plain,
                         "legacy_execution": legacy,
                         "observed_and_unobserved_states_identical": True,
                         "legacy_and_new_backend_native_states_identical": True})
    result = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Exact native stores for region language reset and Language-item hiding",
              "controls": controls, "passed": len(controls), "camera_contacted": False,
              "driver_sha256": sha(Path(__file__).read_bytes()),
              "observer_limit": "Observes value changes between instructions; same-value stores are intentionally not events."}
    save_json(output/"summary.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", type=Path, default=BACKEND)
    args = parser.parse_args()
    observe(args.out, args.backend)
    print("Verified exact stock reset/hide stores and candidate preservation with non-mutating RAM observations")


if __name__ == "__main__":
    main()
