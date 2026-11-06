#!/usr/bin/env python3
"""Verify saved GM1 read packets and dump bytes offline, including resume lineage."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

BASE = 0x40000000
PROGRAM_BYTES = 9 * 1024 * 1024
SECONDARY_BASE = 0x41400000
SECONDARY_BYTES = 0x360000
GM5_NOR_BYTES = 32 * 1024 * 1024
BLOCK = 1024
GM5_CONTROL = bytes.fromhex("8100580002008100580002002c00180002002c00180002000000020000000000")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def wire(event: dict) -> bytes:
    data = bytes.fromhex(event["hex"])
    if len(data) != event["bytes"]:
        raise ValueError("Logged transfer length differs from raw bytes")
    return data


def check_frame(data: bytes, size: int, kind: int) -> None:
    if (len(data) != size or data[0] != kind or data[1:3] != b"\0\xff"
            or data[-1] != 0 or data[-2] != sum(data[1:-2]) & 255):
        raise ValueError("Frame length/type/sequence/checksum/terminator differs")


def request(data: bytes, model: str = "DMC-GM1", *, full_nor: bool = False) -> dict:
    if len(data) < 4:
        raise ValueError("Short request")
    op = data[3]
    if op in (0x38, 0x70):
        check_frame(data, 16, 8)
        if op == 0x38:
            index = struct.unpack_from("<H", data, 4)[0]
            if not 0x3F80 <= index < 0x3F90 or data[6] != 0x20 or any(data[7:14]):
                raise ValueError("Unexpected settings read range/area")
        else:
            index = struct.unpack_from("<I", data, 4)[0]
            if index >= 32 or any(data[8:14]):
                raise ValueError("Unexpected program word read range")
        return {"operation": op, "index": index, "type": 8, "size": 16}
    if op == 0x5C:
        check_frame(data, 1030, 1)
        start, end = struct.unpack_from("<II", data, 4)
        program_bytes = (GM5_NOR_BYTES if full_nor else 0x800000) if model == "DMC-GM5" else PROGRAM_BYTES
        allowed = (BASE <= start < BASE + program_bytes
                   or SECONDARY_BASE <= start < SECONDARY_BASE + SECONDARY_BYTES
                   or model == "DMC-GM5" and (start in (0x70A68400, 0x702FF800, 0x701AF000, 0x70A0F000, 0x70A67800, 0x701F9400)
                                               or 0x7BFB0000 <= start < 0x7BFB4800))
        if (not allowed or start % BLOCK
                or end != start + BLOCK or any(data[12:-2])):
            raise ValueError("Unexpected block read interval/padding")
        return {"operation": op, "index": (start - BASE) // BLOCK, "type": 1, "size": 1030}
    raise ValueError(f"Unexpected operation {op:#x}; not an allowed read capture")


def parse_events(events, allow_incomplete: bool = False, model: str = "DMC-GM1", *, full_nor: bool = False) -> dict:
    phase = "idle"
    pending = None
    frames, errors = [], []
    identities = []
    controls = writes = 0
    for event in events:
        kind = event["event"]
        if kind == "registry_identity":
            identities.append(event)
        if kind == "api_result":
            if event["result"] != "0x00000000":
                errors.append(event)
            continue
        if kind not in ("control_attempt", "bulk_out_attempt", "bulk_in_type", "bulk_in"):
            continue
        if errors:
            raise ValueError("USB transfer attempted after a recorded API error")
        if kind == "control_attempt":
            controls += 1
            setup = event["setup_hex"]
            if setup == "4000000000000000" and phase == "idle":
                phase = "out_prepared"
            elif setup == "4000000001000000" and phase == "need_type_prepare":
                phase = "type_prepared"
            elif setup == "4000000001000000" and phase == "need_frame_prepare":
                phase = "frame_prepared"
            else:
                raise ValueError(f"Unexpected control request/phase: {setup}, {phase}")
        elif kind == "bulk_out_attempt":
            writes += 1
            if phase != "out_prepared":
                raise ValueError("Bulk OUT without its preparation")
            pending = request(wire(event), model, full_nor=full_nor)
            phase = "need_type_prepare"
        elif kind == "bulk_in_type":
            if phase != "type_prepared" or wire(event) != bytes([pending["type"]]):
                raise ValueError("Unexpected response-type transfer")
            phase = "need_frame_prepare"
        else:
            if phase != "frame_prepared":
                raise ValueError("Full frame without the second IN preparation")
            data = wire(event)
            check_frame(data, pending["size"], pending["type"])
            if data[3] != (5 if pending["operation"] == 0x5C else 0x36):
                raise ValueError("Unexpected response status")
            if pending["operation"] != 0x5C and any(data[6:14]):
                raise ValueError("Unexpected word response padding")
            frames.append(dict(pending, payload=data[4:-2] if pending["operation"] == 0x5C else data[4:6]))
            pending = None
            phase = "idle"
    if (phase != "idle" or errors) and not allow_incomplete:
        raise ValueError("Capture ended with an incomplete or failed transaction")
    return {"frames": frames, "controls": controls, "writes": writes,
            "errors": errors, "terminal_phase": phase, "identities": identities}


def verify_capture(capture: Path, allow_incomplete: bool = False, seen=None) -> dict:
    capture = capture.resolve()
    if capture.name == "result":
        capture = capture.parent
    seen = set() if seen is None else set(seen)
    if capture in seen or len(seen) >= 64:
        raise ValueError("Invalid resume lineage cycle/depth")
    seen.add(capture)
    result = capture / "result"
    summary = json.loads((result / "summary.json").read_text())
    model = summary.get("model", "DMC-GM1")
    nor_mode = summary["mode"] in ("nor-backup", "resume-nor-backup")
    if model not in ("DMC-GM1", "DMC-GM5"):
        raise ValueError("Unsupported camera model")
    if model == "DMC-GM5" and summary["mode"] not in (
            "inspect", "access", "settings", "flash", "block", "window", "initializer",
            "startup-data", "security-flag", "updater-window", "runtime-control",
            "update-profile", "usb-handler", "usb-state", "language-head", "update-settings",
            "update-ui-state", "update-entry", "nor-backup", "resume-nor-backup", "secondary", "resume-secondary",
            "program", "resume"):
        raise ValueError("Unsupported GM5 capture mode")
    if nor_mode and model != "DMC-GM5":
        raise ValueError("Full NOR backup requires the GM5 model")
    if summary["exit_status"] and not allow_incomplete:
        raise ValueError("Capture is marked incomplete")
    with (result / "events.jsonl").open() as stream:
        parsed = parse_events((json.loads(line) for line in stream), allow_incomplete, model, full_nor=nor_mode)
    if model == "DMC-GM5":
        identity = parsed["identities"]
        if len(identity) != 1 or any(identity[0].get(key) != value for key, value in {
                "product_name": model, "vendor_id": 0x04DA, "product_id": 0x2370,
                "interface": [255, 160, 176], "configuration": 1,
                "alternate_setting": 0, "endpoints": 3}.items()):
            raise ValueError("GM5 registry identity differs")
    if (parsed["controls"] != summary["control_requests_attempted"]
            or parsed["writes"] != summary["bulk_writes_attempted"]):
        raise ValueError("Summary transfer counts differ from transcript")
    frames = parsed["frames"]
    words = [f for f in frames if f["operation"] != 0x5C]
    if len(words) != summary["validated_word_responses"]:
        raise ValueError("Word response count differs")
    settings = [f for f in words if f["operation"] == 0x38]
    if [f["index"] for f in settings] != list(range(0x3F80, 0x3F80 + len(settings))):
        raise ValueError("Settings word order differs")
    settings_data = b"".join(f["payload"] for f in settings)
    settings_path = result / "fixed-markers.bin"
    if settings_data != settings_path.read_bytes() or len(settings_data) != summary["settings_bytes"]:
        raise ValueError("Settings file differs from validated packets")
    if len(settings_data) == 32:
        if model == "DMC-GM5":
            if settings_data != GM5_CONTROL:
                raise ValueError("GM5 settings control differs from prior body sample")
        elif settings_data[:10] != b"Panasonic\0" or settings_data[16:24] != model.encode()+b"\0":
            raise ValueError("Camera settings markers differ")
    elif frames:
        raise ValueError("Incomplete settings control precedes later reads")
    program_words = [f for f in words if f["operation"] == 0x70]
    if program_words:
        if [f["index"] for f in program_words] != list(range(len(program_words))):
            raise ValueError("Program word order differs")
        if b"".join(f["payload"] for f in program_words) != (result / "flash-prefix.bin").read_bytes():
            raise ValueError("Program prefix differs from validated packets")
    blocks = [f for f in frames if f["operation"] == 0x5C]
    mode = summary["mode"]
    secondary_mode = mode in ("secondary", "secondary-window", "resume-secondary")
    file_base = (0x416C3000 if mode == "secondary-data" else SECONDARY_BASE if secondary_mode
                 else (0x40643800 if model == "DMC-GM5" else 0x405A3800) if mode == "initializer" else BASE)
    if model == "DMC-GM5":
        file_base = {"startup-data": 0x40003000, "security-flag": 0x406B1800,
                     "updater-window": 0x4154E000, "runtime-control": 0x70A68400,
                     "update-profile": 0x4162A400, "usb-handler": 0x4036C000,
                     "usb-state": 0x702FF800, "language-head": 0x7BFB0000,
                     "update-settings": 0x7BFB0000, "update-ui-state": 0x701F9400,
                     "update-entry": 0x4023B800}.get(mode, file_base)
    file_base_block = (file_base - BASE) // BLOCK
    prefix = b""
    anchors = []
    if mode in ("resume", "resume-secondary", "resume-nor-backup"):
        manifest = json.loads((capture / "resume-manifest.json").read_text())
        parent = verify_capture(Path(manifest["parent_capture"]), True, seen)
        if nor_mode != (parent["mode"] in ("nor-backup", "resume-nor-backup")):
            raise ValueError("Resume mixes a full NOR backup and program component")
        if int(parent["program_file_base"], 16) != file_base:
            raise ValueError("Resume component differs from parent")
        prefix = (capture / "verified-prefix.bin").read_bytes()
        if (len(prefix) != parent["verified_prefix_bytes"] or digest(prefix) != parent["program_sha256"]
                or digest(prefix) != manifest["prefix_sha256"]):
            raise ValueError("Copied resume prefix differs from verified parent")
        first = len(prefix) // BLOCK
        relative_anchors = list(dict.fromkeys((0, first // 2, first - 1)))
        anchors = [file_base_block + n for n in relative_anchors]
        if [f["index"] for f in blocks[:len(anchors)]] != anchors:
            raise ValueError("Resume anchors differ or are incomplete")
        for f in blocks[:len(anchors)]:
            relative_index = f["index"] - file_base_block
            if f["payload"] != prefix[relative_index*BLOCK:(relative_index+1)*BLOCK]:
                raise ValueError("Live resume anchor differs from parent")
        blocks = blocks[len(anchors):]
    filename = {"block": "program-block.bin", "window": "program-window.bin",
                "program": "program-main.bin", "resume": "program-main.bin",
                "initializer": "ram-initializer.bin", "secondary": "program2.bin",
                "secondary-window": "program2-window.bin", "resume-secondary": "program2.bin",
                "secondary-data": "program2-data.bin", "startup-data": "startup-data.bin",
                "security-flag": "security-flag.bin", "updater-window": "updater-window.bin",
                "runtime-control": "runtime-control.bin", "update-profile": "update-profile.bin",
                "usb-handler": "usb-handler.bin", "usb-state": "usb-state.bin",
                "language-head": "language-settings-head.bin", "update-settings": "update-settings.bin",
                "update-ui-state": "update-ui-state.bin", "update-entry": "update-entry.bin",
                "nor-backup": "flash32m.bin", "resume-nor-backup": "flash32m.bin"}.get(mode)
    program_data = b""
    file_offset = 0
    if filename:
        program_data = (result / filename).read_bytes()
        # The first initializer capture used an absolute file offset. Preserve
        # that original sparse file and verify its populated interval directly.
        if mode == "initializer" and model == "DMC-GM1" and len(program_data) == 0x5AB800:
            file_offset = 0x5A3800
            if any(program_data[:file_offset]):
                raise ValueError("Unexpected data before sparse initializer interval")
            program_data = program_data[file_offset:]
        if mode == "window":
            if len(blocks) != 16 or [f["index"] for f in blocks] != list(range(8)) + list(reversed(range(8))):
                raise ValueError("Window forward/reverse sequence differs")
            for f in blocks:
                if program_data[f["index"]*BLOCK:(f["index"]+1)*BLOCK] != f["payload"]:
                    raise ValueError("Window block differs from transcript")
            if program_data != (result / "program-window-repeat.bin").read_bytes():
                raise ValueError("Repeated window bytes differ")
        else:
            first = (file_base - BASE + len(prefix)) // BLOCK
            if [f["index"] for f in blocks] != list(range(first, first + len(blocks))):
                raise ValueError("Program blocks contain an overlap, gap or reordered address")
            if program_data != prefix + b"".join(f["payload"] for f in blocks):
                raise ValueError("Program file differs from validated packets/prefix")
        if len(blocks) * BLOCK != summary.get("program_block_bytes", 0):
            raise ValueError("Program byte count differs from transcript")
    complete = not summary["exit_status"] and not parsed["errors"] and parsed["terminal_phase"] == "idle"
    main_bytes = 0x800000 if model == "DMC-GM5" else PROGRAM_BYTES
    if mode in ("program", "resume") and (len(program_data) > main_bytes or complete and len(program_data) != main_bytes):
        raise ValueError("Successful main-program capture has an incomplete extent")
    if mode in ("secondary", "resume-secondary") and complete and len(program_data) != SECONDARY_BYTES:
        raise ValueError("Successful secondary-program capture has an incomplete extent")
    if nor_mode and (len(program_data) > GM5_NOR_BYTES or complete and len(program_data) != GM5_NOR_BYTES):
        raise ValueError("Full NOR backup extent differs")
    expected_sizes = {"block": 1024, "window": 8192, "initializer": 32768,
                      "secondary-window": 65536, "secondary-data": 18432,
                      "startup-data": 1024, "security-flag": 1024,
                      "updater-window": 16384, "runtime-control": 1024,
                      "update-profile": 1024, "usb-handler": 16384, "usb-state": 1024,
                      "language-head": 1024, "update-settings": 18432,
                      "update-ui-state": 1024, "update-entry": 3072}
    if complete and mode in expected_sizes and len(program_data) != expected_sizes[mode]:
        raise ValueError("Successful bounded capture has an incomplete extent")
    return {"schema": 1, "capture": str(capture), "model": model, "mode": mode, "complete": complete,
            "settings_bytes_verified": len(settings_data), "word_responses_verified": len(words),
            "program_block_responses_verified": len(blocks) + len(anchors),
            "resume_anchors_verified": len(anchors), "copied_prefix_bytes": len(prefix),
            "program_file": str(result / filename) if filename else None,
            "verified_prefix_bytes": len(program_data), "program_sha256": digest(program_data),
            "program_file_base": hex(file_base), "program_file_offset": file_offset,
            "next_program_address": hex(file_base + len(program_data)),
            "terminal_phase": parsed["terminal_phase"], "errors": parsed["errors"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        report = verify_capture(args.capture, args.allow_incomplete)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Capture verification failed: {error}\n")
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        with args.out.open("x") as stream:
            stream.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
