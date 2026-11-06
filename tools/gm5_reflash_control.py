#!/usr/bin/env python3
"""Prepare and test an unchanged-installed-program2 GM5 reflash control offline.

The scope is deliberately fixed to this camera's verified backup. No USB, SD
copying, RAM writes or physical installation is implemented by this tool.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

from gh2_debug_verify import checked_disassembly
from gm5_emulator import DEFAULT_BACKEND, base_scenario, decoder_scenario, put, word, run_scenario, sha
from gm5_prompt_package import KEY, PUBLIC, artifact
from gm5_virtual_install import BACKUP, BACKUP_SHA, BUFFER, INPUT, SECTOR, SECONDARY_SHA, events, installed, scenario
from panasonic_signature_verify import verify as verify_signature
from panasonic_upd import parse, PAYLOAD_START, TABLE_OFFSET, ENTRY_SIZE
from panasonic_v2_decode import OFFICIAL_HASHES

OFFICIAL = Path("firmware/official-gm5-v11/GM5__V11.bin")
DECODED = Path("work/gm5-v11-decoded-verified")
DESTINATION, LENGTH, ADVERTISED = 0x1400000, 0x360000, 0x0112


def assemble(template: bytes, plaintext: bytes, ciphertext: bytes) -> bytes:
    """Accept only the pinned official template and this installed component."""
    if sha(template) != OFFICIAL_HASHES["GM5"]:
        raise ValueError("Official GM5 template differs")
    if len(plaintext) != LENGTH or sha(plaintext) != SECONDARY_SHA:
        raise ValueError("Expected unchanged installed program2")
    if len(ciphertext) != LENGTH:
        raise ValueError("Ciphertext length differs")
    entry = next(e for e in parse(template) if e["name"] == "program2")
    if (entry["size"], entry["destination_offset_candidate"], entry["flags_raw"]) != (LENGTH, DESTINATION, 3):
        raise ValueError("Official program2 geometry differs")
    result = bytearray(template[:PAYLOAD_START]) + ciphertext
    result[0x200] = 0
    result[0x220:0x260] = bytes(64)  # Explicitly unsigned; no reused signature.
    struct.pack_into("<HH", result, 0x1C, ADVERTISED, ADVERTISED)
    struct.pack_into("<I", result, 0x3C, len(result)-0x200)
    result[0x2A0:0x2E0] = result[:0x40]
    struct.pack_into("<I", result, 0x2E8, 1)
    result[TABLE_OFFSET:PAYLOAD_START] = bytes(PAYLOAD_START-TABLE_OFFSET)
    struct.pack_into("<12s4I32s16s16s", result, TABLE_OFFSET,
                     b"program2", PAYLOAD_START-0x200, LENGTH, DESTINATION, 3,
                     hashlib.sha256(plaintext).digest(), bytes.fromhex(entry["field16_hex"]),
                     bytes.fromhex(entry["reserved16_hex"]))
    struct.pack_into("<I", result, 0x40, zlib.crc32(result[0x200:]))
    validate_scope(bytes(result))
    return bytes(result)


def validate_scope(raw: bytes) -> dict:
    entries = parse(raw, allow_unsigned=True)
    if len(entries) != 1:
        raise ValueError("Control must contain exactly one component")
    entry = entries[0]
    expected = ("program2", DESTINATION, LENGTH, 3, SECONDARY_SHA, PAYLOAD_START)
    actual = (entry["name"], entry["destination_offset_candidate"], entry["size"],
              entry["flags_raw"], entry["field32_hex"], entry["file_offset"])
    if actual != expected or len(raw) != PAYLOAD_START+LENGTH:
        raise ValueError("Component differs from the fixed installed-program2 scope")
    if struct.unpack_from("<HH", raw, 0x1C) != (ADVERTISED, ADVERTISED):
        raise ValueError("Advertised version differs")
    if raw[0x200] or raw[0x220:0x260] != bytes(64):
        raise ValueError("Expected explicit unsigned marker/signature")
    if any(raw[TABLE_OFFSET+ENTRY_SIZE:PAYLOAD_START]):
        raise ValueError("Unused directory entries must be empty")
    if DESTINATION % SECTOR or LENGTH % SECTOR or LENGTH % BUFFER:
        raise ValueError("Whole sectors and 1 KiB programming buffers are required")
    return entry


def save_json(path: Path, data: dict) -> None:
    with path.open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def build(codec: Path, decoder: Path, output: Path) -> dict:
    images, main, secondary, flash = installed()
    template = OFFICIAL.read_bytes()
    if sha(template) != OFFICIAL_HASHES["GM5"]:
        raise ValueError("Official template differs")
    entries = parse(template)
    if not verify_signature(PUBLIC, hashlib.sha256(template[0x2A0:0x2A0+76+92*len(entries)]).digest(),
                            template[0x220:0x260]):
        raise ValueError("Official directory authentication failed")
    if secondary != flash[DESTINATION:DESTINATION+LENGTH]:
        raise ValueError("Installed program2 differs from the complete backup")
    if struct.unpack_from("<HH", main, 0x6A0) != (0x0111, 0x0111):
        raise ValueError("Installed version control differs")
    if main[0x64B4CC:0x64B4DC].hex() != KEY:
        raise ValueError("Installed cipher key differs")
    prior = json.loads((DECODED/"decode-report.json").read_text())
    if (sha(decoder.read_bytes()) != prior["decoder"]["sha256"]
            or sha((DECODED/"decoder-source.c").read_bytes()) != prior["decoder_source"]["sha256"]):
        raise ValueError("Original decoder must match the retained official-decoding receipt")
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    for source, name in ((codec, "codec"), (decoder, "original-decoder"),
                         (Path("tools/panasonic_aes5.c"), "codec-source.c"),
                         (DECODED/"decoder-source.c", "original-decoder-source.c"),
                         (Path(__file__), "builder-source.py")):
        target = output/name
        target.write_bytes(source.read_bytes())
        target.chmod(0o500 if name in ("codec", "original-decoder") else 0o400)
    codec, decoder = (output/"codec").resolve(), (output/"original-decoder").resolve()
    selftest = subprocess.check_output([str(codec), "--selftest"], text=True).strip()
    oracles = []
    with tempfile.TemporaryDirectory(prefix="oracle-", dir=output) as temporary:
        directory = Path(temporary)
        for entry in entries:
            source = DECODED/f"{entry['index']:02d}_{entry['name']}.decoded.bin"
            plaintext = source.read_bytes()
            if len(plaintext) != entry["size"] or sha(plaintext) != entry["field32_hex"]:
                raise ValueError("Official decoded oracle differs")
            encoded = directory/(entry["name"]+".data")
            subprocess.run([str(codec), "--encrypt", str(source), str(encoded), KEY,
                            entry["field16_hex"], "0", str(len(plaintext))],
                           check=True, capture_output=True, text=True)
            wanted = template[entry["file_offset"]:entry["file_offset"]+entry["size"]]
            if encoded.read_bytes() != wanted:
                raise ValueError(f"Encoder does not reproduce official {entry['name']} ciphertext")
            oracles.append({"name": entry["name"], "bytes": len(wanted),
                            "plaintext_sha256": sha(plaintext), "ciphertext_sha256": sha(wanted),
                            "official_ciphertext_byte_identical": True})
            print(f"Official ciphertext reproduced: {entry['name']}", flush=True)
        entry = next(e for e in entries if e["name"] == "program2")
        encoded = directory/"installed-program2.data"
        subprocess.run([str(codec), "--encrypt", images[1]["path"], str(encoded), KEY,
                        entry["field16_hex"], "0", str(LENGTH)], check=True, capture_output=True, text=True)
        raw = assemble(template, secondary, encoded.read_bytes())
    package = output/"GM5__V11.bin"
    package.write_bytes(raw)
    package.chmod(0o400)
    entry = validate_scope(raw)
    roundtrip = output/"host-decoded-program2.data"
    # Use the retained pre-encoder decoder, rather than only a codec round trip.
    subprocess.run([str(decoder), str(package), str(roundtrip), KEY, entry["field16_hex"],
                    str(PAYLOAD_START), str(LENGTH)], check=True, capture_output=True, text=True)
    if roundtrip.read_bytes() != secondary:
        raise ValueError("Original independent decoder did not recover the exact installed bytes")
    signed_end = 0x2A0+76+92
    if verify_signature(PUBLIC, hashlib.sha256(raw[0x2A0:signed_end]).digest(), raw[0x220:0x260]):
        raise ValueError("Unsigned control unexpectedly authenticates")
    report = {"schema": 1, "scope": "Offline unchanged-installed-program2 reflash control",
              "package": artifact(package), "component": entry,
              "backup": artifact(BACKUP), "official_template": artifact(OFFICIAL),
              "installed_plaintext_sha256": SECONDARY_SHA, "plaintext_byte_identical_to_backup": True,
              "original_decoder_roundtrip_byte_identical": True, "official_ciphertext_oracles": oracles,
              "codec": artifact(codec), "original_decoder": artifact(decoder), "codec_selftest": selftest,
              "builder_sha256": sha(Path(__file__).read_bytes()),
              "advertised_halfwords": [hex(ADVERTISED)]*2, "installed_version_bytes_unchanged": True,
              "signature_valid": False, "required_unsigned_allowance": 1,
              "nor_range": {"offset": hex(DESTINATION), "end_exclusive": hex(DESTINATION+LENGTH),
                            "sectors": LENGTH//SECTOR, "program_buffers": LENGTH//BUFFER},
              "excluded": [e["name"] for e in entries if e["name"] != "program2"],
              "camera_contacted": False, "sd_card_written": False, "physical_flash_written": False,
              "native_validation_complete": False, "virtual_programming_complete": False}
    report["retained_sources"] = [artifact(output/name) for name in
                                  ("builder-source.py", "codec-source.c", "original-decoder-source.c")]
    save_json(output/"build-report.json", report)
    return report


def installed_decoder(name: str, path: Path, allowance: int, images: list[dict]) -> dict:
    spec = decoder_scenario(name, path, allowance, path.stat().st_size)
    spec["images"][:2] = copy.deepcopy(images)
    stub, ctx = 0x70008000, 0x70020000
    code = b"\xdd"+struct.pack("<i", 0x7BD4ED0E-stub)+bytes([0xF0, 36])
    code += b"\xfc\xdc"+struct.pack("<I", ctx)+b"\x95\0"
    position = stub+len(code)
    code += b"\xdd"+struct.pack("<i", 0x7BD4EE4E-position)+bytes([0x30, 12, 0xFF])
    spec["memory"][0] = put(stub, code)
    spec["memory"].append(word(ctx+108, 0x7BE2A770))
    return spec


def startup_test(images: list[dict], main: bytes, secondary: bytes, backend: Path,
                 decoder: Path, output: Path) -> dict:
    regions = []
    for start, end in ((0x40000030, 0x40000035), (0x4001E801, 0x4001E807),
                       (0x4001E8EE, 0x4001E924)):
        disassembly, count = checked_disassembly(Path(images[0]["path"]), main, decoder,
                                                0x40000000, start, end)
        regions.append({"start": hex(start), "end_exclusive": hex(end), "instructions": count,
                        "bytes_sha256": sha(main[start-0x40000000:end-0x40000000]),
                        "disassembly": disassembly})
    if (0x40000030+struct.unpack_from("<i", main, 0x31)[0]) & 0xFFFFFFFF != 0x7BC00000:
        raise ValueError("Reset linked-entry branch differs")
    constants = tuple(struct.unpack_from("<I", main, at)[0]
                      for at in (0x1E803, 0x1E8F0, 0x1E8F6, 0x1E8FE, 0x1E91F))
    if constants != (0x70000000, 0x41400000, 0x7BC00000, 0xB0000000, 0x41760000):
        raise ValueError("Installed program2-copy constants differ")
    spec = base_scenario("installed_program2_startup_copy")
    spec["images"] = copy.deepcopy(images)
    spec["maps"] += [[0x41400000, LENGTH], [0xBBC00000, LENGTH]]
    spec["images"].append(dict(images[1], address=0x41400000))
    spec["registers"].update(pc=0x4001E8EE, a0=0x70000000)
    spec["memory"] = [put(0x700F0000, b"\0")]
    spec["stops"] = {"copy_finished": 0x4001E924}
    spec["budget"], spec["trace_every"] = 10000000, 10000
    spec["dumps"] = [{"name": "copied-program2.data", "address": 0xBBC00000, "size": LENGTH}]
    spec["assumptions"] += ["Copy snippet starts after board setup with A0=0x70000000 as set in its native prefix.",
                             "The destination 0xbbc00000 is modeled as separate memory; its physical alias with 0x7bc00000 is not independently tested."]
    record = run_scenario(spec, backend, output)
    if (record["result"]["stop"] != "copy_finished"
            or (output/"copied-program2.data").read_bytes() != secondary):
        raise ValueError("Native startup did not copy the entire installed program2")
    return {"name": spec["name"], "execution": record, "regions": regions,
            "complete_component_copy_matches_backup": True,
            "copy_destination": "0xbbc00000", "linked_entry": "0x7bc00000",
            "physical_alias_independently_verified": False}


def tests(package: Path, backend: Path, decoder: Path, output: Path) -> dict:
    raw = package.read_bytes()
    entry = validate_scope(raw)
    images, main, secondary, flash = installed()
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    for name in ("gm5_emulator.py", "gm5_virtual_install.py", "panasonic_upd.py", "gh2_debug_verify.py"):
        (output/name).write_bytes((Path("tools")/name).read_bytes())
    controls = [startup_test(images, main, secondary, backend, decoder, output/"startup_copy")]
    print("Passed installed_program2_startup_copy", flush=True)
    bad_crc = bytearray(raw); bad_crc[-1] ^= 1
    bad_crc_path = output/"bad-crc.data"; bad_crc_path.write_bytes(bad_crc)
    decoded_path = context_path = None
    for name, path, allowance, expected in (("minimal_decode_allowed", package, 1, 0),
                                            ("minimal_decode_default_policy", package, 0, 0x80000065),
                                            ("minimal_decode_bad_crc", bad_crc_path, 1, 0x80000064)):
        spec = installed_decoder(name, path, allowance, images)
        directory = output/name
        record = run_scenario(spec, backend, directory)
        if (record["result"]["stop"] != "returned"
                or int(record["result"]["registers"][0], 0) != expected):
            raise ValueError(f"Installed decoder failed {name}: {record['result']}")
        after = (directory/"decoded-input.data").read_bytes()
        if not expected:
            if after[PAYLOAD_START:] != secondary or sha(after[PAYLOAD_START:]) != entry["field32_hex"]:
                raise ValueError("Native-decoded payload differs from the exact installed program2")
            decoded_path, context_path = directory/"decoded-input.data", directory/"context.bin"
        elif after != path.read_bytes():
            raise ValueError("Rejected input was modified")
        controls.append({"name": name, "execution": record, "expected_status": hex(expected),
                         "host_checked_native_plaintext_matches_backup": not bool(expected)})
        print(f"Passed {name}", flush=True)
    assert decoded_path and context_path
    decoded = decoded_path.read_bytes()
    for name, fail, cut in (("minimal_native_install", 0, 0),
                             ("minimal_native_program_failure", 1, 0),
                             ("minimal_native_power_cut", 0, 2)):
        spec = scenario(name, images, main, sync=True)
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
        spec["budget"], spec["trace_every"] = 200000000, 10000
        spec["dumps"] = [{"name": "post-job-input.data", "address": INPUT, "size": len(decoded)}]
        spec["assumptions"] += ["Post-decode job starts from the exact successful installed-build decoder context.",
                                 "Current settings fixtures use retained NOR slot A and adjustment data; not a full live-RAM capture.",
                                 "Board/handshake calls at 0x7bd4fe14 and 0x7bd4ff0d are bypassed explicitly; UI callbacks are disabled.",
                                 "Stops after programming iteration, before final cleanup/restart; no full boot or physical installation proof."]
        directory = output/name
        record = run_scenario(spec, backend, directory)
        stop = "nor_power_cut" if cut else "programming_finished"
        if record["result"]["stop"] != stop:
            raise ValueError(f"Native minimal installation stopped unexpectedly: {record['result']}")
        if (directory/"post-job-input.data").read_bytes() != decoded:
            raise ValueError("Minimal native job changed its decoded payload")
        expected = bytearray(flash)
        if fail or cut:
            expected[DESTINATION:DESTINATION+SECTOR] = b"\xff"*SECTOR
            if cut: expected[DESTINATION:DESTINATION+BUFFER] = secondary[:BUFFER]
        actual = (directory/"virtual-nor.bin").read_bytes()
        if actual != expected:
            raise ValueError("Full 32 MiB readback differs from the independent operation oracle")
        if actual[:DESTINATION] != flash[:DESTINATION] or actual[DESTINATION+LENGTH:] != flash[DESTINATION+LENGTH:]:
            raise ValueError("Write outside program2, including settings/calibration")
        committed = [e for e in events(directory) if e["event"] in ("erase_commit", "program_commit")]
        if any(not DESTINATION <= int(e["offset"], 0) < DESTINATION+LENGTH for e in committed):
            raise ValueError("NOR command committed outside the fixed component")
        statuses = [int(json.loads(line)["d0"], 0) for line in (directory/"trace.jsonl").read_text().splitlines()
                    if '"event":"watch"' in line]
        if not cut and statuses != ([0x8000000C] if fail else [0]):
            raise ValueError(f"Native single-component writer statuses differ: {statuses}")
        stats = record["result"]["nor"]
        counts = (1, 1) if cut else (1, 0) if fail else (LENGTH//SECTOR, LENGTH//BUFFER)
        if (stats["erases"], stats["programs"], stats["zero_to_one_words"]) != (*counts, 0):
            raise ValueError(f"Unexpected minimal NOR operation counts: {stats}")
        if not fail and not cut:
            erase_offsets = [int(e["offset"], 0) for e in committed if e["event"] == "erase_commit"]
            program_offsets = [int(e["offset"], 0) for e in committed if e["event"] == "program_commit"]
            if erase_offsets != list(range(DESTINATION, DESTINATION+LENGTH, SECTOR)):
                raise ValueError("Sector erase coverage differs")
            if program_offsets != list(range(DESTINATION, DESTINATION+LENGTH, BUFFER)):
                raise ValueError("Programming buffer coverage differs")
        controls.append({"name": name, "execution": record, "complete_readback_matches_operation_oracle": True,
                         "whole_flash_byte_identical_to_backup": actual == flash,
                         "outside_program2_byte_identical": True, "settings_and_calibration_byte_identical": True,
                         "all_mutation_commands_inside_program2": True,
                         "component_writer_returns": [hex(value) for value in statuses],
                         "readback_detects_incomplete_install": bool(fail or cut),
                         "outer_job_reaches_end_despite_writer_error": bool(fail)})
        print(f"Passed {name}", flush=True)
    if sha(BACKUP.read_bytes()) != BACKUP_SHA or package.read_bytes() != raw:
        raise ValueError("Protected input changed during tests")
    report = {"schema": 1, "scope": "Exact minimal GM5 package: native decoder/startup-copy/post-decode virtual NOR",
              "package": artifact(package), "passed": len(controls), "controls": controls,
              "driver_sha256": sha(Path(__file__).read_bytes()), "backup_sha256": BACKUP_SHA,
              "backup_unchanged": True, "camera_contacted": False, "physical_flash_written": False,
              "limits": ["Unsigned native decoding skips component SHA checks; host checks every decoded byte against the backup.",
                         "Explicit board/RTOS/cache abstractions and partial entry states remain; no full physical machine is modeled.",
                         "The 0xbbc00000/0x7bc00000 runtime alias is indicated by native code, not independently measured.",
                         "Physical acceptance, final cleanup/restart and a working recovery writer remain unproven."]}
    report["retained_helpers"] = [artifact(output/name) for name in
                                  ("gm5_emulator.py", "gm5_virtual_install.py", "panasonic_upd.py", "gh2_debug_verify.py")]
    save_json(output/"summary.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "test"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--codec", type=Path, default=Path("work/panasonic-aes5-codec"))
    parser.add_argument("--original-decoder", type=Path, default=Path("work/panasonic-aes5"))
    parser.add_argument("--package", type=Path)
    parser.add_argument("--backend", type=Path, default=DEFAULT_BACKEND)
    parser.add_argument("--disassembler", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    args = parser.parse_args()
    if args.action == "build":
        result = build(args.codec, args.original_decoder, args.out)
        print(f"Prepared offline control {result['package']['sha256']}")
    else:
        if args.package is None: parser.error("test requires --package")
        result = tests(args.package, args.backend, args.disassembler, args.out)
        print(f"Passed {result['passed']} exact-package native controls")


if __name__ == "__main__":
    main()
