#!/usr/bin/env python3
"""Replay short physical GM5 language-patch checks offline; no camera access.

Proves three exact ROM windows, ROM/RAM policy zero and English after the
owner-reported power cycle. Does not claim a complete main/NOR readback.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct

from gm1_capture_verify import BASE, GM5_CONTROL, parse_events
from gm5_emulator import sha
from gm5_policy_proof import read_capture
from gm5_prompt_package import artifact
from gm5_region_emulator import inputs, candidate, patches
from gm5_region_package import validate

PACKAGE_SHA = "4954b517462b8ee5f900945496b882ddfa45f97b540f0d1dad6dcdf706ea50c7"
MAIN_SHA = "5364cde77a78a40fce270bf1c24642a9fbd2e6d7d3501bb38d8b806548a48d67"
PATCH_WINDOWS = (
    (0x400AA000, "language-visibility.bin"),
    (0x40379800, "language-list.bin"),
    (0x40491800, "language-normalizer.bin"),
)
LANGUAGE_WINDOWS = (
    (0x4061E400, "settings-dispatch.bin"),
    (0x4036CC00, "settings-branch.bin"),
    (0x4036D400, "settings-writer.bin"),
    (0x701AF000, "language-ui-state.bin"),
    (0x70A0F000, "language-menu-state.bin"),
    (0x70A67800, "shutdown-state.bin"),
)


def short_capture(capture: Path, mode: str, windows: tuple) -> tuple[dict, dict]:
    directory = capture / "result"
    summary = json.loads((directory / "summary.json").read_text())
    if (summary["model"], summary["mode"], summary["exit_status"]) != ("DMC-GM5", mode, 0):
        raise ValueError("Incomplete or different short capture")
    parsed = parse_events((json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()),
                          model="DMC-GM5")
    identity = parsed["identities"]
    expected_identity = {"product_name": "DMC-GM5", "vendor_id": 0x04DA, "product_id": 0x2370,
                         "interface": [255, 160, 176], "configuration": 1,
                         "alternate_setting": 0, "endpoints": 3}
    if len(identity) != 1 or any(identity[0].get(k) != v for k, v in expected_identity.items()):
        raise ValueError("GM5 USB identity differs")
    frames = parsed["frames"]
    if [f["operation"] for f in frames] != [0x38]*16 + [0x5C]*len(windows):
        raise ValueError("Unexpected request order/count in short capture")
    control = b"".join(f["payload"] for f in frames[:16])
    if ([f["index"] for f in frames[:16]] != list(range(0x3F80, 0x3F90))
            or control != GM5_CONTROL or control != (directory / "fixed-markers.bin").read_bytes()):
        raise ValueError("GM5 settings control differs")
    if (parsed["controls"] != summary["control_requests_attempted"]
            or parsed["writes"] != summary["bulk_writes_attempted"]
            or summary["validated_word_responses"] != 16
            or summary["program_block_bytes"] != 1024*len(windows)):
        raise ValueError("Short capture counts differ")
    data, records = {}, []
    for frame, (address, name) in zip(frames[16:], windows):
        payload = (directory / name).read_bytes()
        if (BASE + frame["index"]*1024 != address or len(payload) != 1024
                or payload != frame["payload"]):
            raise ValueError("Short window address/file differs from validated packets")
        data[address] = payload
        records.append({"address": hex(address), **artifact(directory / name)})
    return {"capture": str(capture), "windows": records,
            "events": artifact(directory / "events.jsonl"),
            "request_count": len(frames), "all_requests_are_reads": True}, data


def collect(observation_path: Path, output: Path) -> dict:
    observation = json.loads(observation_path.read_text())
    if not (observation["owner_selected_english_in_camera"]
            and observation["owner_reports_english_survived_manual_off_on"]):
        raise ValueError("Owner menu-selection/power-cycle observation is missing")
    original, _, _ = inputs()
    expected = candidate(original)
    package = Path("work/gm5-region-package-2/GM5__V11.bin")
    raw = package.read_bytes()
    if sha(raw) != PACKAGE_SHA or sha(expected) != MAIN_SHA:
        raise ValueError("Exact validated language candidate differs")
    validate(raw, expected)
    sd = json.loads(Path("evidence/gm5-region-sd.json").read_text())
    if sd["sha256"] != PACKAGE_SHA or not (sd["readback_byte_identical"] and sd["safely_ejected"]):
        raise ValueError("SD copy does not match exact candidate")
    windows_check, windows = short_capture(Path(observation["patch_capture"]), "region-check", PATCH_WINDOWS)
    for address, _ in PATCH_WINDOWS:
        if windows[address] != expected[address-BASE:address-BASE+1024]:
            raise ValueError("Physical patch window differs from exact candidate")
    rom_check, rom = read_capture(observation["rom_capture"], ("security-flag",), 0x406B1800, 1024)
    ram_check, ram = read_capture(observation["ram_capture"], ("runtime-control",), 0x70A68400, 1024)
    settings_check, settings = read_capture(observation["settings_capture"], ("update-settings",), 0x7BFB0000, 18432)
    if rom != expected[0x6B1800:0x6B1C00] or struct.unpack_from("<H", rom, 0x3DC)[0] != 0:
        raise ValueError("ROM policy window differs")
    if struct.unpack_from("<H", ram, 0x90)[0] != 0 or settings[0x1B9] != 1:
        raise ValueError("RAM policy or saved-language shadow differs")
    language_check, language = short_capture(Path(observation["language_capture"]), "language-inspect", LANGUAGE_WINDOWS)
    for address, _ in LANGUAGE_WINDOWS[:3]:
        if language[address] != expected[address-BASE:address-BASE+1024]:
            raise ValueError("Language-inspection ROM guard differs from candidate")
    if language[0x701AF000][0x239] != 1:
        raise ValueError("Active UI language is not English")
    menu = language[0x70A0F000]
    rows = []
    for offset in range(0x150, 0x300, 8):
        ident, state = struct.unpack_from("<HB", menu, offset)
        if ident == 0xFFFF:
            break
        rows.append({"id": ident, "state": state})
    else:
        raise ValueError("Live language list lacks its bounded terminator")
    if {"id": 1, "state": 4} not in rows:
        raise ValueError("English is not available in the native language list")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Short physical verification of GM5 language patch and post-cycle English/policy state",
              "package": artifact(package), "expected_main_sha256": MAIN_SHA,
              "expected_main_hash_is_not_a_complete_physical_readback": True,
              "physical_patch_windows_match_exact_candidate": True, "physical_patch_window_bytes": 3072,
              "patches_verified": patches(original), "rom_policy": 0, "ram_policy": 0,
              "saved_language_shadow_id": settings[0x1B9], "active_ui_language_id": 1,
              "settings_mode": struct.unpack_from("<H", settings, 0x32E)[0],
              "region_word": hex(struct.unpack_from("<H", settings, 0x330)[0]),
              "live_language_entries": rows, "owner_observation": observation,
              "read_only_checks": {"patch_windows": windows_check, "rom": rom_check,
                                   "ram": ram_check, "settings": settings_check, "language": language_check},
              "post_update_host_policy_language_or_nor_writes": False,
              "complete_main_readback_performed": False,
              "collector_sha256": sha(Path(__file__).read_bytes()),
              "limits": ["Three patched ROM windows are verified; this is not a complete installed-main/NOR comparison.",
                         "Normal-mode installation, menu selection and manual off/on are owner observations.",
                         "Settings/UI language and ROM/RAM policy are packet-verified reads after that reported off/on."]}
    with output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    collect(args.observation, args.out)
    print("Verified three exact physical patch windows, English settings/UI and ROM/RAM policy zero.")


if __name__ == "__main__":
    main()
