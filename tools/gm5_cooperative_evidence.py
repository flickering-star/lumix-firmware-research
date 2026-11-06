#!/usr/bin/env python3
"""Verify and retain the cooperative-task and ARM-routing extension evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import struct

from gm5_arm_emulator import ARM_IMAGE, ARM_SHA
from gm5_emulator import number, sha
from gm5_prompt_package import artifact
from gm5_reflash_control import save_json
from gm5_region_emulator import SECONDARY
from gm5_rtos_evidence import checked
from gm5_task_emulator import inspect_switch, snapshot_bytes


FLOW = Path("work/gm5-native-language-ready-tasks-2")
ROUTING = Path("work/gm5-arm-routing-controls-1")
RECEIPT = Path("work/toolchain/gdb-mn10300-build/gm5-emulator-build-cooperative_stops.json")
FROZEN_BACKEND = Path("work/gm5-cooperative-stops-release-1")


def checked_arm(directory: Path, expected: dict) -> dict:
    report = json.loads((directory/"report.json").read_text())
    if report != expected or report["camera_contacted"] or report["complete_camera_emulation"]:
        raise ValueError("ARM execution receipt or scope differs")
    for filename, key in (("scenario.json", "scenario_sha256"), ("trace.jsonl", "trace_sha256"),
                          ("driver-source.py", "driver_sha256")):
        if sha((directory/filename).read_bytes()) != report[key]:
            raise ValueError("ARM execution source/scenario/trace changed")
    for item in report["images"]:
        if sha(Path(item["path"]).read_bytes()) != item["sha256"]:
            raise ValueError("ARM input image changed")
    for package in report["dependencies"]:
        for item in package["files"]:
            if sha(Path(item["path"]).read_bytes()) != item["sha256"]:
                raise ValueError("ARM backend component differs from the executed dependency")
    for item in report["dumps"]:
        if sha((directory/item["name"]).read_bytes()) != item["sha256"]:
            raise ValueError("ARM output dump changed")
    return {"directory": str(directory), "result": report["result"],
            "scenario_sha256": report["scenario_sha256"], "trace_sha256": report["trace_sha256"],
            "driver_sha256": report["driver_sha256"], "cpu_model_fixture": report["cpu_model_fixture"]}


def native_stage(directory: Path, record: dict) -> dict:
    summary = checked(directory, record)
    if "control_event_sha256" in record:
        if sha((directory/"control-events.jsonl").read_bytes()) != record["control_event_sha256"]:
            raise ValueError("Native command-controller transcript changed")
    return summary


def collect(output: Path, release: Path, tests: Path) -> dict:
    if output.exists() or release.exists(): raise ValueError("Evidence/release output already exists")
    test_text = tests.read_text()
    if "Ran 105 tests" not in test_text or not test_text.rstrip().endswith("OK") or "skipped" in test_text:
        raise ValueError("Requires the complete105-test repository run with no skips")
    receipt = json.loads(RECEIPT.read_text())
    old = json.loads(Path("work/toolchain/gdb-mn10300-build/gm5-emulator-build-rtos_aliases.json").read_text())
    for key in ("original_generated_engine", "instrumented_engine_copy"):
        if receipt[key]["sha256"] != old[key]["sha256"]:
            raise ValueError("Cooperative-stop extension changed CPU instruction semantics")
    if [i["sha256"] for i in receipt["gnu_libraries"]] != [i["sha256"] for i in old["gnu_libraries"]]:
        raise ValueError("Cooperative-stop extension changed the linked GNU CPU libraries")
    if sha(Path(receipt["executable"]["path"]).read_bytes()) != receipt["executable"]["sha256"]:
        raise ValueError("Cooperative backend binary changed")
    parent = FLOW/"native_parent_menu_entry"
    report = json.loads((parent/"notification-report.json").read_text())
    if sha((parent/"driver-source.py").read_bytes()) != report["driver_sha256"]:
        raise ValueError("Notification adapter source changed")
    if report["delivered_interrupts"] or not report["native_ready_tasks_enabled"]:
        raise ValueError("Task experiment supplied an interrupt or did not enable native task switches")
    stages = [native_stage(Path(stage["directory"]), stage["execution"]) for stage in report["native_stages"]]
    if sum(stage["result"]["steps"] for stage in stages) != report["native_instructions"] or report["native_instructions"] != 60342:
        raise ValueError("Task-experiment instruction counts differ")
    if [(s["previous_task"]["id"], s["next_task"]["id"]) for s in report["task_switches"]] != [(7,60),(60,61)]:
        raise ValueError("Native worker-task sequence differs")
    suspended, secondary = {}, SECONDARY.read_bytes()
    for event in report["task_switches"]:
        index = next(i for i, s in enumerate(stages) if s["directory"] == event["directory"])
        previous = stages[index-1]
        rebuilt = inspect_switch(Path(previous["directory"]), previous["result"], secondary, suspended)
        if any(event[key] != value for key, value in rebuilt.items()):
            raise ValueError("Task-event description differs from actual stopped state")
        directory = Path(event["directory"])
        if sha((directory/"task-driver-source.py").read_bytes()) != event["task_driver_sha256"]:
            raise ValueError("Native task adapter source changed")
        actual = stages[index]["result"]
        if actual["stop"] != "native_stack_restored" or actual["steps"] != 3:
            raise ValueError("Native stack helper did not complete its three actual instructions")
        registers = [number(value) for value in actual["registers"]]
        if (registers[8], registers[9]) != (event["incoming_sp"]+16, event["continuation_pc"]):
            raise ValueError("Native stack helper restored unexpected SP/PC")
        for register, value in zip((7,6,3,2), event["frame_words"][:4]):
            if registers[register] != value: raise ValueError("Native saved-frame register differs")
        previous_spec = json.loads((Path(previous["directory"])/"scenario.json").read_text())
        for dump in previous_spec["dumps"]:
            expected = bytearray((Path(previous["directory"])/dump["name"]).read_bytes())
            offset = event["previous_stack_slot"]-number(dump["address"])
            if 0 <= offset <= len(expected)-4: struct.pack_into("<I", expected, offset, event["outgoing_sp"])
            if expected != (directory/dump["name"]).read_bytes():
                raise ValueError("Native stack-helper storage differs beyond its outgoing SP slot")
        suspended.pop(event["next_task"]["tcb"], None)
        suspended[event["previous_task"]["tcb"]] = {
            "saved_sp": event["outgoing_sp"], "frame_sha256": sha(snapshot_bytes(directory,event["outgoing_sp"],20))}
    last = Path(report["last_directory"])
    idle_sp = struct.unpack("<I", snapshot_bytes(last,0x70A01D88,4))[0]
    if idle_sp or report["last_execution"]["result"]["stop"] != "native_context_switch":
        raise ValueError("Final boundary is no longer the uninitialized native idle frame")
    notifications = [(r["instruction_pc"],r["register"],r["value"]) for r in report["requests"]]
    if notifications != [("0x7bc7a63f","0x9c013004",2), ("0x7bc15408","0x9c013006",1), ("0x7bc15408","0x9c013006",1)]:
        raise ValueError("Pending native notification sequence differs")
    ring = snapshot_bytes(last,0x93F01110,32)
    if struct.unpack_from("<IHH",ring) != (768,0,24): raise ValueError("Native pending-ring shape differs")
    messages = [{"service_id":hex(struct.unpack_from("<H",ring,offset)[0]),
                 "payload_bytes":struct.unpack_from("<H",ring,offset+2)[0],
                 "words":[hex(value) for value in struct.unpack_from("<II",ring,offset+4)]}
                for offset in (8,20)]
    routing = json.loads((ROUTING/"summary.json").read_text())
    if routing["passed"] != 38 or routing["camera_contacted"] or routing["complete_arm_boot_or_ipc_delivery"]:
        raise ValueError("ARM routing controls are incomplete or exceed their verified scope")
    if sha((ROUTING/"driver-source.py").read_bytes()) != routing["driver_sha256"] or sha(ARM_IMAGE.read_bytes()) != ARM_SHA:
        raise ValueError("ARM comparison source changed")
    comparisons = []
    for case in routing["cases"]:
        native = native_stage(Path(case["mn103_directory"]),case["mn103_execution"])
        arm = checked_arm(Path(case["arm_directory"]),case["arm_execution"])
        expected = number(case["expected"])
        if (native["result"]["stop"],arm["result"]["stop"]) != ("returned","returned") or (
                number(native["result"]["registers"][0]), number(arm["result"]["registers"]["r0"])) != (expected,expected):
            raise ValueError("ARM/MN103 native returns no longer agree")
        comparisons.append({"name":case["name"],"expected":case["expected"],"mn103":native,"arm":arm})
    vector = checked_arm(ROUTING/"reset_vector",routing["reset_vector"])
    system = checked_arm(ROUTING/"system_boundary",routing["system_boundary"])
    release.mkdir(mode=0o700)
    copied = []
    sources = [(p,p.name)for p in FROZEN_BACKEND.iterdir() if p.is_file()]
    sources += [(FLOW/"driver-source.py","native-language-flow.py"),
                (parent/"driver-source.py","notification-adapter.py"),
                (Path(report["task_switches"][0]["directory"])/"task-driver-source.py","task-adapter.py"),
                (ROUTING/"destination_800f_arm/driver-source.py","arm-adapter.py"),
                (ROUTING/"driver-source.py","arm-controls.py"),
                (Path("tools/arm_simulator/requirements-macos.txt"),"arm-requirements-macos.txt"),
                (Path(__file__),"evidence-collector.py")]
    for source,name in sources:
        target = release/name; shutil.copyfile(source,target); copied.append(artifact(target))
    (release/"gm5-mn103-sim").chmod(0o500)
    result = {"schema":1,"time_utc":datetime.now(timezone.utc).isoformat(),
              "scope":"Native cooperative worker tasks and matching ARM/MN103 service routing; complete cross-processor UI flow remains incomplete",
              "camera_contacted":False,"physical_region_patch_installed":False,
              "cpu_engine_and_gnu_libraries_unchanged":True,"mn103_build":artifact(RECEIPT),
              "retained_release":copied,"native_parent_stages":stages,
              "native_instructions":report["native_instructions"],"native_task_switches":report["task_switches"],
              "pending_notification_requests":report["requests"],"pending_ring_messages":messages,
              "unresolved_native_boundary":{"pc":"0x7be02f19","task_tcb":"0x70a01d70","task_id":0,
                                             "saved_sp":idle_sp,"reason":report["task_switch_blocked_reason"]},
              "arm_source":artifact(ARM_IMAGE),"arm_source_derivation":artifact(ARM_IMAGE.parent/"source.json"),
              "arm_dependencies":routing["cases"][0]["arm_execution"]["dependencies"],
              "arm_mn103_routing_comparisons":comparisons,"arm_reset_vector":vector,"arm_system_boundary":system,
              "repository_tests":{"passed":105,"skipped":0,"log":artifact(tests)},
              "complete_language_ui_flow":False,"interrupts_or_ipc_acknowledgements_supplied":False,
              "region_package_sha256":"4954b517462b8ee5f900945496b882ddfa45f97b540f0d1dad6dcdf706ea50c7",
              "limits":routing["limits"]+["The bounded initializer has not produced a saved idle-task stack.",
                  "Notification writes are recorded; hardware delivery, ARM callbacks and reply generation still need native initialization.",
                  "Command-word completion is an abstract busy-read fixture, not measured controller timing."]}
    save_json(output,result);return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True);parser.add_argument("--release",type=Path,required=True)
    parser.add_argument("--tests",type=Path,default=Path("work/gm5-cooperative-arm-full-tests.log"))
    args=parser.parse_args(); result=collect(args.out,args.release,args.tests)
    print(json.dumps({"native_instructions":result["native_instructions"],"repository_tests":result["repository_tests"]["passed"]}),flush=True)


if __name__=="__main__":main()
