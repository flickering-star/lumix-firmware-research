#!/usr/bin/env python3
"""Verify and publish the native RTOS extension and its current UI boundary."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from gm5_emulator import number, sha
from gm5_prompt_package import artifact
from gm5_reflash_control import save_json
from gm5_region_emulator import candidate, inputs
from gm5_rtos_emulator import BACKEND


OBJECTS = Path("work/gm5-native-rtos-objects-6")
CONTROLS = Path("work/gm5-native-rtos-controls-2")
INSTALL = Path("work/gm5-native-rtos-region-install-2")
UI = Path("work/gm5-ui-startup-with-native-rtos-3")
BOUNDARY = Path("work/gm5-native-language-full-flow-6")
DIFFERENTIAL = Path("work/gm5-region-memory-observation-rtos-aliases-1")


def checked(directory: Path, record: dict | None = None) -> dict:
    actual = json.loads((directory/"report.json").read_text())
    if record is not None and actual != record:
        raise ValueError("Native execution receipt changed")
    record = actual
    for filename, key in (("scenario.json", "scenario_sha256"), ("trace.jsonl", "trace_sha256")):
        if sha((directory/filename).read_bytes()) != record[key]:
            raise ValueError("Native scenario/trace differs from its receipt")
    if sha(Path(record["backend"]["path"]).read_bytes()) != record["backend"]["sha256"]:
        raise ValueError("Native backend differs from recorded executable")
    for image in record["images"]:
        if sha(Path(image["path"]).read_bytes()) != image["sha256"]:
            raise ValueError("Native source/snapshot image changed")
    if "nor_source" in record:
        if sha(Path(record["nor_source"]["path"]).read_bytes()) != record["nor_source"]["sha256"]:
            raise ValueError("Native source NOR changed")
        for filename, key in (("virtual-nor.bin", "nor_output_sha256"), ("nor-events.jsonl", "nor_event_sha256")):
            if sha((directory/filename).read_bytes()) != record[key]:
                raise ValueError("Native NOR output/transcript changed")
    stdout_results = [json.loads(line) for line in (directory/"stdout.txt").read_text().splitlines()
                      if line.startswith('{"event":"result",')]
    if stdout_results != [record["result"]]:
        raise ValueError("Native stdout does not match its retained result")
    spec = json.loads((directory/"scenario.json").read_text())
    if record["result"]["services"] is not None or "single_thread_sync" in spec:
        raise ValueError("Native RTOS evidence unexpectedly includes the return-stub service model")
    if any(number(item["address"]) in (0x7BE0826E, 0x7BE0629D) for item in spec["memory"]):
        raise ValueError("Native RTOS synchronization instruction bytes were replaced")
    return {"directory": str(directory), "result": record["result"],
            "backend_sha256": record["backend"]["sha256"],
            "scenario_sha256": record["scenario_sha256"], "trace_sha256": record["trace_sha256"],
            "output_dumps": [artifact(directory/item["name"]) for item in spec.get("dumps", [])],
            "assumptions": record["assumptions"]}


def group(directory: Path, field: str, count: int) -> tuple[dict, list[dict]]:
    report = json.loads((directory/"summary.json").read_text())
    if report["passed"] != count or len(report[field]) != count:
        raise ValueError("Native control group is incomplete")
    if sha((directory/"driver-source.py").read_bytes()) != report["driver_sha256"]:
        raise ValueError("Native group driver snapshot changed")
    return report, [dict(name=item["name"], execution=checked(directory/item["name"], item["execution"]))
                    for item in report[field]]


def collect(output: Path, release: Path) -> dict:
    main, _, _ = inputs(); wanted = candidate(main)
    receipt_path = Path("work/toolchain/gdb-mn10300-build/gm5-emulator-build-rtos_aliases.json")
    receipt = json.loads(receipt_path.read_text())
    if sha(BACKEND.read_bytes()) != receipt["executable"]["sha256"]:
        raise ValueError("RAM-alias backend differs from build receipt")
    old = json.loads(Path("work/toolchain/gdb-mn10300-build/gm5-emulator-build-language_watch.json").read_text())
    for key in ("original_generated_engine", "instrumented_engine_copy"):
        if receipt[key]["sha256"] != old[key]["sha256"]:
            raise ValueError("RAM alias extension changed the CPU engine")
    if [item["sha256"] for item in receipt["gnu_libraries"]] != [item["sha256"] for item in old["gnu_libraries"]]:
        raise ValueError("RAM alias extension changed linked GNU libraries")
    objects = json.loads((OBJECTS/"summary.json").read_text())
    if not objects["completed_objects"] or objects["peer_handshake_executed"] or objects["scheduler_started"]:
        raise ValueError("Bounded RTOS initialization scope differs")
    stage_directories = {"context": "context_prefix", "owners": "lock_owners",
                         "peer_context": "inactive_peer_context", "peer_owners": "inactive_peer_lock_owners",
                         "objects": "kernel_objects"}
    stages = [dict(stage=name, execution=checked(OBJECTS/stage_directories[name], record))
              for name, record in objects["executions"].items()]
    api, api_cases = group(CONTROLS, "cases", 13)
    installation, install_cases = group(INSTALL, "cases", 3)
    if installation["candidate_main_sha256"] != sha(wanted) or installation["rtos_return_stubs_used"]:
        raise ValueError("Native programming result uses another region candidate or RTOS stubs")
    success = INSTALL/"native_rtos_region_install/virtual-nor.bin"
    if success.read_bytes()[:len(wanted)] != wanted:
        raise ValueError("Programmed main differs from exact region candidate")
    ui = checked(UI)
    if ui["result"]["stop"] != "ui_startup_returned" or int(ui["result"]["registers"][8], 0) != 0x700F0000:
        raise ValueError("Complete UI-startup wrapper did not return with its stack restored")
    boundary = checked(BOUNDARY/"native_parent_menu_entry")
    error = (BOUNDARY/"native_parent_menu_entry/stderr.txt").read_text()
    match = re.search(r"(\d+) byte (read|write) to unmapped address (0x[0-9a-f]+) at (0x[0-9a-f]+)", error)
    if not match or match.groups() != ("2", "write", "0x9c013004", "0x7bc7a63f"):
        raise ValueError("Current UI boundary differs from the reviewed notification-register write")
    fault = dict(zip(("bytes", "operation", "address", "instruction_pc"), match.groups()))
    differential = json.loads((DIFFERENTIAL/"summary.json").read_text())
    if differential["passed"] != 2 or any(not item["legacy_and_new_backend_native_states_identical"]
                                         for item in differential["controls"]):
        raise ValueError("Optional backend changed legacy native language execution")
    log = Path("work/gm5-native-rtos-tests.log")
    if "Ran 88 tests" not in log.read_text() or not log.read_text().rstrip().endswith("OK"):
        raise ValueError("Repository regression suite is incomplete")
    release.mkdir(exist_ok=False); release.chmod(0o700)
    copied = []
    source_pins = {Path(item["path"]).name: item["sha256"] for item in
                   [receipt["harness_source"], receipt["build_driver"]]+receipt["execution_hooks"]+receipt["device_sources"]}
    source_pins["gm5_emulator.py"] = next(iter(objects["executions"].values()))["driver_sha256"]
    historical = Path("work/gm5-native-rtos-release-2")
    for source, name in [(BACKEND, "gm5-mn103-sim"), (receipt_path, "build.json")]+[
            (path, path.name) for path in Path("tools/mn103_simulator").iterdir() if path.is_file()]+[
            (Path("tools")/name, name) for name in ("gm5_emulator.py", "gm5_rtos_emulator.py",
                "gm5_native_rtos_controls.py", "gm5_native_rtos_install.py", "gm5_ui_emulator.py",
                "gm5_native_language_flow.py", "gm5_rtos_evidence.py")]:
        target = release/name
        if name in source_pins and sha(source.read_bytes()) != source_pins[name]:
            source = historical/name
            if not source.is_file() or sha(source.read_bytes()) != source_pins[name]:
                raise ValueError("Historical RTOS source is missing or differs from its execution/build receipt")
        shutil.copyfile(source, target); copied.append(artifact(target))
    (release/"gm5-mn103-sim").chmod(0o500)
    result = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Native RTOS synchronization, coherent RAM views, complete UI startup and virtual region installation",
              "build": receipt, "retained_release": copied,
              "cpu_engine_and_gnu_libraries_unchanged": True,
              "native_initialization": stages, "native_api_controls": api_cases,
              "native_install_controls": install_cases, "native_ui_startup": ui,
              "candidate_main_sha256": sha(wanted), "package": installation["package"],
              "task_fixture": api["task_fixture"], "repository_tests": {"passed": 88, "log": artifact(log)},
              "ram_alias_controls": "Four repository tests cover both directions, fast/step equality, observations and independent frontend/backend guards.",
              "callback_abi_controls": "Three repository tests cover CALLS/self-allocated frames, CALL/automatic frames and a double-frame failure control.",
              "legacy_language_differential": artifact(DIFFERENTIAL/"summary.json"),
              "unresolved_ui_boundary": {"execution": boundary, "actual_access": fault,
                                         "interpretation": "Native service notification follows mask registration; software-interrupt delivery remains unmodeled."},
              "complete_language_confirmation_flow_executed": False,
              "camera_contacted": False, "physical_region_patch_installed": False,
              "limits": api["limits"]+["The full RTOS entry still requires a peer handshake; the initializer uses bounded native subsequences.",
                                        "Two existing board/shutdown skips remain in the programming job; final restart is not modeled.",
                                        "No display, sensor, USB, SD-controller, real interrupts or concurrent task execution is modeled."],
              "collector_sha256": sha(Path(__file__).read_bytes())}
    save_json(output, result)
    print("Verified native RTOS extension:13API controls,3whole-programming controls,88repository tests; full UI confirmation remains bounded", flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--release", type=Path, default=Path("work/gm5-native-rtos-release-2"))
    args = parser.parse_args()
    collect(args.out, args.release)


if __name__ == "__main__":
    main()
