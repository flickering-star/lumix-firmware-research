#!/usr/bin/env python3
"""Verify saved physical GM5 policy-change evidence and full main readback.

Offline collector only: no camera transport or writes. Requires completed
packet-verified capture files, the exact candidate and the protected backup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct

from gm1_capture_verify import request, verify_capture, wire
from gm5_emulator import sha
from gm5_policy_package import PATCH, LENGTH, patched, validate
from gm5_prompt_package import artifact
from gm5_reflash_control import save_json
from gm5_virtual_install import BACKUP, BACKUP_SHA

PACKAGE_SHA = "86832e6eafa90b453894237805dafe128f61d346066f73a3752a8071d8286f16"
MAIN_SHA = "c918553771018e171605ecb1f177a4d64bc94b221fe5304b8ff419f4509d208d"


def read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def read_capture(path: str | Path, mode: tuple[str, ...], base: int, size: int) -> tuple[dict, bytes]:
    checked = verify_capture(Path(path))
    if (not checked["complete"] or checked["errors"] or checked["model"] != "DMC-GM5"
            or checked["mode"] not in mode or int(checked["program_file_base"], 16) != base
            or checked["verified_prefix_bytes"] != size):
        raise ValueError("Physical proof needs a complete capture of the exact GM5 interval")
    data = Path(checked["program_file"]).read_bytes()
    if len(data) != size or sha(data) != checked["program_sha256"]:
        raise ValueError("Physical capture file changed after packet replay")
    return checked, data


def preparation_audit(arm: dict) -> dict:
    directory = Path(arm["ram_capture"])/"result"
    raw = (directory/"events.jsonl").read_bytes()
    if sha(raw) != arm["ram_events_sha256"]:
        raise ValueError("Original RAM preparation transcript changed")
    writes = 0
    reads = 0
    for event in (json.loads(line) for line in raw.splitlines()):
        if event["event"] != "bulk_out_attempt":
            continue
        packet = wire(event)
        if len(packet) == 16 and packet[3] == 0x9C:
            if packet.hex() != "0800ff9c9084a670000000000000c500":
                raise ValueError("Preparation contains a different write than the fixed RAM policy zero")
            writes += 1
        else:
            request(packet, "DMC-GM5")
            reads += 1
    if writes != 1 or arm["ram_flag_before"] != 1 or arm["ram_flag_after"] != 0:
        raise ValueError("Expected one guarded pre-installation RAM policy change")
    return {"fixed_ram_writes": writes, "other_outgoing_requests_are_reads": True,
            "read_requests": reads, "write_address": "0x70a68490",
            "host_nor_programming_request_present": False, "transcript_sha256": sha(raw)}


def collect(main_capture: Path, output: Path) -> dict:
    backup = BACKUP.read_bytes()
    if len(backup) != 0x2000000 or sha(backup) != BACKUP_SHA:
        raise ValueError("Protected original NOR backup changed")
    expected = patched(backup[:LENGTH])
    if sha(expected) != MAIN_SHA:
        raise ValueError("Expected one-byte main hash differs")
    package = Path("work/gm5-policy-zero-1/GM5__V11.bin")
    raw = package.read_bytes()
    if sha(raw) != PACKAGE_SHA:
        raise ValueError("Exact installed-test candidate changed")
    validate(raw, expected)
    sd = read_json("evidence/gm5-policy-zero-sd.json")
    arm = read_json("evidence/gm5-policy-zero-arm.json")
    if (sd["sha256"] != PACKAGE_SHA or arm["package_sha256"] != PACKAGE_SHA
            or not sd["readback_byte_identical"] or not sd["safely_ejected"]):
        raise ValueError("Prepared card and armed candidate do not agree")
    audit = preparation_audit(arm)
    before = read_json("evidence/gm5-policy-zero-before-rom.json")
    before_check, before_rom = read_capture(before["capture"], ("security-flag",), 0x406B1800, 1024)
    if before_rom != backup[0x6B1800:0x6B1C00] or struct.unpack_from("<H", before_rom, 0x3DC)[0] != 1:
        raise ValueError("Immediate physical pre-update ROM policy is not the original one")
    first_rom = read_json("evidence/gm5-policy-zero-first-rom-read.json")
    rom_check, rom = read_capture(first_rom["capture"]["capture"], ("security-flag",), 0x406B1800, 1024)
    wanted_rom = bytearray(before_rom); wanted_rom[0x3DC] = 0
    if rom != wanted_rom or struct.unpack_from("<H", rom, 0x3DC)[0] != 0:
        raise ValueError("Post-update physical ROM differs from the precise expected policy change")
    first = read_json("evidence/gm5-policy-zero-first-flash-proof.json")
    ram_check, ram = read_capture(first["ram_capture"]["capture"], ("runtime-control",), 0x70A68400, 1024)
    if struct.unpack_from("<H", ram, 0x90)[0] != 0:
        raise ValueError("Post-update RAM policy is not zero")
    cycle = read_json("evidence/gm5-policy-zero-power-cycle.json")
    if (cycle["owner_confirmation"] != "I also did a normal off/on cycle"
            or not cycle["persistence_across_owner_reported_normal_off_on_verified"]
            or cycle["post_restart_host_ram_or_nor_writes"]):
        raise ValueError("Normal power-cycle persistence evidence is missing")
    main_check, actual = read_capture(main_capture, ("program", "resume"), 0x40000000, LENGTH)
    if actual != expected or sha(actual) != MAIN_SHA:
        raise ValueError(f"Complete physical main does not match the one-byte-patched candidate: {sha(actual)}")
    differences = [i for i, (before_byte, after_byte) in enumerate(zip(backup[:LENGTH], actual))
                   if before_byte != after_byte]
    if differences != [PATCH] or actual[0x6A0:0x6B0] != backup[0x6A0:0x6B0]:
        raise ValueError("Physical main has another difference or a changed installed version")
    Path(main_check["program_file"]).chmod(0o400)
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Physical modified GM5 main installation, exact readback and normal-power-cycle policy persistence",
              "model": "DMC-GM5", "package": artifact(package),
              "expected_main_sha256": MAIN_SHA, "actual_main_sha256": sha(actual),
              "main_readback_bytes": len(actual), "main_byte_identical_to_candidate_plaintext": True,
              "differences_from_original_main": [{"offset": hex(PATCH), "flash_address": hex(0x40000000+PATCH),
                                                  "before": 1, "after": 0}],
              "version_halfwords_unchanged": [hex(v) for v in struct.unpack_from("<HH", actual, 0x6A0)],
              "rom_policy_before": 1, "rom_policy_after": 0, "ram_policy_after_normal_power_cycle": 0,
              "owner_update_observation": first_rom["owner_report"], "owner_power_cycle_confirmation": cycle,
              "preparation_request_audit": audit,
              "read_only_capture_checks": {"before_rom": before_check, "after_rom": rom_check,
                                           "after_ram": ram_check, "complete_main": main_check},
              "original_backup": artifact(BACKUP), "original_backup_unchanged": True,
              "native_candidate_evidence": artifact(Path("evidence/gm5-policy-zero-package.json")),
              "sd_preparation_evidence": artifact(Path("evidence/gm5-policy-zero-sd.json")),
              "arm_evidence": artifact(Path("evidence/gm5-policy-zero-arm.json")),
              "collector_sha256": sha(Path(__file__).read_bytes()),
              "verified": {"modified_unsigned_sd_main_installation": True,
                           "complete_8MiB_main_matches_exact_candidate": True,
                           "persistent_rom_and_ram_policy_zero": True,
                           "post_update_measurement_transfers_are_read_only": True},
              "limits": ["This confirms this connected GM5/build and exact candidate, not all firmware variants or arbitrary patches.",
                         "The complete 32 MiB NOR and other independent storage were not reread after this test; no full physical calibration comparison is claimed.",
                         "Normal off/on is an owner observation; the ROM/RAM values and complete main are packet-verified service reads.",
                         "No external recovery programmer has been validated, and broader camera-function testing is outside this proof."]}
    save_json(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-capture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.main_capture, args.out)
    print(f"Verified physical main {report['actual_main_sha256']}: exactly one ROM byte changed; policy persists as zero")


if __name__ == "__main__":
    main()
