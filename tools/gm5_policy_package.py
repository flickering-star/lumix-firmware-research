#!/usr/bin/env python3
"""Prepare/test a GM5 package with one installed-ROM policy byte changed to zero.

Host files and virtual NOR only. No camera transport, card copying or physical
installation is implemented. The original backup and other components are kept.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

from gm5_emulator import DEFAULT_BACKEND, put, word, run_scenario, sha
from gm5_prompt_package import KEY, artifact
from gm5_reflash_control import installed_decoder, save_json
from gm5_virtual_install import BACKUP, BACKUP_SHA, MAIN_SHA, BUFFER, SECTOR, INPUT, events, installed, scenario
from panasonic_upd import parse, PAYLOAD_START, TABLE_OFFSET, ENTRY_SIZE
from panasonic_v2_decode import OFFICIAL_HASHES

OFFICIAL = Path("firmware/official-gm5-v11/GM5__V11.bin")
CONTROL = Path("work/gm5-reflash-control-2")
LENGTH, PATCH, ADVERTISED = 0x800000, 0x6B1BDC, 0x0113


def patched(source: bytes) -> bytes:
    if len(source) != LENGTH or sha(source) != MAIN_SHA or source[PATCH:PATCH+2] != b"\1\0":
        raise ValueError("Expected the exact installed main and stock policy halfword one")
    result = bytearray(source)
    result[PATCH] = 0
    return bytes(result)


def validate(raw: bytes, expected_main: bytes) -> dict:
    entries = parse(raw, allow_unsigned=True)
    if len(entries) != 1 or len(raw) != PAYLOAD_START+LENGTH:
        raise ValueError("Policy control requires only the complete installed main program")
    entry = entries[0]
    expected = ("program", 0, LENGTH, 3, sha(expected_main), PAYLOAD_START)
    actual = (entry["name"], entry["destination_offset_candidate"], entry["size"],
              entry["flags_raw"], entry["field32_hex"], entry["file_offset"])
    if actual != expected:
        raise ValueError("Policy candidate component/destination/digest differs")
    if (raw[0x200] or raw[0x220:0x260] != bytes(64)
            or struct.unpack_from("<HH", raw, 0x1C) != (ADVERTISED, ADVERTISED)
            or any(raw[TABLE_OFFSET+ENTRY_SIZE:PAYLOAD_START])):
        raise ValueError("Policy candidate unsigned/header/directory scope differs")
    return entry


def build(output: Path) -> dict:
    _, main, _, flash = installed()
    wanted = patched(main)
    if flash[:LENGTH] != main:
        raise ValueError("Installed main differs from protected NOR backup")
    original = OFFICIAL.read_bytes()
    if sha(original) != OFFICIAL_HASHES["GM5"]:
        raise ValueError("Official template differs")
    source_entry = next(e for e in parse(original) if e["name"] == "program")
    prior = json.loads((CONTROL/"build-report.json").read_text())
    for name, field in (("codec", "codec"), ("original-decoder", "original_decoder")):
        if sha((CONTROL/name).read_bytes()) != prior[field]["sha256"]:
            raise ValueError("Retained verified cipher tool changed")
    if (len(prior["official_ciphertext_oracles"]) != 8
            or not all(e["official_ciphertext_byte_identical"] for e in prior["official_ciphertext_oracles"])):
        raise ValueError("Independent eight-component encoder oracle receipt missing")
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    for name in ("codec", "original-decoder", "codec-source.c", "original-decoder-source.c"):
        target = output/name
        target.write_bytes((CONTROL/name).read_bytes())
        target.chmod(0o500 if name in ("codec", "original-decoder") else 0o400)
    (output/"builder-source.py").write_bytes(Path(__file__).read_bytes())
    plain = output/"expected-patched-main.bin"
    plain.write_bytes(wanted)
    plain.chmod(0o400)
    encrypted = output/"encoded-main.data"
    subprocess.run([str((output/"codec").resolve()), "--encrypt", str(plain), str(encrypted), KEY,
                    source_entry["field16_hex"], "0", str(LENGTH)], check=True, capture_output=True, text=True)
    raw = bytearray(original[:PAYLOAD_START])+encrypted.read_bytes()
    raw[0x200] = 0
    raw[0x220:0x260] = bytes(64)
    struct.pack_into("<HH", raw, 0x1C, ADVERTISED, ADVERTISED)
    struct.pack_into("<I", raw, 0x3C, len(raw)-0x200)
    raw[0x2A0:0x2E0] = raw[:0x40]
    struct.pack_into("<I", raw, 0x2E8, 1)
    raw[TABLE_OFFSET:PAYLOAD_START] = bytes(PAYLOAD_START-TABLE_OFFSET)
    struct.pack_into("<12s4I32s16s16s", raw, TABLE_OFFSET,
                     b"program", PAYLOAD_START-0x200, LENGTH, 0, 3, hashlib.sha256(wanted).digest(),
                     bytes.fromhex(source_entry["field16_hex"]), bytes.fromhex(source_entry["reserved16_hex"]))
    struct.pack_into("<I", raw, 0x40, zlib.crc32(raw[0x200:]))
    entry = validate(bytes(raw), wanted)
    package = output/"GM5__V11.bin"
    package.write_bytes(raw)
    package.chmod(0o400)
    decoded = output/"original-decoder-main.data"
    subprocess.run([str((output/"original-decoder").resolve()), str(package), str(decoded), KEY,
                    entry["field16_hex"], str(PAYLOAD_START), str(LENGTH)],
                   check=True, capture_output=True, text=True)
    if decoded.read_bytes() != wanted:
        raise ValueError("Original decoder did not recover exact one-byte main patch")
    differences = [i for i, (before, after) in enumerate(zip(main, wanted)) if before != after]
    if differences != [PATCH] or main[0x6A0:0x6B0] != wanted[0x6A0:0x6B0]:
        raise ValueError("A byte outside the single policy initializer changed")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "One-byte persistent unsigned-policy candidate, based on exact installed GM5 main",
              "package": artifact(package), "component": entry, "backup_sha256": BACKUP_SHA,
              "original_main_sha256": MAIN_SHA, "patched_main_sha256": sha(wanted),
              "payload_byte_differences": [{"offset": hex(PATCH), "flash_address": hex(0x40000000+PATCH),
                                            "before": 1, "after": 0}],
              "installed_version_fields_unchanged": True,
              "advertised_container_halfwords": [hex(ADVERTISED)]*2,
              "components_excluded": [e["name"] for e in parse(original) if e["name"] != "program"],
              "requires_current_ram_policy_zero_for_installation": True,
              "expected_ram_policy_after_fresh_initialization": 0,
              "codec": artifact(output/"codec"), "original_decoder": artifact(output/"original-decoder"),
              "encoder_oracle_receipt": artifact(CONTROL/"build-report.json"),
              "original_decoder_roundtrip_exact": True,
              "builder_sha256": sha(Path(__file__).read_bytes()), "camera_contacted": False,
              "sd_card_written": False, "physical_installation_attempted": False,
              "physical_boot_and_recovery_validated": False}
    save_json(output/"build-report.json", report)
    return report


def install_spec(name: str, images: list[dict], main: bytes, flash: bytes,
                 decoded_path: Path, context_path: Path, *, fail=0, cut=0) -> dict:
    spec = scenario(name, images, main, sync=True)
    decoded = decoded_path.read_bytes()
    spec["images"].append({"path": str(decoded_path), "address": INPUT, "sha256": sha(decoded)})
    def jump(at: int, target: int) -> dict:
        return put(at, b"\xdc"+struct.pack("<i", target-at))
    spec["memory"] += [put(0x7BFB0000, flash[0x1FA0000:0x1FC0000]),
                       put(0x702C817C, flash[0x1FA4800:0x1FA6800]),
                       put(0x7BFD4800, flash[0x1FE0000:0x1FEC000]),
                       put(0x70020000, context_path.read_bytes()), word(0x70030004, 2),
                       word(0x700F0010, 0), word(0x700F001C, 0x70020000), word(0x70A68490, 0),
                       jump(0x7BD4FE14, 0x7BD4FE23), jump(0x7BD4FF0D, 0x7BD4FF17)]
    spec["registers"].update(pc=0x7BD4FD8A, a2=INPUT, a3=0x70030000)
    spec["stops"] = {"programming_finished": 0x7BD50074}
    spec["watchpoints"] = {"component_writer_return": 0x7BD50035}
    spec["nor"].update(fail_program=fail, cut_after=cut)
    spec["budget"], spec["trace_every"] = 500000000, 10000
    spec["dumps"] = [{"name": "post-job-input.data", "address": INPUT, "size": len(decoded)}]
    spec["assumptions"] += ["Exact native decoding output/context supplies post-decode job state.",
                             "Board/handshake call regions at 0x7bd4fe14/0x7bd4ff0d are bypassed; UI callbacks disabled.",
                             "Settings fixtures come from retained NOR, not a complete live RAM snapshot.",
                             "Stops after native programming loop; final cleanup/restart and full boot are not modeled."]
    return spec


def tests(package: Path, backend: Path, output: Path) -> dict:
    images, main, _, flash = installed()
    wanted = patched(main)
    raw = package.read_bytes()
    validate(raw, wanted)
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    for name in ("gm5_reflash_control.py", "gm5_virtual_install.py", "gm5_emulator.py", "panasonic_upd.py"):
        (output/name).write_bytes((Path("tools")/name).read_bytes())
    damaged = bytearray(raw); damaged[-1] ^= 1
    bad = output/"bad-crc.data"; bad.write_bytes(damaged)
    controls = []
    decoded_path = context_path = None
    for name, path, allowance, status in (("policy_decode_allowed", package, 1, 0),
                                          ("policy_decode_default_rejected", package, 0, 0x80000065),
                                          ("policy_decode_bad_crc", bad, 1, 0x80000064)):
        spec = installed_decoder(name, path, allowance, images)
        directory = output/name
        record = run_scenario(spec, backend, directory)
        if (record["result"]["stop"] != "returned"
                or int(record["result"]["registers"][0], 0) != status):
            raise ValueError(f"Policy decoder control failed: {name}: {record['result']}")
        decoded = (directory/"decoded-input.data").read_bytes()
        if not status:
            if decoded[PAYLOAD_START:] != wanted:
                raise ValueError("Native decoded policy payload differs from the exact one-byte main patch")
            decoded_path, context_path = directory/"decoded-input.data", directory/"context.bin"
        elif decoded != path.read_bytes():
            raise ValueError("Rejected policy package input changed")
        controls.append({"name": name, "execution": record, "expected_status": hex(status),
                         "host_compared_native_plaintext_to_exact_patch": not bool(status)})
        print(f"Passed {name}", flush=True)
    assert decoded_path and context_path
    decoded = decoded_path.read_bytes()
    successful = None
    expected_success = bytearray(flash); expected_success[:LENGTH] = wanted
    for name, fail, cut in (("policy_native_install", 0, 0),
                             ("policy_native_program_failure", 1, 0),
                             ("policy_native_power_cut", 0, 2)):
        spec = install_spec(name, images, main, flash, decoded_path, context_path, fail=fail, cut=cut)
        directory = output/name
        record = run_scenario(spec, backend, directory)
        stop = "nor_power_cut" if cut else "programming_finished"
        if record["result"]["stop"] != stop:
            raise ValueError(f"Unexpected policy programming stop: {record['result']}")
        if (directory/"post-job-input.data").read_bytes() != decoded:
            raise ValueError("Native job changed the policy package payload")
        expected = bytearray(flash)
        if fail or cut:
            expected[:SECTOR] = b"\xff"*SECTOR
            if cut: expected[:BUFFER] = wanted[:BUFFER]
        else:
            expected[:] = expected_success
        actual = (directory/"virtual-nor.bin").read_bytes()
        if actual != expected:
            raise ValueError("Complete policy NOR differs from the independent operation oracle")
        if actual[LENGTH:] != flash[LENGTH:]:
            raise ValueError("A component outside main, including calibration/settings, changed")
        committed = [e for e in events(directory) if e["event"] in ("erase_commit", "program_commit")]
        if any(not 0 <= int(e["offset"], 0) < LENGTH for e in committed):
            raise ValueError("A mutation command reached outside the main interval")
        statuses = [int(json.loads(line)["d0"], 0) for line in (directory/"trace.jsonl").read_text().splitlines()
                    if '"event":"watch"' in line]
        if not cut and statuses != ([0x8000000C] if fail else [0]):
            raise ValueError("Native main-component writer return sequence differs")
        stats = record["result"]["nor"]
        counts = (1, 1) if cut else (1, 0) if fail else (LENGTH//SECTOR, LENGTH//BUFFER)
        if (stats["erases"], stats["programs"], stats["zero_to_one_words"]) != (*counts, 0):
            raise ValueError("Native policy write counts differ")
        if not fail and not cut:
            erases = [int(e["offset"], 0) for e in committed if e["event"] == "erase_commit"]
            programs = [int(e["offset"], 0) for e in committed if e["event"] == "program_commit"]
            if erases != list(range(0, LENGTH, SECTOR)) or programs != list(range(0, LENGTH, BUFFER)):
                raise ValueError("Native main-sector/buffer coverage differs")
            if [i for i, (a, b) in enumerate(zip(flash, actual)) if a != b] != [PATCH]:
                raise ValueError("Complete virtual success changed more than the one policy byte")
            successful = directory/"virtual-nor.bin"
        controls.append({"name": name, "execution": record, "complete_readback_matches_operation_oracle": True,
                         "outside_main_unchanged": True, "settings_calibration_unchanged": True,
                         "all_mutation_commands_inside_main": True, "readback_detects_partial_write": bool(fail or cut),
                         "component_writer_returns": [hex(v) for v in statuses],
                         "exactly_one_policy_byte_changed_on_success": not bool(fail or cut)})
        print(f"Passed {name}", flush=True)
    assert successful
    for name, pc, stop, source, end, destination in (
            ("policy_programmed_key_initializer", 0x4000018F, 0x400001AD,
             0x643B7C, 0x64B5B8, 0x70000000),
            ("policy_programmed_policy_initializer", 0x40003000, 0x4000301E,
             0x64B5B8, 0x6DD76C, 0x70A01E6C)):
        spec = scenario(name, images, main, successful)
        spec["registers"]["pc"] = pc
        spec["stops"] = {"copy_finished": stop}
        spec["budget"] = 2000000
        spec["trace_every"] = 1000
        spec["dumps"] = [{"name": "initialized.data", "address": destination, "size": end-source}]
        spec["assumptions"].append("Native copy loops reload the encoded-and-programmed virtual NOR; hardware boot prefix is not executed.")
        directory = output/name
        record = run_scenario(spec, backend, directory)
        copied = (directory/"initialized.data").read_bytes()
        if record["result"]["stop"] != "copy_finished" or copied != wanted[source:end]:
            raise ValueError("Reloaded native initializer differs from programmed policy ROM")
        if (directory/"virtual-nor.bin").read_bytes() != expected_success:
            raise ValueError("Initializer modified the virtual NOR")
        item = {"name": name, "execution": record, "entire_initializer_matches_programmed_rom": True}
        if name.endswith("policy_initializer"):
            offset = 0x70A68490-destination
            if copied[offset:offset+2] != b"\0\0":
                raise ValueError("Programmed policy did not initialize RAM halfword zero")
            differences = [hex(destination+i) for i, (a, b) in enumerate(zip(main[source:end], copied)) if a != b]
            if differences != ["0x70a68490"]:
                raise ValueError("Policy initializer changed other RAM bytes")
            item.update(ram_policy_halfword=0, ram_differences_from_stock=differences)
        else:
            if copied[0x7950:0x7960].hex() != KEY:
                raise ValueError("The reloaded cipher key changed")
            item["cipher_key_unchanged"] = True
        controls.append(item)
        print(f"Passed {name}", flush=True)
    if sha(BACKUP.read_bytes()) != BACKUP_SHA or package.read_bytes() != raw:
        raise ValueError("Protected input changed")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Exact one-byte policy package: native decoding, virtual NOR and programmed-image initialization",
              "package": artifact(package), "patched_main_sha256": sha(wanted), "passed": len(controls),
              "controls": controls, "driver_sha256": sha(Path(__file__).read_bytes()),
              "backup_sha256": BACKUP_SHA, "backup_unchanged": True,
              "camera_contacted": False, "physical_flash_written": False,
              "limits": ["Explicit board/handshake/RTOS/cache abstractions remain; this is not a complete machine or physical write test.",
                         "Native unsigned decoding skips SHA verification; the host compares every decoded byte with the exact expected patch.",
                         "Copy-loop initialization establishes flag behavior, not full boot or absence of additional boot authentication.",
                         "The main program includes boot code; programming it spans 64 sectors despite a one-byte intended difference.",
                         "Physical recovery has not been validated. The prepared candidate has not been copied or installed."]}
    save_json(output/"summary.json", report)
    return report


def publish(build_dir: Path, native_dir: Path, output: Path) -> dict:
    built = json.loads((build_dir/"build-report.json").read_text())
    native = json.loads((native_dir/"summary.json").read_text())
    if (built["package"] != native["package"] or native["passed"] != 8 or len(native["controls"]) != 8
            or built["builder_sha256"] != native["driver_sha256"]):
        raise ValueError("Policy build/test receipts differ")
    if (sha((build_dir/"builder-source.py").read_bytes()) != built["builder_sha256"]
            or sha((native_dir/"driver-source.py").read_bytes()) != native["driver_sha256"]):
        raise ValueError("Policy source snapshots changed")
    _, main, _, flash = installed()
    wanted = patched(main)
    expected = bytearray(flash); expected[:LENGTH] = wanted
    package = Path(built["package"]["path"])
    if sha(package.read_bytes()) != built["package"]["sha256"]:
        raise ValueError("Encoded policy package changed")
    validate(package.read_bytes(), wanted)
    backend = Path("work/gm5-emulator-nor-release-backend/gm5-mn103-sim")
    backend_sha = sha(backend.read_bytes())
    for case in native["controls"]:
        directory = native_dir/case["name"]
        record = case["execution"]
        if json.loads((directory/"report.json").read_text()) != record or record["backend"]["sha256"] != backend_sha:
            raise ValueError("Original native execution receipt/backend differs")
        for filename, field in (("scenario.json", "scenario_sha256"), ("trace.jsonl", "trace_sha256")):
            if sha((directory/filename).read_bytes()) != record[field]:
                raise ValueError("Policy native scenario/trace changed")
        if "nor_source" in record:
            actual = (directory/"virtual-nor.bin").read_bytes()
            if sha(actual) != record["nor_output_sha256"] or sha((directory/"nor-events.jsonl").read_bytes()) != record["nor_event_sha256"]:
                raise ValueError("Policy virtual image/command transcript changed")
            if case["name"] == "policy_native_install" or case["name"].startswith("policy_programmed_"):
                if actual != expected: raise ValueError("Complete policy success image differs")
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(), "build": built, "native": native,
              "retained_backend": artifact(backend), "publisher_sha256": sha(Path(__file__).read_bytes()),
              "physical_test_prepared_only": True, "sd_card_written": False, "camera_contacted": False,
              "next_physical_proof": ["Install this exact package only after separate physical-test readiness.",
                                      "After completed update, perform a normal power-off/on before reading policy; send no USB policy write.",
                                      "Verify ROM0x406b1bdc is zero, RAM0x70a68490 initializes to zero, and main readback matches the expected one-byte-patched hash.",
                                      "Successful flash readback and persistence distinguish this from the unchanged control."]}
    save_json(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "test", "publish"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--backend", type=Path, default=DEFAULT_BACKEND)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--native-dir", type=Path)
    args = parser.parse_args()
    if args.action == "build":
        result = build(args.out)
        print(f"Prepared exact one-byte policy package {result['package']['sha256']}")
    elif args.action == "test":
        if args.package is None: parser.error("test requires --package")
        result = tests(args.package, args.backend, args.out)
        print(f"Passed {result['passed']} exact-policy-package native controls")
    else:
        if args.build_dir is None or args.native_dir is None: parser.error("publish requires --build-dir and --native-dir")
        publish(args.build_dir, args.native_dir, args.out)
        print("Published verified one-byte policy-package evidence")


if __name__ == "__main__":
    main()
