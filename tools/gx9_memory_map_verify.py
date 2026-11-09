#!/usr/bin/env python3
"""Verify GX9 address-map evidence in two pinned private RAM captures offline.

Decodes a candidate Linux first-level table and checks actual ARM instructions
which build four early identity maps. Neither is a list of safe USB addresses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct


LINUX_SHA = "70ee773d7d4065d594d12d31e060f390abba5f0984c7a77fcae79b06e8a516b0"
EARLY_SHA = "3fcd46e425cdc5eeaa9053decb99cda821b09017a97906de3cd4b12d1a44802c"
TABLES_SHA = "11087f892ac73608bf922cd2ce90866aecd268b79fe1540ded5182d5b280a97f"


def pinned(path: Path, size: int, digest: str) -> bytes:
    data = path.read_bytes()
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Capture differs from the pinned input: {path}")
    return data


def linux_table(data: bytes) -> dict:
    raw = data[0x4000:0x8000]
    if len(raw) != 16384:
        raise ValueError("Candidate first-level table is truncated")
    descriptors = struct.unpack("<4096I", raw)
    groups = []
    coarse = []
    faults = 0
    sections = 0
    for index, value in enumerate(descriptors):
        kind = value & 3
        if kind == 0:
            faults += 1
        elif kind == 1:
            coarse.append({"virtual_start": hex(index << 20),
                           "table_physical": hex(value & 0xFFFFFC00),
                           "descriptor": hex(value)})
        elif kind in (2, 3):
            # ARMv7 section PXN occupies bit 0; bit 1 still identifies a section.
            if value & (1 << 18):
                raise ValueError("Supersections require a separate decoder")
            virtual = index << 20
            physical = value & 0xFFF00000
            attributes = value & 0xFFFFF
            sections += 1
            if (groups and groups[-1]["virtual_end_exclusive"] == virtual
                    and groups[-1]["physical_end_exclusive"] == physical
                    and groups[-1]["attributes"] == attributes):
                groups[-1]["virtual_end_exclusive"] += 0x100000
                groups[-1]["physical_end_exclusive"] += 0x100000
            else:
                groups.append({"virtual_start": virtual,
                               "virtual_end_exclusive": virtual + 0x100000,
                               "physical_start": physical,
                               "physical_end_exclusive": physical + 0x100000,
                               "attributes": attributes})
    return {
        "candidate_service_address": "0x80204000",
        "table_bytes": len(raw), "table_sha256": hashlib.sha256(raw).hexdigest(),
        "format": "ARMv7 short-descriptor first-level translation table",
        "fault_entries": faults, "section_entries": sections,
        "section_ranges": [{k: hex(v) for k, v in g.items()} for g in groups],
        "coarse_table_entries": coarse,
        "active_ttbr_register_observed": False,
        "physical_to_usb_address_translation_verified": False,
        "exhaustive_hardware_map": False,
    }


def rotate_right(value: int, count: int) -> int:
    return ((value >> count) | (value << ((32-count) % 32))) & 0xFFFFFFFF


def early_map_builder(data: bytes) -> dict:
    def word(offset: int) -> int:
        return struct.unpack_from("<I", data, offset)[0]

    def literal(offset: int, register: int) -> int:
        instruction = word(offset)
        if instruction & 0xFFFFF000 != 0xE59F0000 | register << 12:
            raise ValueError("Expected positive PC-relative ARM literal load")
        return word(offset + 8 + (instruction & 0xFFF))

    loop_tail = (0xE1A01A23, 0xE0821101, 0xE0837004, 0xE5817000,
                 0xE0833006, 0xE2555001, 0x5AFFFFF8)
    tables = []
    for core in range(4):
        start = 0x514 + core * 0x300
        table = None
        regions = []
        for region in range(16):
            offset = start + region * 0x30
            instruction = word(offset)
            if instruction & 0xFFFFF000 != 0xE3A03000:
                raise ValueError("Expected MOV r3, rotated immediate")
            base = rotate_right(instruction & 255, 2*((instruction >> 8) & 15))
            if base != region << 28:
                raise ValueError("Early map's source section differs")
            if word(offset+4) != 0xE3A050FF or word(offset+8) != 0xE3A06601:
                raise ValueError("Expected 256 iterations with a 1 MiB increment")
            if tuple(word(offset+i) for i in range(20, 48, 4)) != loop_tail:
                raise ValueError("Section-descriptor store loop differs")
            target = literal(offset+12, 2)
            table = target if table is None else table
            if target != table:
                raise ValueError("Early map writes an unexpected table")
            attributes_instruction = word(offset+16)
            if attributes_instruction & 0xFFFFF000 == 0xE59F4000:
                attributes = literal(offset+16, 4)
            elif attributes_instruction == 0xE3024002:
                attributes = 0x2002
            elif attributes_instruction == 0xE3A04002:
                attributes = 2
            else:
                raise ValueError("Unexpected descriptor-attribute instruction")
            if attributes >= 0x100000 or attributes & 3 != 2:
                raise ValueError("Expected ordinary section attributes")
            regions.append({"virtual_start": hex(base),
                            "virtual_end_exclusive": hex(base+0x10000000),
                            "physical_start": hex(base),
                            "attributes": hex(attributes)})
        code = data[start:start+0x300]
        tables.append({"core_index": core, "table_address_literal": hex(table),
                       "code_service_address": hex(0x80000000+start),
                       "code_bytes": len(code),
                       "code_sha256": hashlib.sha256(code).hexdigest(),
                       "identity_mapped_bytes": 1 << 32, "regions": regions})
    if word(0x504) != 0xEE021F10 or literal(0x108, 0) != 0x83E70000:
        raise ValueError("Early TTBR0 setup or its source literal differs")
    return {"tables": tables,
            "ttbr0_store_service_address": "0x80000504",
            "mapped_descriptor_does_not_establish_backing_memory": True,
            "current_tables_read": False,
            "usb_handler_cpu_mapping_identified": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("linux_capture", type=Path)
    parser.add_argument("early_capture", type=Path)
    parser.add_argument("--early-tables", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    linux = pinned(args.linux_capture, 98304, LINUX_SHA)
    early = pinned(args.early_capture, 986112, EARLY_SHA)
    result = {"schema": 1, "scope": "Pinned GX9 RAM map evidence; offline only",
              "inputs": [{"label": "linux-prefix", "bytes": len(linux), "sha256": LINUX_SHA},
                         {"label": "early-arm-prefix", "bytes": len(early), "sha256": EARLY_SHA}],
              "linux_table_candidate": linux_table(linux),
              "early_arm_table_builder": early_map_builder(early),
              "camera_or_network_access": False}
    table = result["linux_table_candidate"]
    if table["section_entries"] != 47 or len(table["coarse_table_entries"]) != 24:
        raise ValueError("Pinned GX9 table geometry differs")
    if args.early_tables:
        current = pinned(args.early_tables, 81920, TABLES_SHA)
        result["inputs"].append({"label": "early-tables-and-entry", "bytes": len(current),
                                 "sha256": TABLES_SHA})
        builder = result["early_arm_table_builder"]
        for entry in builder["tables"]:
            expected = b"".join(struct.pack("<I", base + int(region["attributes"], 16))
                                for region in entry["regions"]
                                for base in range(int(region["virtual_start"], 16),
                                                  int(region["virtual_end_exclusive"], 16), 0x100000))
            offset = entry["core_index"] * 16384
            actual = current[offset:offset+16384]
            if actual != expected:
                raise ValueError("Acquired early table differs from its native builder")
            entry.update(acquired_table_sha256=hashlib.sha256(actual).hexdigest(),
                         all_4096_entries_match_builder=True)
        builder["current_tables_read"] = True
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print("Verified 47 Linux section entries, 24 coarse-table entries and four early identity-map builders.")


if __name__ == "__main__":
    main()
