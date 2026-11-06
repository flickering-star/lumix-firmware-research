#!/usr/bin/env python3
"""Trace and execute GM5 native language normalization/menu construction offline.

Uses the physically verified policy-zero main. Candidate changes redirect the
Japanese language dispatch and preserve Language-menu visibility, not region identity.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct

from gh2_debug_verify import checked_disassembly
from gm5_emulator import DEFAULT_BACKEND, base_scenario, put, run_scenario, sha
from gm5_reflash_control import save_json
from gm5_virtual_install import BACKUP, BACKUP_SHA, SECONDARY_SHA

MAIN = Path("captures/gm5-program-readback-f61hhqc_/result/program-main.bin")
MAIN_SHA = "c918553771018e171605ecb1f177a4d64bc94b221fe5304b8ff419f4509d208d"
SECONDARY = Path("work/gm5-emulator-installed-initializers-final/private-inputs/installed-program2.bin")
BASE, JP = 0x40000000, 0x100
NORMALIZE, MENU = 0x40211EC6, 0x400A8427
NORMALIZER_TABLE, MENU_TABLE = 0x40491894, 0x40379B84
INTERNATIONAL_LIST = 0x40379678
LANGUAGE, UI_LANGUAGE, LIVE_LIST = 0x7BFB01B9, 0x701AF239, 0x70A0F150


def inputs() -> tuple[bytes, bytes, bytes]:
    main, secondary, flash = MAIN.read_bytes(), SECONDARY.read_bytes(), BACKUP.read_bytes()
    if (sha(main), sha(secondary), sha(flash)) != (MAIN_SHA, SECONDARY_SHA, BACKUP_SHA):
        raise ValueError("Expected the physically verified current GM5 main, original secondary and protected NOR")
    return main, secondary, flash


def table(data: bytes, address: int) -> list[dict]:
    result = []
    for at in range(address-BASE, address-BASE+512, 8):
        ident, state, reserved, auxiliary = struct.unpack_from("<HBBI", data, at)
        if ident == 0xFFFF:
            return result
        result.append({"id": ident, "state": state, "reserved": reserved, "auxiliary": auxiliary})
    raise ValueError("Language list lacks a bounded terminator")


def dispatch(data: bytes, address: int) -> dict[int, tuple[int, int]]:
    rows = {}
    for at in range(address-BASE, address-BASE+256, 8):
        ident, target = struct.unpack_from("<II", data, at)
        if ident:
            if ident in rows: raise ValueError("Duplicate dispatch identifier")
            rows[ident] = (at+4, target)
    return rows


def patches(main: bytes) -> list[dict]:
    rows = []
    for address, old, target, purpose in ((NORMALIZER_TABLE, 0x40211FC5, 0x40211FAB, "saved-language validation/default"),
                                          (MENU_TABLE, 0x400A858F, 0x400A8565, "language-menu construction")):
        at, previous = dispatch(main, address)[JP]
        if previous != old: raise ValueError("Japanese language dispatch differs")
        before, after = struct.pack("<I", previous), struct.pack("<I", target)
        differences = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        if len(differences) != 1: raise ValueError("Expected one-byte dispatch redirection")
        index = at+differences[0]
        rows.append({"offset": index, "address": BASE+index, "before": main[index],
                     "after": after[differences[0]], "region": JP, "purpose": purpose,
                     "dispatch_entry_address": BASE+at-4, "original_target": previous, "target": target})
    if main[0xAA012:0xAA01F] != bytes.fromhex("dd12c51c000004fac80001c913"):
        raise ValueError("Japanese Language-menu hide guard differs")
    rows.append({"offset": 0xAA01D, "address": 0x400AA01D, "before": 0xC9, "after": 0xCA,
                 "region": JP, "purpose": "preserve the Language setup-menu item instead of hiding it",
                 "original_branch": "bne0x400aa030", "patched_branch": "bra0x400aa030"})
    return rows


def candidate(main: bytes) -> bytes:
    if sha(main) != MAIN_SHA: raise ValueError("Region candidate must start from the verified policy-zero main")
    result = bytearray(main)
    for patch in patches(main): result[patch["offset"]] = patch["after"]
    if result[0x6B1BDC:0x6B1BDE] != b"\0\0": raise ValueError("Persistent update policy changed")
    if [i for i, (a, b) in enumerate(zip(main, result)) if a != b] != sorted(p["offset"] for p in patches(main)):
        raise ValueError("Unexpected region patch scope")
    for at in (NORMALIZER_TABLE, MENU_TABLE):
        old, new = dispatch(main, at), dispatch(result, at)
        if {k: v for k, v in old.items() if k != JP} != {k: v for k, v in new.items() if k != JP}:
            raise ValueError("Non-Japanese region mapping changed")
    return bytes(result)


def scenario(name: str, main: bytes, flash: bytes, *, region: int, language: int,
             settings_mode: int = 1, patched_rom: bool = False, menu_only: bool = False) -> dict:
    spec = base_scenario(name)
    spec["images"] = [{"path": str(MAIN), "address": BASE, "sha256": MAIN_SHA},
                      {"path": str(SECONDARY), "address": 0x7BC00000, "sha256": SECONDARY_SHA}]
    settings = bytearray(flash[0x1FA0000:0x1FC0000])
    struct.pack_into("<HH", settings, 0x32E, settings_mode, region)
    settings[0x1B9] = language
    spec["memory"] = [put(0x70000000, main[0x643B7C:0x64B5B8]),
                      put(0x70A01E6C, main[0x64B5B8:0x6DD76C]),
                      put(0x7BFB0000, settings), put(UI_LANGUAGE, b"\xa5")]
    if patched_rom:
        spec["memory"] += [put(p["address"], bytes([p["after"]])) for p in patches(main)]
    stub = 0x70008000
    code = b""
    if not menu_only:
        code += b"\xdd"+struct.pack("<i", NORMALIZE-stub)+bytes([0x80, 8])
    at = stub+len(code)
    code += b"\xdd"+struct.pack("<i", MENU-at)+bytes([0, 4, 0xFF])
    code = code[:-1]
    at = stub+len(code)
    code += b"\xdd"+struct.pack("<i", 0x400AA012-at)+bytes([0, 4, 0xFF])
    spec["memory"].append(put(stub, code))
    spec["registers"].update(pc=stub, d2=0x22334455, d3=0x55667788, a2=0x33445566, a3=0x44556677)
    spec["stops"] = {"returned": stub+len(code)-1}
    spec["budget"], spec["trace_every"] = 100000, 100
    spec["dumps"] = [{"name": "settings.data", "address": 0x7BFB0000, "size": len(settings)},
                     {"name": "ui-language.data", "address": UI_LANGUAGE, "size": 1},
                     {"name": "menu.data", "address": LIVE_LIST, "size": 256},
                     {"name": "setup-menu.data", "address": 0x70A0E898, "size": 216}]
    spec["assumptions"] = ["Current physically verified policy-zero main and original installed secondary.",
                           "RAM initializer regions and current settings fixture are seeded from retained ROM/NOR.",
                           "Executes complete native language normalizer and menu-list builder, not the entire UI/startup.",
                           "No filesystem, EEPROM save, display or physical camera transport is modeled by this function harness."]
    spec["region_test"] = {"region": region, "input_language": language, "settings_mode": settings_mode,
                           "patched_rom": patched_rom, "menu_only": menu_only,
                           "settings_before_sha256": sha(settings)}
    return spec


def tests(output: Path, backend: Path, *, exhaustive=False) -> dict:
    main, secondary, flash = inputs()
    changed = candidate(main)
    output.mkdir(parents=True, exist_ok=False); output.chmod(0o700)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    (output/"expected-region-main.bin").write_bytes(changed)
    (output/"expected-region-main.bin").chmod(0o400)
    controls = []
    region_cases = [JP, 1, 0x102, 0x11D, 0, 0xFFFF]
    languages = (0, 1, 6, 19, 23, 25, 254, 255)
    if exhaustive: region_cases = list(range(0x122)) + [0xFFFF]
    for is_patch in (False, True):
        for region in region_cases:
            for language in languages if region == JP else (0, 1, 255):
                name = f"{'patched' if is_patch else 'stock'}_r{region:04x}_l{language:02x}"
                spec = scenario(name, main, flash, region=region, language=language, patched_rom=is_patch)
                directory = output/name
                record = run_scenario(spec, backend, directory)
                if record["result"]["stop"] != "returned":
                    raise ValueError(f"Native language control failed {name}: {record['result']}")
                settings = (directory/"settings.data").read_bytes()
                ui = (directory/"ui-language.data").read_bytes()[0]
                menu = (directory/"menu.data").read_bytes()
                setup = (directory/"setup-menu.data").read_bytes()
                if struct.unpack_from("<H", setup, 0x78)[0] != 143:
                    raise ValueError("Language setup item ID differs")
                visibility = setup[0x7A]
                if ui != settings[0x1B9]: raise ValueError("Language shadow/cache diverged")
                before = bytearray(flash[0x1FA0000:0x1FC0000])
                struct.pack_into("<HH", before, 0x32E, 1, region); before[0x1B9] = language
                differences = [i for i, (a, b) in enumerate(zip(before, settings)) if a != b]
                if any(i != 0x1B9 for i in differences):
                    raise ValueError("Normalizer modified other settings/region/calibration bytes")
                ids = []
                for at in range(0, len(menu), 8):
                    ident, state = struct.unpack_from("<HB", menu, at)
                    if ident == 65535: break
                    if state != 4: raise ValueError("Unexpected language availability state")
                    ids.append(ident)
                else: raise ValueError("Native menu has no bounded terminator")
                if region == JP:
                    allowed = [row["id"] for row in table(main, INTERNATIONAL_LIST)] if is_patch else [0]
                    wanted = language if language in allowed else 1 if is_patch else 0
                    if ui != wanted or ids != allowed: raise ValueError("Japanese-region behavior differs from the independent list oracle")
                    if visibility != (4 if is_patch else 0):
                        raise ValueError("Japanese Language-menu visibility differs")
                controls.append({"name": name, "region": hex(region), "input_language": language,
                                 "patched": is_patch, "normalized_language": ui, "menu_ids": ids,
                                 "settings_modified_offsets": [hex(i) for i in differences],
                                 "settings_region_and_other_bytes_unchanged": True, "execution": record})
                controls[-1]["language_menu_visibility_state"] = visibility
        print(f"Passed {'patched' if is_patch else 'stock'} language controls", flush=True)
    stock_by_key = {(c["region"], c["input_language"]): c for c in controls if not c["patched"]}
    for case in controls:
        if case["patched"] and case["region"] != hex(JP):
            old = stock_by_key[(case["region"], case["input_language"])]
            if (case["normalized_language"], case["menu_ids"], case["language_menu_visibility_state"]) != (
                    old["normalized_language"], old["menu_ids"], old["language_menu_visibility_state"]):
                raise ValueError("Non-Japanese region behavior changed")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Current GM5 native region-specific language normalization and menu construction",
              "passed": len(controls), "exhaustive_regions": exhaustive, "controls": controls,
              "patches": patches(main), "original_main_sha256": MAIN_SHA, "candidate_main_sha256": sha(changed),
              "international_language_ids": [row["id"] for row in table(main, INTERNATIONAL_LIST)],
              "driver_sha256": sha(Path(__file__).read_bytes()), "camera_contacted": False,
              "physical_firmware_modified": False, "eeprom_persistence_emulated": False}
    save_json(output/"summary.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", type=Path, default=DEFAULT_BACKEND)
    parser.add_argument("--exhaustive", action="store_true")
    args = parser.parse_args()
    result = tests(args.out, args.backend, exhaustive=args.exhaustive)
    print(f"Passed {result['passed']} native region/language controls")


if __name__ == "__main__":
    main()
