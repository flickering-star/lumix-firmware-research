#!/usr/bin/env python3
"""Extend the GM5 region harness through native settings load/save and virtual NOR.

All settings/flash outputs are private virtual files. No camera I/O is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct

from gm5_emulator import DEFAULT_BACKEND, put, word, run_scenario, sha
from gm5_reflash_control import save_json
from gm5_region_emulator import MAIN, MAIN_SHA, SECONDARY, SECONDARY_SHA, candidate, inputs
from gm5_virtual_install import scenario as nor_scenario


def call(code: bytes, target: int, mask: int, frame: int, stub=0x70008000) -> bytes:
    return code+b"\xdd"+struct.pack("<i", target-(stub+len(code)))+bytes([mask, frame])


def base(name: str, source: Path, main: bytes) -> dict:
    images = [{"path": str(MAIN), "address": 0x40000000, "sha256": MAIN_SHA},
              {"path": str(SECONDARY), "address": 0x7BC00000, "sha256": SECONDARY_SHA}]
    spec = nor_scenario(name, images, main, source, sync=True)
    spec["budget"], spec["trace_every"] = 20000000, 1000
    spec["dumps"] = [{"name": "ram.data", "address": 0x70000000, "size": 0x1000000},
                     {"name": "settings.data", "address": 0x7BFB0000, "size": 0x40000}]
    return spec


def boot(name: str, source: Path, main: bytes, output: Path, backend: Path) -> dict:
    spec = base(name, source, main)
    code = call(b"", 0x401E2FFE, 0, 0)
    code = call(code, 0x401E3051, 0xF0, 20)
    code = call(code, 0x40211EC6, 0x80, 8)
    code = call(code, 0x400A8427, 0, 4)
    code = call(code, 0x400AA012, 0, 4)+b"\xff"
    spec["memory"].append(put(0x70008000, code))
    spec["registers"]["pc"] = 0x70008000
    spec["stops"] = {"boot_language_initialized": 0x70008000+len(code)-1}
    spec["assumptions"] += ["Executes native settings-buffer setup, A/B bank loading/selection and language startup functions.",
                             "This is a bounded boot subsequence; sensor/display/USB tasks and the full scheduler are not started."]
    return run_scenario(spec, backend, output)


def from_state(name: str, source: Path, main: bytes, state: Path) -> dict:
    spec = base(name, source, main)
    spec["memory"] = spec["memory"][2:]  # Retain only checked RTOS stubs; restore the actual preceding state.
    for filename, address in (("ram.data", 0x70000000), ("settings.data", 0x7BFB0000)):
        path = state/filename
        spec["images"].append({"path": str(path), "address": address, "sha256": sha(path.read_bytes())})
    spec["assumptions"].append("Every RAM/settings byte is restored from the preceding completed native stage.")
    return spec


def navigate_english(state: Path, source: Path, main: bytes, output: Path, backend: Path) -> dict:
    spec = from_state("native_menu_navigation", source, main, state)
    ram = (state/"ram.data").read_bytes()
    if ram[0x1AF239] != 0 or ram[0xA0E912] != 4:
        raise ValueError("Expected visible Language item with Japanese currently selected")
    menu_ids = []
    for at in range(0xA0F150, 0xA0F250, 8):
        ident = struct.unpack_from("<H", ram, at)[0]
        if ident == 65535: break
        menu_ids.append(ident)
    if len(menu_ids) != 23 or menu_ids[-1] != 0 or menu_ids[0] != 1:
        raise ValueError("Expected the exact23-language menu with English first and Japanese last")
    # Open the real list context, move forward through one complete cycle and
    # one extra entry, recording each native selection. No language value is
    # injected into the pending-selection word.
    code = bytes.fromhex("800f04fcdc50f1a070")
    code = call(code, 0x401286CE, 0xA0, 12)
    for index in range(len(menu_ids)+1):
        code += bytes.fromhex("8001")
        code = call(code, 0x4012876A, 0xC0, 12)
        code += bytes.fromhex("fcacbeee1a70fc83")+struct.pack("<I", 0x70050000+2*index)
    code += b"\xff"
    spec["memory"].append(put(0x70008000, code))
    spec["registers"]["pc"] = 0x70008000
    spec["stops"] = {"english_selected": 0x70008000+len(code)-1}
    spec["assumptions"].append("Native list-open/navigation functions process24forward button actions; display callbacks are outside this subsequence.")
    record = run_scenario(spec, backend, output)
    if record["result"]["stop"] != "english_selected":
        raise ValueError(f"Native menu navigation failed: {record['result']}")
    after = (output/"ram.data").read_bytes()
    selected = list(struct.unpack_from("<24H", after, 0x50000))
    if selected != menu_ids+[1] or struct.unpack_from("<H", after, 0x1AEEBE)[0] != 1:
        raise ValueError("Native next-language actions did not cycle the actual menu and select English")
    save_json(output/"navigation.json", {"selected_language_ids": selected,
                                       "all23choices_reachable": True, "final_selection": 1,
                                       "pending_language_directly_written_by_fixture": False})
    return record


def persistence(output: Path, backend: Path, *, patch=False, source_input: Path | None = None,
                navigate=False) -> dict:
    main, _, flash = inputs()
    output.mkdir(parents=True, exist_ok=False); output.chmod(0o700)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    raw = bytearray(source_input.read_bytes() if source_input else flash)
    expected_main = candidate(main) if patch else main
    if source_input:
        if len(raw) != len(flash) or raw[:len(main)] != expected_main:
            raise ValueError("Programmed input must contain the exact region candidate/current main")
    else:
        raw[:len(main)] = expected_main
    source = output/"input-nor.bin"; source.write_bytes(raw); source.chmod(0o400)
    first = output/"native_boot"
    boot_record = boot("native_boot", source, main, first, backend)
    if boot_record["result"]["stop"] != "boot_language_initialized":
        raise ValueError(f"Native startup failed: {boot_record['result']}")
    print("Passed native settings load and language startup", flush=True)
    navigation_record = None
    selection_state, selection_source = first, first/"virtual-nor.bin"
    if navigate:
        navigation_state = output/"native_menu_navigation"
        navigation_record = navigate_english(first, selection_source, main, navigation_state, backend)
        selection_state, selection_source = navigation_state, navigation_state/"virtual-nor.bin"
        print("Passed native menu navigation through all23choices to English", flush=True)
    selected = output/"native_select_english"
    spec = from_state("native_select_english", selection_source, main, selection_state)
    if not navigate:
        spec["memory"].append(put(0x701AEEBE, b"\1\0"))
    spec["registers"]["pc"] = 0x400EA1EA
    spec["stops"] = {"language_selected": 0x400EA204}
    spec["assumptions"].append("Executes the actual language-selection stores and normal selection flag; stops before UI/display callbacks.")
    select_record = run_scenario(spec, backend, selected)
    if select_record["result"]["stop"] != "language_selected":
        raise ValueError(f"Native language selection failed: {select_record['result']}")
    settings = (selected/"settings.data").read_bytes()
    if settings[0x1B9] != 1 or struct.unpack_from("<H", settings, 0x312)[0] != 1:
        raise ValueError("Normal native selection did not store English and its selection flag")
    print("Passed native English selection stores", flush=True)
    saved = output/"native_save"
    spec = from_state("native_save", selected/"virtual-nor.bin", main, selected)
    code = call(b"", 0x401E3382, 0xA0, 12)+b"\xff"
    spec["memory"].append(put(0x70008000, code))
    spec["registers"]["pc"] = 0x70008000
    spec["stops"] = {"settings_saved": 0x70008000+len(code)-1}
    spec["budget"] = 50000000
    spec["watchpoints"] = {"settings_writer_return": 0x40276431,
                          "extra_writer_return": 0x401E3454,
                          "extra_writer_second_return": 0x401E34A3}
    save_record = run_scenario(spec, backend, saved)
    if save_record["result"]["stop"] != "settings_saved":
        report = {"scope": "Native settings persistence pilot stopped at an explicit unmodeled access",
                  "boot": boot_record, "selection": select_record, "save": save_record,
                  "camera_contacted": False}
        save_json(output/"stopped.json", report)
        raise ValueError(f"Native settings save stopped: {save_record['result']}")
    print("Passed native settings save against virtual NOR", flush=True)
    final = output/"native_reboot"
    reboot_record = boot("native_reboot", saved/"virtual-nor.bin", main, final, backend)
    if reboot_record["result"]["stop"] != "boot_language_initialized":
        raise ValueError(f"Native settings reload failed: {reboot_record['result']}")
    final_settings = (final/"settings.data").read_bytes()
    final_ram = (final/"ram.data").read_bytes()
    wanted = 1 if patch else 0
    if final_settings[0x1B9] != wanted or final_ram[0x1AF239] != wanted:
        raise ValueError("Save/reboot language result differs from the region-lock hypothesis")
    after = (saved/"virtual-nor.bin").read_bytes()
    differences = [i for i, (a, b) in enumerate(zip(raw, after)) if a != b]
    if any(not 0x1FA0000 <= i < 0x1FE0000 for i in differences):
        raise ValueError("Settings save changed data outside its two persistent banks")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(), "patch": patch,
              "scope": "Native settings A/B load, language selection, NOR save and fresh native language initialization",
              "executions": {"boot": boot_record, "selection": select_record, "save": save_record, "reboot": reboot_record},
              "final_settings_language": final_settings[0x1B9], "final_ui_language": final_ram[0x1AF239],
              "expected_language": wanted, "settings_save_changed_bytes": len(differences),
              "all_save_changes_within_two_settings_banks": True,
              "driver_sha256": sha(Path(__file__).read_bytes()), "camera_contacted": False,
              "physical_persistence_tested": False,
              "programmed_source": str(source_input) if source_input else None,
              "source_sha256": sha(raw),
              "limits": ["Bounded native boot subsequence and selection stores; display callbacks and the full scheduler are not executed.",
                         "Checked RTOS stubs and simplified cache/NOR timing remain; no physical EEPROM/calibration operation was attempted."]}
    if navigation_record:
        report["executions"]["navigation"] = navigation_record
        report["language_selected_through_native_menu_navigation"] = True
    save_json(output/"summary.json", report)
    print(f"Passed native save/reboot: {'English retained' if patch else 'English reset to Japanese'}", flush=True)
    return report


def pilot(output: Path, backend: Path, *, patch=False) -> dict:
    main, _, flash = inputs()
    output.mkdir(parents=True, exist_ok=False); output.chmod(0o700)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    raw = bytearray(flash); raw[:len(main)] = candidate(main) if patch else main
    source = output/"input-nor.bin";source.write_bytes(raw);source.chmod(0o400)
    record = boot("native_settings_boot", source, main, output/"native_settings_boot", backend)
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(), "patch": patch,
              "boot_execution": record, "driver_sha256": sha(Path(__file__).read_bytes()),
              "camera_contacted": False}
    save_json(output/"pilot.json", report)
    print(json.dumps({"stop": record["result"]["stop"], "pc": record["result"]["pc"],
                      "steps": record["result"]["steps"], "nor": record["result"]["nor"]}), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--patched", action="store_true")
    parser.add_argument("--persistence", action="store_true")
    parser.add_argument("--source-nor", type=Path, help="Exact encoded-and-programmed virtual candidate NOR")
    parser.add_argument("--navigate", action="store_true", help="Use native menu navigation to select English before saving")
    parser.add_argument("--backend", type=Path, default=DEFAULT_BACKEND)
    args = parser.parse_args()
    if args.persistence:
        persistence(args.out, args.backend, patch=args.patched, source_input=args.source_nor, navigate=args.navigate)
    else:
        if args.source_nor: parser.error("--source-nor requires --persistence")
        pilot(args.out, args.backend, patch=args.patched)


if __name__ == "__main__":
    main()
