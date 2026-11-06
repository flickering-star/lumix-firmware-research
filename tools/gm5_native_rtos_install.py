#!/usr/bin/env python3
"""Run the exact region package's native programming job without RTOS stubs.

The prior board/shutdown skips remain explicit. All NOR writes are virtual.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from gm5_emulator import run_scenario, sha, word
from gm5_native_rtos_controls import CURRENT_TASK, control_addresses, u32
from gm5_policy_package import install_spec
from gm5_reflash_control import save_json
from gm5_region_emulator import MAIN, MAIN_SHA, SECONDARY, SECONDARY_SHA, candidate, inputs, patches
from gm5_region_package import validate
from gm5_rtos_emulator import BACKEND, restored_scenario
from gm5_virtual_install import LOCK, UNLOCK


BUILD = Path("work/gm5-region-package-2")
DECODED = Path("work/gm5-region-package-native-2/region_decode_allowed")
STATE = Path("work/gm5-native-rtos-controls-1/native_task7_activation")


def tests(output: Path, state: Path, backend: Path) -> dict:
    main, _, flash = inputs(); wanted = candidate(main)
    built = json.loads((BUILD/"build-report.json").read_text())
    raw = Path(built["package"]["path"]).read_bytes()
    if sha(raw) != built["package"]["sha256"]:
        raise ValueError("Exact encoded region candidate changed")
    validate(raw, wanted)
    decoded, context = DECODED/"decoded-input.data", DECODED/"context.bin"
    if decoded.read_bytes()[0x600:] != wanted:
        raise ValueError("Retained native decoding output differs from region candidate")
    current_path = Path(built["virtual_current_nor"]["path"])
    current = current_path.read_bytes()
    if sha(current) != built["virtual_current_nor"]["sha256"] or current[:len(main)] != main:
        raise ValueError("Virtual current policy-zero source differs")
    images = [{"path": str(MAIN), "address": 0x40000000, "sha256": MAIN_SHA},
              {"path": str(SECONDARY), "address": 0x7BC00000, "sha256": SECONDARY_SHA}]
    task, _, semaphore = control_addresses()
    output.mkdir(parents=True, exist_ok=False); output.chmod(0o700)
    cases = []
    for name, fail, cut in (("native_rtos_region_install", 0, 0),
                            ("native_rtos_region_program_error", 1, 0),
                            ("native_rtos_region_power_cut", 0, 2)):
        prior = install_spec(name, images, main, flash, decoded, context, fail=fail, cut=cut)
        inherited = prior["memory"]
        if [int(item["address"], 0) for item in inherited[:4]] != [0x70000000, 0x70A01E6C, LOCK, UNLOCK]:
            raise ValueError("Prior job scenario initialization/stub layout changed")
        spec = restored_scenario(name, state)
        spec["images"] += prior["images"][2:]
        spec["memory"] += inherited[4:]+[word(CURRENT_TASK, task)]
        if any(int(item["address"], 0) in (LOCK, UNLOCK) for item in spec["memory"]):
            raise ValueError("Native RTOS scenario still overrides a synchronization function")
        spec["registers"].update(prior["registers"])
        for key in ("stops", "budget", "trace_every", "dumps"):
            if key != "dumps": spec[key] = prior[key]
            else: spec[key] += prior[key]
        spec["nor"] = dict(prior["nor"], path=str(current_path), sha256=sha(current))
        spec["watchpoints"] = dict(prior["watchpoints"], native_writer_semaphore_wait=LOCK,
                                    native_writer_semaphore_signal=UNLOCK)
        spec["assumptions"] += [
            "Uses the exact region package's prior completed native decode output/context; no decoding function is replaced.",
            "The original policy-zero NOR is the programming source; RTOS state is restored from bounded native object/task initialization.",
            "Native-activated task7 is selected explicitly as current; the task scheduler and task entry do not execute.",
            "The original board/shutdown skips at0x7bd4fe14/0x7bd4ff0d remain explicit and UI callbacks stay disabled.",
            "Every semaphore/mutex instruction is unchanged; no checked synchronization return stubs or SYNC service model is configured.",
            "Stops after the native programming iteration, before final cleanup/restart; this is not a complete machine boot.",
        ]
        directory = output/name
        record = run_scenario(spec, backend, directory)
        result = record["result"]
        stop = "nor_power_cut" if cut else "programming_finished"
        if result["stop"] != stop or result["services"] is not None:
            raise ValueError(f"Unexpected native RTOS installation result: {result}")
        expected = bytearray(current)
        if fail or cut:
            expected[:0x20000] = b"\xff"*0x20000
            if cut: expected[:1024] = wanted[:1024]
        else: expected[:len(wanted)] = wanted
        after = (directory/"virtual-nor.bin").read_bytes()
        if after != expected:
            raise ValueError("Native RTOS installation differs from complete virtual NOR oracle")
        if not cut and u32((directory/"ram.data").read_bytes(), semaphore-0x70000000+24) != 1:
            raise ValueError("Native install did not restore the writer semaphore token")
        events = [json.loads(line) for line in (directory/"trace.jsonl").read_text().splitlines()
                  if '"event":"watch"' in line]
        statuses = [int(item["d0"], 0) for item in events if item["label"] == "component_writer_return"]
        if not cut and statuses != [0x8000000C if fail else 0]:
            raise ValueError("Native component writer status differs")
        synchronization = [item for item in events if item["label"].startswith("native_writer_semaphore_")]
        if any(int(item["d0"], 0) != 0x12 for item in synchronization):
            raise ValueError("Native writer used another synchronization identifier")
        counts = result["nor"]
        expected_counts = (1, 1) if cut else (1, 0) if fail else (64, 8192)
        if (counts["erases"], counts["programs"], counts["zero_to_one_words"]) != (*expected_counts, 0):
            raise ValueError("Native RTOS erase/program counts differ")
        cases.append({"name": name, "execution": record, "complete_virtual_nor_matches_expected": True,
                      "native_semaphore_events": synchronization, "component_returns": [hex(v) for v in statuses],
                      "outside_main_unchanged": after[len(main):] == current[len(main):]})
        if not fail and not cut:
            differences = [i for i, (a, b) in enumerate(zip(current, after)) if a != b]
            if differences != sorted(item["offset"] for item in patches(main)):
                raise ValueError("Native RTOS install changed more than the three language bytes")
            cases[-1]["exact_three_language_byte_changes"] = True
        print(f"Passed {name}", flush=True)
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Exact region candidate programming job with unchanged native RTOS synchronization",
              "passed": len(cases), "cases": cases, "package": built["package"],
              "candidate_main_sha256": sha(wanted), "camera_contacted": False,
              "rtos_return_stubs_used": False, "board_shutdown_skips_remain": True,
              "task_runtime_or_concurrent_cpus_emulated": False,
              "driver_sha256": sha(Path(__file__).read_bytes())}
    save_json(output/"summary.json", report)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument("--backend", type=Path, default=BACKEND)
    args = parser.parse_args()
    tests(args.out, args.state, args.backend)


if __name__ == "__main__":
    main()
