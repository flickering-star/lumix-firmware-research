#!/usr/bin/env python3
"""Prepare and validate the three-byte Japanese-language unlock package offline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

from gm5_emulator import DEFAULT_BACKEND, sha, run_scenario
from gm5_policy_package import install_spec
from gm5_prompt_package import KEY, artifact
from gm5_reflash_control import installed_decoder, save_json
from gm5_region_emulator import MAIN, MAIN_SHA, SECONDARY, SECONDARY_SHA, candidate, inputs, patches
from gm5_region_persistence import boot
from panasonic_upd import parse, PAYLOAD_START, TABLE_OFFSET, ENTRY_SIZE
from panasonic_v2_decode import OFFICIAL_HASHES

LENGTH, ADVERTISED = 0x800000, 0x0114
TOOLS = Path("work/gm5-policy-zero-1")


def validate(raw: bytes, wanted: bytes) -> dict:
    entries = parse(raw, allow_unsigned=True)
    if len(entries) != 1 or len(raw) != LENGTH+PAYLOAD_START:
        raise ValueError("Region package must contain only the complete main")
    entry = entries[0]
    if (entry["name"], entry["destination_offset_candidate"], entry["size"], entry["flags_raw"],
            entry["file_offset"], entry["field32_hex"]) != ("program", 0, LENGTH, 3, PAYLOAD_START, sha(wanted)):
        raise ValueError("Region package component scope/digest differs")
    if (struct.unpack_from("<HH", raw, 0x1C) != (ADVERTISED, ADVERTISED)
            or raw[0x200] or raw[0x220:0x260] != bytes(64)
            or any(raw[TABLE_OFFSET+ENTRY_SIZE:PAYLOAD_START])):
        raise ValueError("Region package metadata differs")
    return entry


def build(output: Path) -> dict:
    main, _, flash = inputs(); wanted = candidate(main)
    original_path = Path("firmware/official-gm5-v11/GM5__V11.bin")
    original = original_path.read_bytes()
    if sha(original) != OFFICIAL_HASHES["GM5"]: raise ValueError("Official template differs")
    old = json.loads((TOOLS/"build-report.json").read_text())
    output.mkdir(parents=True, exist_ok=False); output.chmod(0o700)
    for name, field in (("codec", "codec"), ("original-decoder", "original_decoder")):
        source = TOOLS/name
        if sha(source.read_bytes()) != old[field]["sha256"]: raise ValueError("Retained verified codec changed")
        (output/name).write_bytes(source.read_bytes()); (output/name).chmod(0o500)
    for name in ("codec-source.c", "original-decoder-source.c"):
        (output/name).write_bytes((TOOLS/name).read_bytes())
    (output/"builder-source.py").write_bytes(Path(__file__).read_bytes())
    (output/"region-source.py").write_bytes(Path("tools/gm5_region_emulator.py").read_bytes())
    plain = output/"expected-region-main.bin"; plain.write_bytes(wanted); plain.chmod(0o400)
    encrypted = output/"encoded-main.data"
    entry = next(e for e in parse(original) if e["name"] == "program")
    subprocess.run([str((output/"codec").resolve()), "--encrypt", str(plain), str(encrypted), KEY,
                    entry["field16_hex"], "0", str(LENGTH)], check=True, capture_output=True, text=True)
    raw = bytearray(original[:PAYLOAD_START])+encrypted.read_bytes()
    raw[0x200] = 0;raw[0x220:0x260] = bytes(64)
    struct.pack_into("<HH", raw, 0x1C, ADVERTISED, ADVERTISED)
    struct.pack_into("<I", raw, 0x3C, len(raw)-0x200)
    raw[0x2A0:0x2E0] = raw[:0x40]
    struct.pack_into("<I", raw, 0x2E8, 1)
    raw[TABLE_OFFSET:PAYLOAD_START] = bytes(PAYLOAD_START-TABLE_OFFSET)
    struct.pack_into("<12s4I32s16s16s", raw, TABLE_OFFSET, b"program", PAYLOAD_START-0x200,
                     LENGTH, 0, 3, hashlib.sha256(wanted).digest(), bytes.fromhex(entry["field16_hex"]),
                     bytes.fromhex(entry["reserved16_hex"]))
    struct.pack_into("<I", raw, 0x40, zlib.crc32(raw[0x200:]))
    parsed = validate(bytes(raw), wanted)
    package = output/"GM5__V11.bin";package.write_bytes(raw);package.chmod(0o400)
    decoded = output/"original-decoder-main.data"
    subprocess.run([str((output/"original-decoder").resolve()), str(package), str(decoded), KEY,
                    parsed["field16_hex"], str(PAYLOAD_START), str(LENGTH)],
                   check=True, capture_output=True, text=True)
    if decoded.read_bytes() != wanted: raise ValueError("Original decoder did not recover the exact region patch")
    baseline = bytearray(flash);baseline[:LENGTH] = main
    source = output/"virtual-current-nor.bin";source.write_bytes(baseline);source.chmod(0o400)
    region_evidence = Path("evidence/gm5-region-language-lock-v2.json")
    proof = json.loads(region_evidence.read_text())
    if proof["candidate_main_sha256"] != sha(wanted) or len(proof["patches"]) != 3:
        raise ValueError("Completed region/visibility proof does not match this candidate")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Japanese language selection/normalization unlock; current installed policy-zero main",
              "package": artifact(package), "component": parsed, "plaintext_sha256": sha(wanted),
              "current_main": artifact(MAIN), "patches": patches(main),
              "existing_policy_zero_retained": wanted[0x6B1BDC] == 0,
              "actual_version_fields_unchanged": wanted[0x6A0:0x6B0] == main[0x6A0:0x6B0],
              "original_decoder_roundtrip_exact": True,
              "virtual_current_nor": artifact(source), "original_settings_fixture": "Original retained NOR; no current physical settings claim",
              "native_region_evidence": artifact(region_evidence),
              "builder_sha256": sha(Path(__file__).read_bytes()),
              "region_helper_sha256": sha(Path("tools/gm5_region_emulator.py").read_bytes()),
              "camera_contacted": False, "sd_card_written": False, "physical_region_update_performed": False}
    save_json(output/"build-report.json", report)
    return report


def tests(build_dir: Path, output: Path, backend: Path) -> dict:
    main, _, flash = inputs(); wanted = candidate(main)
    built = json.loads((build_dir/"build-report.json").read_text())
    package = Path(built["package"]["path"]);raw = package.read_bytes()
    if sha(raw) != built["package"]["sha256"]: raise ValueError("Encoded candidate changed")
    validate(raw, wanted)
    source = Path(built["virtual_current_nor"]["path"])
    current = source.read_bytes()
    if sha(current) != built["virtual_current_nor"]["sha256"] or current[:LENGTH] != main:
        raise ValueError("Current virtual source differs")
    images = [{"path": str(MAIN), "address": 0x40000000, "sha256": MAIN_SHA},
              {"path": str(SECONDARY), "address": 0x7BC00000, "sha256": SECONDARY_SHA}]
    output.mkdir(parents=True, exist_ok=False);output.chmod(0o700)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    for name in ("gm5_region_emulator.py", "gm5_region_persistence.py", "gm5_policy_package.py", "gm5_reflash_control.py"):
        (output/name).write_bytes((Path("tools")/name).read_bytes())
    controls = []
    decoded_path = context_path = None
    for name, allowance, status in (("region_decode_allowed", 1, 0), ("region_decode_default_rejected", 0, 0x80000065)):
        spec = installed_decoder(name, package, allowance, images)
        directory = output/name;record = run_scenario(spec, backend, directory)
        if record["result"]["stop"] != "returned" or int(record["result"]["registers"][0], 0) != status:
            raise ValueError(f"Exact region package decoding failed: {record['result']}")
        after = (directory/"decoded-input.data").read_bytes()
        if not status:
            if after[PAYLOAD_START:] != wanted: raise ValueError("Native region plaintext differs")
            decoded_path, context_path = directory/"decoded-input.data", directory/"context.bin"
        elif after != raw: raise ValueError("Rejected native package was modified")
        controls.append({"name": name, "execution": record, "expected_status": hex(status),
                         "host_exact_plaintext_check": not bool(status)})
        print(f"Passed {name}", flush=True)
    assert decoded_path and context_path
    target = bytearray(current);target[:LENGTH] = wanted
    success = None
    for name, failure, cut in (("region_native_install", 0, 0), ("region_program_error", 1, 0), ("region_power_cut", 0, 2)):
        spec = install_spec(name, images, main, flash, decoded_path, context_path, fail=failure, cut=cut)
        spec["nor"].update(path=str(source), sha256=sha(current))
        directory = output/name;record = run_scenario(spec, backend, directory)
        stop = "nor_power_cut" if cut else "programming_finished"
        if record["result"]["stop"] != stop: raise ValueError(f"Unexpected region installation stop: {record['result']}")
        expected = bytearray(current)
        if failure or cut:
            expected[:0x20000] = b"\xff"*0x20000
            if cut: expected[:1024] = wanted[:1024]
        else: expected[:] = target
        actual = (directory/"virtual-nor.bin").read_bytes()
        if actual != expected: raise ValueError("Full region virtual NOR differs from independent operation oracle")
        counts = (1, 1) if cut else (1, 0) if failure else (64, 8192)
        stats = record["result"]["nor"]
        if (stats["erases"], stats["programs"], stats["zero_to_one_words"]) != (*counts, 0):
            raise ValueError("Region native write plan differs")
        if not failure and not cut:
            diffs = [i for i, (a, b) in enumerate(zip(current, actual)) if a != b]
            if diffs != sorted(p["offset"] for p in patches(main)): raise ValueError("Virtual install changed another byte")
            success = directory/"virtual-nor.bin"
        controls.append({"name": name, "execution": record, "complete_image_matches_operation_oracle": True,
                         "outside_main_and_settings_calibration_unchanged": actual[LENGTH:] == current[LENGTH:],
                         "exact_three_language_byte_changes_on_success": not bool(failure or cut)})
        print(f"Passed {name}", flush=True)
    assert success
    name = "region_programmed_settings_boot"
    record = boot(name, success, main, output/name, backend)
    if record["result"]["stop"] != "boot_language_initialized":
        raise ValueError("Native language startup failed from exact programmed package")
    ram = (output/name/"ram.data").read_bytes()
    menu = ram[0xA0F150:0xA0F150+192]
    ids = []
    for at in range(0, len(menu), 8):
        ident = struct.unpack_from("<H", menu, at)[0]
        if ident == 65535: break
        ids.append(ident)
    if len(ids) != 23 or not {0, 1}.issubset(ids) or ram[0xA68490] != 0 or ram[0xA0E912] != 4:
        raise ValueError("Programmed image did not expose English/Japanese and retain policy0")
    controls.append({"name": name, "execution": record, "menu_ids": ids, "existing_policy_zero_preserved": True,
                     "language_setup_item_visible": True, "source_is_exact_decoded_and_programmed_candidate": True})
    print(f"Passed {name}", flush=True)
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(), "passed": len(controls),
              "scope": "Exact encoded region candidate: native decoder, virtual installation, settings load and language startup",
              "package": built["package"], "controls": controls,
              "candidate_main_sha256": sha(wanted), "driver_sha256": sha(Path(__file__).read_bytes()),
              "camera_contacted": False, "physical_region_update_performed": False,
              "limits": ["Existing explicit board/RTOS/cache/NOR assumptions remain; no physical region update has been attempted.",
                         "This package changes language lists for region0x100; regional identity, video rules and calibration stay outside scope."]}
    save_json(output/"summary.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "test"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--backend", type=Path, default=DEFAULT_BACKEND)
    args = parser.parse_args()
    if args.action == "build":
        report = build(args.out);print(f"Prepared region candidate {report['package']['sha256']}")
    else:
        if args.build_dir is None: parser.error("test requires --build-dir")
        report = tests(args.build_dir, args.out, args.backend);print(f"Passed {report['passed']} exact-region-package controls")


if __name__ == "__main__":
    main()
