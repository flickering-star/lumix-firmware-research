#!/usr/bin/env python3
"""Verify the pinned GH2 0x5c memory-copy reader offline; never contact USB."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from gh2_debug_verify import MAIN_BASE, TABLE_OFFSET, checked_disassembly, verify_input


def make_report(body: Path, decoder: Path) -> dict:
    data = body.read_bytes()
    verify_input(data)
    branch = struct.unpack_from("<I", data, TABLE_OFFSET + 4 * 0x5C)[0]
    if branch != 0x401EF2BD:
        raise ValueError("Block-reader table entry differs")
    at = branch - MAIN_BASE
    if data[at] != 0xCD or branch + struct.unpack_from("<h", data, at + 1)[0] != 0x401F0470:
        raise ValueError("Block-reader dispatch call differs")
    properties = dict(struct.iter_unpack("<II", data[0x407F23B4-MAIN_BASE:0x407F2434-MAIN_BASE]))
    if properties.get(0x5C - 11) != 0x401EF514:
        raise ValueError("Block-reader header classification differs")
    if data[0x401EF514-MAIN_BASE:0x401EF516-MAIN_BASE] != bytes.fromhex("ca11"):
        raise ValueError("Expected branch into class-one header classification")
    regions = []
    for name, start, end in (
        ("block_dispatch", 0x401EF2BD, 0x401EF2C5),
        ("header_classification", 0x401EF4B2, 0x401EF592),
        ("absolute_range_copy_and_response", 0x401F0470, 0x401F04FD),
    ):
        disassembly, count = checked_disassembly(body, data, decoder, MAIN_BASE, start, end)
        regions.append({"name": name, "start": hex(start), "end_exclusive": hex(end),
                        "native_sha256": hashlib.sha256(data[start-MAIN_BASE:end-MAIN_BASE]).hexdigest(),
                        "instruction_count": count, "raw_annotations_match_source": True,
                        "disassembly": disassembly})
    return {
        "schema": 1,
        "scope": "Pinned GH2 native block reader; GM1 compatibility requires live comparison",
        "source": {"path": str(body), "sha256": hashlib.sha256(data).hexdigest()},
        "verifier": {"path": "tools/gh2_block_read_verify.py",
                     "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "decoder": {"path": str(decoder), "sha256": hashlib.sha256(decoder.read_bytes()).hexdigest()},
        "mechanical_checks": {"operation": "0x5c", "dispatch_branch": hex(branch),
                              "handler": "0x401f0470", "header_property_key": "0x51",
                              "header_property_target": "0x401ef514", "regions": regions},
        "manual_static_interpretation": {
            "request_type": 1, "request_bytes": 1030,
            "start_address": "32-bit little endian, request bytes 4..7",
            "end_address_exclusive": "32-bit little endian, request bytes 8..11",
            "copy": "Copies byte pairs from start to end into USB buffer offset four",
            "response": "Type one, sequence 00/ff, status 05, fixed 1024-byte payload; checksum at 1028, zero terminator at 1029",
            "reviewed_side_effects": "USB protocol state and response-buffer stores; no flash-programming call in the reviewed handler",
            "bounds": "No explicit 1024-byte range limit in the handler; the host must require an aligned, exactly 1024-byte interval. No out-of-range request is proposed.",
        },
        "camera_contacted_by_verifier": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = make_report(args.body, args.decoder)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print("Verified GH2 0x5c dispatch, header classification and native copy/response regions.")


if __name__ == "__main__":
    main()
