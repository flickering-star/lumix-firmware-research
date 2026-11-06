#!/usr/bin/env python3
"""Verify exact region package, native UI/save path and optional RAM tracing."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from gm5_emulator import sha
from gm5_prompt_package import artifact
from gm5_reflash_control import save_json
from gm5_region_emulator import candidate, inputs, patches
from gm5_region_package import validate
from gm5_region_verify import checked_run

BUILD = Path("work/gm5-region-package-2")
NATIVE = Path("work/gm5-region-package-native-2")
PERSISTENCE = Path("work/gm5-region-encoded-navigation-persistence-1")
OBSERVATIONS = Path("work/gm5-region-memory-observation-2")
WATCH_BACKEND = Path("work/toolchain/gdb-mn10300-build/gm5-mn103-sim-language_watch")


def collect(output: Path) -> dict:
    main, _, _ = inputs(); wanted = candidate(main)
    built = json.loads((BUILD/"build-report.json").read_text())
    native = json.loads((NATIVE/"summary.json").read_text())
    package = Path(built["package"]["path"])
    if sha(package.read_bytes()) != built["package"]["sha256"] or native["package"] != built["package"]:
        raise ValueError("Exact region package build/native hashes differ")
    validate(package.read_bytes(), wanted)
    if native["passed"] != 6 or len(native["controls"]) != 6:
        raise ValueError("Exact encrypted package controls are incomplete")
    if (sha((BUILD/"builder-source.py").read_bytes()) != built["builder_sha256"]
            or sha((NATIVE/"driver-source.py").read_bytes()) != native["driver_sha256"]):
        raise ValueError("Region package source snapshots changed")
    for control in native["controls"]:
        checked_run(NATIVE/control["name"], control["execution"])
    persistence = json.loads((PERSISTENCE/"summary.json").read_text())
    if (not persistence["language_selected_through_native_menu_navigation"]
            or persistence["final_settings_language"] != 1 or persistence["final_ui_language"] != 1
            or sha((PERSISTENCE/"driver-source.py").read_bytes()) != persistence["driver_sha256"]):
        raise ValueError("Exact encoded/programmed menu/save/reload proof is incomplete")
    if Path(persistence["programmed_source"]).read_bytes() != (NATIVE/"region_native_install/virtual-nor.bin").read_bytes():
        raise ValueError("Persistence did not use the exact programmed candidate")
    for record in persistence["executions"].values():
        checked_run(PERSISTENCE/record["name"], record)
    navigation = json.loads((PERSISTENCE/"native_menu_navigation/navigation.json").read_text())
    if len(navigation["selected_language_ids"]) != 24 or navigation["pending_language_directly_written_by_fixture"]:
        raise ValueError("Native language navigation was bypassed")
    observations = json.loads((OBSERVATIONS/"summary.json").read_text())
    if observations["passed"] != 2 or sha((OBSERVATIONS/"driver-source.py").read_bytes()) != observations["driver_sha256"]:
        raise ValueError("Native RAM observation proof changed")
    receipt = json.loads(Path("work/toolchain/gdb-mn10300-build/gm5-emulator-build-language_watch.json").read_text())
    if sha(WATCH_BACKEND.read_bytes()) != receipt["executable"]["sha256"]:
        raise ValueError("RAM observation backend differs from build receipt")
    retained = Path("work/gm5-emulator-language-watch-release")
    retained.mkdir(exist_ok=True)
    # Validate this historical release against its own build/run hashes.
    # Later optional emulator features may change the current checkout; they
    # must never replace the source that produced an earlier native proof.
    frontend_hashes = {control["execution"]["driver_sha256"] for control in observations["controls"]}
    if len(frontend_hashes) != 1:
        raise ValueError("Observation runs used inconsistent frontends")
    receipt_path = Path("work/toolchain/gdb-mn10300-build/gm5-emulator-build-language_watch.json")
    retained_inputs = [(WATCH_BACKEND, "gm5-mn103-sim", receipt["executable"]["sha256"]),
                       (receipt_path, "gm5-emulator-build.json", sha(receipt_path.read_bytes())),
                       (Path("tools/gm5_emulator.py"), "gm5_emulator.py", frontend_hashes.pop())]
    sources = [receipt["harness_source"], receipt["build_driver"]]+receipt["execution_hooks"]+receipt["device_sources"]
    sources += [item["extension"] for item in receipt["build_recipe_patches"] if "extension" in item]
    retained_inputs += [(Path(item["path"]), Path(item["path"]).name, item["sha256"]) for item in sources]
    for source, name, expected in retained_inputs:
        target = retained/name
        if target.exists():
            if sha(target.read_bytes()) != expected:
                raise ValueError("Retained observation release differs from its recorded build/run")
        else:
            if sha(source.read_bytes()) != expected:
                raise ValueError("Historical observation source is missing and the checkout has advanced")
            shutil.copyfile(source, target)
    (retained/"gm5-mn103-sim").chmod(0o500)
    for control in observations["controls"]:
        for suffix, key in (("", "execution"), ("_unobserved", "unobserved_execution"),
                            ("_legacy_unobserved", "legacy_execution")):
            record = control[key];directory = OBSERVATIONS/(control["name"]+suffix)
            if json.loads((directory/"report.json").read_text()) != record:
                raise ValueError("Observed native run receipt changed")
            for filename, field in (("scenario.json", "scenario_sha256"), ("trace.jsonl", "trace_sha256")):
                if sha((directory/filename).read_bytes()) != record[field]:
                    raise ValueError("Observed native scenario or trace changed")
    log = Path("work/gm5-region-visibility-final-tests.log")
    text = log.read_text()
    if "Ran 81 tests" not in text or not text.rstrip().endswith("OK"):
        raise ValueError("Final repository regression suite is not complete")
    result = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Three-byte Japanese language unlock: exact package and native menu/save/reload readiness",
              "package": built["package"], "candidate_main_sha256": sha(wanted), "patches": patches(main),
              "region_matrix_evidence": artifact(Path("evidence/gm5-region-language-lock-v2.json")),
              "native_region_controls": 1756, "exact_encoded_package_native_controls": native,
              "encoded_programmed_native_navigation_save_reload": persistence,
              "native_navigation": navigation, "native_memory_change_observations": observations,
              "observation_backend": artifact(retained/"gm5-mn103-sim"), "observation_build": receipt,
              "repository_tests": {"passed": 81, "log": artifact(log)},
              "current_physical_main_still_policy_zero_only": True,
              "camera_contacted": False, "sd_card_written_with_region_candidate": False,
              "physical_region_patch_installed": False,
              "physical_test_expectations": ["Language menu visible on Japanese region0x100 without changing region identity.",
                                             "Japanese remains the initial language when saved language0 is valid; select English through the normal menu.",
                                             "After normal off/on, English should remain and policy0 should still initialize without a USB write.",
                                             "Complete main readback must match5364cde77a78a40fce270bf1c24642a9fbd2e6d7d3501bb38d8b806548a48d67.",
                                             "The23-language list uses existing firmware resources; no claim that all26resource IDs are exposed."],
              "limits": persistence["limits"]+native["limits"],
              "collector_sha256": sha(Path(__file__).read_bytes())}
    save_json(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.out)
    print(f"Region candidate ready: {result['package']['sha256']};1756native region controls,81repository tests")


if __name__ == "__main__":
    main()
