#!/usr/bin/env python3
"""Check the physically acquired GM1 secondary reset and initializer mappings."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from gh2_debug_verify import checked_disassembly

LINKED_BASE = 0x7BC00000
FLASH_BASE = 0x41400000
PREFIX_BYTES = 65536
PREFIX_SHA256 = "7eaec6c8a65805d282a5e0e3e1f137c5cc0a1d2774d070e9da388aad25a49fc5"


def report(source: Path, decoder: Path) -> dict:
    data = source.read_bytes()
    if len(data) < PREFIX_BYTES or hashlib.sha256(data[:PREFIX_BYTES]).hexdigest() != PREFIX_SHA256:
        raise ValueError("Expected the physically acquired GM1 secondary prefix")
    def word(address):
        return struct.unpack_from("<I", data, address-LINKED_BASE)[0]
    constants = (word(0x7BC001CD), word(0x7BC001D3), word(0x7BC001DD),
                 word(0x7BC00201), word(0x7BC00207), word(0x7BC00211))
    if constants != (0x7BEC3160, 0x7BEC3168, 0x70B01374, 0x7BEC3168, 0x7BEC7724, 0x70B19050):
        raise ValueError("Secondary initialized-data copy constants differ")
    regions = []
    for name, start, end in (("secondary_reset", 0x7BC00000, 0x7BC00058),
                             ("first_data_initialization", 0x7BC000E3, 0x7BC00119),
                             ("later_data_initialization", 0x7BC001B5, 0x7BC0022E)):
        text, count = checked_disassembly(source, data, decoder, LINKED_BASE, start, end)
        regions.append({"name": name, "start": hex(start), "end_exclusive": hex(end),
                        "instruction_count": count, "raw_annotations_match_source": True,
                        "native_sha256": hashlib.sha256(data[start-LINKED_BASE:end-LINKED_BASE]).hexdigest(),
                        "disassembly": text})
    copies = []
    for start, end, destination in (constants[:3], constants[3:]):
        copies.append({"linked_source_start": hex(start), "linked_source_end_exclusive": hex(end),
                       "flash_start": hex(FLASH_BASE + start-LINKED_BASE),
                       "flash_end_exclusive": hex(FLASH_BASE + end-LINKED_BASE),
                       "ram_destination": hex(destination), "bytes": end-start})
    return {"schema": 1, "scope": "GM1 secondary startup/data mappings; no updater key inferred",
            "source": {"path": str(source), "prefix_bytes": PREFIX_BYTES, "prefix_sha256": PREFIX_SHA256},
            "verifier": {"path": "tools/gm1_secondary_verify.py",
                         "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "flash_base": hex(FLASH_BASE), "linked_base": hex(LINKED_BASE),
            "regions": regions, "initialized_copies": copies,
            "limits": ["Mapping follows the main startup copy and the physically matched secondary reset.",
                       "No initializer field is identified as an update key by this verifier.",
                       "No camera connection, native target execution or flash write occurs."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = report(args.source, args.decoder)
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("Verified GM1 secondary reset and two RAM initializer copies.")


if __name__ == "__main__":
    main()
