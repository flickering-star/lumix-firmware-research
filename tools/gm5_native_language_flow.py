#!/usr/bin/env python3
"""Test native Language-menu events, complete confirmation, save and reload.

All instructions execute offline. There is no camera/USB or display device I/O.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from gm5_emulator import put, run_scenario, sha
from gm5_native_rtos_controls import CURRENT_TASK, control_addresses, control_scenario, u16, u32
from gm5_notify_emulator import run_notifications
from gm5_reflash_control import save_json
from gm5_region_emulator import inputs
from gm5_region_persistence import base, call
from gm5_rtos_emulator import BACKEND
from gm5_virtual_install import LOCK, UNLOCK


STATE = Path("work/gm5-ui-startup-with-native-rtos-2")
COMMAND_BACKEND = Path("work/toolchain/gdb-mn10300-build/gm5-mn103-sim-command_latches")
COOPERATIVE_BACKEND = Path("work/toolchain/gdb-mn10300-build/gm5-mn103-sim-cooperative_stops")


def flow(output: Path, state: Path, backend: Path, *, notifications=False, command_completion=False,
         cooperative=False, run_ready_tasks=False) -> dict:
    if run_ready_tasks and not (notifications and cooperative):
        raise ValueError("Running native ready tasks requires --record-notifications and --cooperative")
    prior = json.loads((state/"report.json").read_text())
    if prior["result"]["stop"] != "ui_startup_returned":
        raise ValueError("Requires completed native UI startup with native RTOS state")
    output.mkdir(parents=True, exist_ok=False); output.chmod(0o700)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    cases = []
    task, _, _ = control_addresses()

    def execute(spec: dict) -> Path:
        if command_completion:
            spec["command_controller"] = {"busy_reads": 2, "stuck_mask": 0}
            spec["assumptions"].append("The two reviewed command words use an abstract mask0x0010 completion fixture: other bits start zero and each command completes after two busy reads. Controller identity/physical work remain unmodeled.")
        directory = output/spec["name"]
        modeled = run_notifications(spec, backend, directory, allow_same_context=cooperative,
                                    run_ready_tasks=run_ready_tasks) if notifications else None
        if modeled:
            record = modeled["last_execution"]
            directory = Path(modeled["last_directory"])
        else:
            record = run_scenario(spec, backend, directory)
        if record["result"]["stop"] != "returned" or record["result"]["services"] is not None:
            reason = modeled.get("task_switch_blocked_reason") if modeled else None
            raise ValueError(f"Native language stage stopped unexpectedly: {spec['name']}: {record['result']}; task boundary={reason}")
        if int(record["result"]["registers"][8], 0) != spec["registers"]["sp"]:
            raise ValueError(f"Native language stage did not restore its caller stack: {spec['name']}")
        cases.append({"name": spec["name"], "directory": str(directory), "execution": record})
        if modeled:
            cases[-1]["notification_model"] = {"report": str(directory.parent/"notification-report.json"),
                                               "requests": modeled["requests"], "delivered_interrupts": 0}
        print(f"Passed {spec['name']}", flush=True)
        return directory

    # The service-registration layer has its own context table at93f0000c.
    # Execute its actual queue/table setup, stopping before the subsequent
    # interrupt-controller programming rather than supplying fictitious MMIO.
    spec = control_scenario("native_shared_ring_initialization", state, 0x7BC1522E, 0x80, 4, 0)
    spec["memory"] = [item for item in spec["memory"] if int(item["address"], 0) != CURRENT_TASK]
    rings = execute(spec)
    shared = (rings/"service-notification.data").read_bytes()
    for offset, size in ((0x10,256),(0x110,768),(0x410,256),(0x510,768),(0x810,768),(0xB10,768)):
        if (u32(shared,offset),u16(shared,offset+4),u16(shared,offset+6)) != (size,0,0):
            raise ValueError("Native shared-ring initialization did not set the reviewed capacities/empty offsets")
    spec = control_scenario("native_service_context_prefix", rings, 0x7BC15B13, 0, 4, 0)
    spec["memory"] = [item for item in spec["memory"] if int(item["address"], 0) != CURRENT_TASK]
    spec["registers"]["pc"] = 0x7BC15B13
    spec["stops"] = {"returned": 0x7BC15B3E}
    spec["assumptions"].append("Runs native application-service context/queue setup; stops before0x7bc15b3e interrupt-controller initialization.")
    services = execute(spec)
    spec = control_scenario("language_task_activation", services, 0x7BE02B38, 0xE0, 16, 0)
    spec["registers"]["a0"] = task
    spec["memory"] = [item for item in spec["memory"] if int(item["address"], 0) != CURRENT_TASK]
    active = execute(spec)
    spec = control_scenario("native_parent_menu_entry", active, 0x4010876D, 0xC0, 16, 0)
    spec["registers"]["d1"] = 0
    parent = execute(spec)
    # The real setup-item dispatcher saves this context before entering the
    # Language submenu. Confirmation restores it through0x40130846.
    selection_mode = (parent/"ram.data").read_bytes()[0x1AEEC4]
    parent_saved = execute(control_scenario("native_parent_context_save", parent, 0x40130A85, 0x80, 8, selection_mode))
    opened = execute(control_scenario("full_native_language_entry", parent_saved, 0x400EB4D3, 0x80, 8, 0))
    ram = (opened/"ram.data").read_bytes()
    if u16(ram, 0x1AEEBE) != 0 or ram[0xA0E912] != 4:
        raise ValueError("Language entry did not start with Japanese and a visible Language item")
    # Event family0x0f000002 is the native button-event path. Parameter6
    # selects the forward action; parameter7 selects confirmation. Both enter
    # the complete event handler registered for logical UI state29.
    spec = control_scenario("native_language_forward_event", opened, 0x400EA07A, 0, 0, 0x0F000002, callback_abi=True)
    spec["registers"].update(d1=6, a0=0)
    spec["memory_observations"] += [{"label": "pending_language", "address": 0x701AEEBE, "size": 2}]
    forward = execute(spec)
    ram = (forward/"ram.data").read_bytes()
    if u16(ram, 0x1AEEBE) != 1 or (forward/"settings.data").read_bytes()[0x1B9] != 0:
        raise ValueError("Native forward event did not select English while leaving saved Japanese unchanged")
    spec = control_scenario("native_language_confirm_event", forward, 0x400EA07A, 0, 0, 0x0F000002, callback_abi=True)
    spec["registers"].update(d1=7, a0=0)
    spec["memory_observations"] += [{"label": "saved_language", "address": 0x7BFB01B9, "size": 1},
                                    {"label": "ui_language", "address": 0x701AF239, "size": 1}]
    confirmed = execute(spec)
    settings = (confirmed/"settings.data").read_bytes()
    if settings[0x1B9] != 1 or (confirmed/"ram.data").read_bytes()[0x1AF239] != 1:
        raise ValueError("Full native confirmation did not commit English to settings and active cache")
    spec = control_scenario("native_language_save", confirmed, 0x401E3382, 0xA0, 12, 0)
    spec["budget"], spec["trace_every"] = 50000000, 1000
    saved = execute(spec)
    main, _, _ = inputs()
    source = saved/"virtual-nor.bin"
    spec = base("native_language_fresh_reload", source, main)
    # Boot loading/normalization never needed the old synchronization stubs;
    # remove them and their service model explicitly for this fresh-RAM run.
    spec["memory"] = [item for item in spec["memory"] if int(item["address"], 0) not in (LOCK, UNLOCK)]
    spec.pop("single_thread_sync", None)
    code = b""
    for target, mask, frame in [(0x401E2FFE, 0, 0), (0x401E3051, 0xF0, 20),
                                (0x40211EC6, 0x80, 8), (0x400A8427, 0, 4), (0x400AA012, 0, 4)]:
        code = call(code, target, mask, frame)
    spec["memory"].append(put(0x70008000, code+b"\xff"))
    spec["registers"]["pc"] = 0x70008000
    spec["stops"] = {"returned": 0x70008000+len(code)}
    spec["assumptions"].append("Fresh RAM loads the saved banks and runs native normalization/list/visibility; no RTOS return stubs are supplied or needed by this bounded reload.")
    reloaded = execute(spec)
    final_settings = (reloaded/"settings.data").read_bytes()
    final_ram = (reloaded/"ram.data").read_bytes()
    if (final_settings[0x1B9], final_ram[0x1AF239], final_ram[0xA0E912], final_ram[0xA68490]) != (1, 1, 4, 0):
        raise ValueError("Full native language flow did not retain English, visibility and policy zero after fresh reload")
    before, after = (state/"virtual-nor.bin").read_bytes(), source.read_bytes()
    changes = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    if not changes or any(not 0x1FA0000 <= i < 0x1FE0000 for i in changes):
        raise ValueError("Language save changed bytes outside the two ordinary settings banks")
    for case in cases:
        spec = json.loads((Path(case["directory"])/"scenario.json").read_text())
        for item in spec["memory"]:
            at, raw = int(item["address"], 0), bytes.fromhex(item["hex"])
            if any(at <= protected < at+len(raw) for protected in (0x701AEEBE, 0x701AF239, 0x7BFB01B9)):
                raise ValueError("Fixture directly wrote a language value instead of native UI events")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Complete native UI entry/button-event/confirmation/save/fresh-reload language flow",
              "passed": len(cases), "cases": cases, "final_language": 1,
              "language_values_directly_written_by_fixture": False,
              "rtos_return_stubs_used": False, "changed_persistent_bytes": len(changes),
              "all_save_changes_in_ordinary_settings_banks": True,
              "camera_contacted": False, "display_output_emulated": False,
              "notification_writes_modeled_without_delivery": notifications,
              "abstract_command_completion_fixture": command_completion,
              "limits": ["Native task7 is activated and selected as a serial current-task fixture; its task entry/scheduler do not run.",
                         "Logical UI state and handlers execute; no screen rendering, button hardware or concurrent task model is claimed.",
                         "Fresh reload is a bounded settings/language startup subsequence, not complete camera boot."],
              "driver_sha256": sha(Path(__file__).read_bytes())}
    save_json(output/"summary.json", report)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument("--backend", type=Path)
    parser.add_argument("--record-notifications", action="store_true", help="Record the two reviewed notification stores without delivering interrupts")
    parser.add_argument("--command-completion", action="store_true", help="Use the bounded two-register completion fixture")
    parser.add_argument("--cooperative", action="store_true", help="Execute same-task stack transitions; stop before changing tasks")
    parser.add_argument("--run-ready-tasks", action="store_true", help="Execute bounded native task changes using validated activation or previously saved frames")
    args = parser.parse_args()
    backend = args.backend or (COOPERATIVE_BACKEND if args.cooperative else COMMAND_BACKEND if args.command_completion else BACKEND)
    flow(args.out, args.state, backend, notifications=args.record_notifications,
         command_completion=args.command_completion, cooperative=args.cooperative,
         run_ready_tasks=args.run_ready_tasks)


if __name__ == "__main__":
    main()
