#!/usr/bin/env python3
"""Check startup mappings against the physically acquired GM1 program prefix."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from gh2_debug_verify import checked_disassembly

BASE = 0x40000000
PREFIX_BYTES = 1226752
PREFIX_SHA256 = "ae9ec5587e03aa57e68b61922bd9e516e90eabdf90eb23c29fc71c38db36e0d8"


def make_report(source: Path, decoder: Path) -> dict:
    data = source.read_bytes()
    if len(data) < PREFIX_BYTES or hashlib.sha256(data[:PREFIX_BYTES]).hexdigest() != PREFIX_SHA256:
        raise ValueError("Expected the verified physical GM1 program prefix")
    def word(address):
        return struct.unpack_from("<I", data, address - BASE)[0]
    initializer = (word(0x40000191), word(0x40000197), word(0x400001A1))
    if initializer != (0x405A3884, 0x405AB54C, 0x70000000):
        raise ValueError("Initialized-data copy constants differ")
    secondary = (word(0x400511D8), word(0x40051200), word(0x400511DE))
    if secondary != (0x41400000, 0x41760000, 0x7BC00000):
        raise ValueError("Secondary-code copy constants differ")
    if data[0x30] != 0xDC or (0x40000030 + word(0x40000031)) & 0xFFFFFFFF != secondary[2]:
        raise ValueError("Reset secondary-code branch differs")
    regions = []
    for name, start, end in (
        ("main_reset", 0x40000000, 0x40000038),
        ("initialized_data_copy", 0x4000017D, 0x400001AF),
        ("secondary_code_copy", 0x400510DD, 0x4005121D),
    ):
        text, count = checked_disassembly(source, data, decoder, BASE, start, end)
        regions.append({"name": name, "start": hex(start), "end_exclusive": hex(end),
                        "instruction_count": count, "raw_annotations_match_source": True,
                        "native_sha256": hashlib.sha256(data[start-BASE:end-BASE]).hexdigest(),
                        "disassembly": text})
    return {"schema": 1, "scope": "Physically read GM1 startup mappings; no GM5 or update-key identity inferred",
            "source": {"path": str(source), "verified_prefix_bytes": PREFIX_BYTES,
                       "verified_prefix_sha256": PREFIX_SHA256, "acquisition": "evidence/gm1-usb-readback.json"},
            "verifier": {"path": "tools/gm1_startup_verify.py",
                         "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "regions": regions,
            "initialized_data": {"flash_start": hex(initializer[0]), "flash_end_exclusive": hex(initializer[1]),
                                 "ram_start": hex(initializer[2]), "bytes": initializer[1]-initializer[0]},
            "secondary_code": {"flash_start": hex(secondary[0]), "flash_end_exclusive": hex(secondary[1]),
                               "bytes": secondary[1]-secondary[0], "linked_entry": hex(secondary[2]),
                               "official_directory_component": "program2",
                               "alias_note": "The copy destination uses address arithmetic; physical/runtime alias hardware is not independently verified."},
            "limits": ["RAM initializer is located; no field in it is established as a GM1 update key yet.",
                       "Secondary program is mapped by native code but not acquired by this verifier.",
                       "No camera or firmware code is executed by this tool."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = make_report(args.source, args.decoder)
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print("Verified GM1 reset branch, initialized-data copy and program2 copy regions.")


if __name__ == "__main__":
    main()
