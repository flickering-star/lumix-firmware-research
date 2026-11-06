#!/usr/bin/env python3
"""Recheck the recovered GM1 AHX input and NOR programming path, offline only.

Pins both complete physical programs, checks instruction bytes and call links,
and retains the reviewed disassembly. No image, USB command or target execution
is produced. The factory/recovery interpretation is manual analysis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from gh2_debug_verify import checked_disassembly


INPUTS = {
    "main": (0x40000000, 9437184,
             "a96fb6da618b33207db0d357ac5e2513583aaa71dd01df44bed498e63992fabe"),
    "secondary": (0x7BC00000, 3538944,
                  "7e8c7d96a95a505d5500fafbd076a56e95f27267708c1f02deb2606fcd304968"),
}
REGIONS = (
    ("startup_job_calls", "main", 0x4004FFF6, 0x4005002D),
    ("ahx_job", "main", 0x40158FE8, 0x401592B1),
    ("ahx_file_reader", "main", 0x4024F40F, 0x4024F501),
    ("hex_decoders", "main", 0x4024F501, 0x4024F63F),
    ("s3_parser", "main", 0x4024F63F, 0x4024F725),
    ("programming_setup", "secondary", 0x7BD23171, 0x7BD235F9),
    ("programming_core_front", "secondary", 0x7BD235F9, 0x7BD2370F),
    ("programming_loop_call", "secondary", 0x7BD2384E, 0x7BD2389D),
    ("nor_erase_and_program", "secondary", 0x7BD1B0B0, 0x7BD1B1B0),
)
CALLS = (
    ("main", 0x4005000A, 0x40158FE8),
    ("main", 0x40050026, 0x40158FE8),
    ("main", 0x4015917F, 0x4024F40F),
    ("main", 0x401591A4, 0x4024F40F),
    ("main", 0x4024F498, 0x4024F63F),
    ("main", 0x40159204, 0x7BD23171),
    ("secondary", 0x7BD235F0, 0x7BD235F9),
    ("secondary", 0x7BD23651, 0x7BD1B0B0),
    ("secondary", 0x7BD236F4, 0x7BD1B116),
    ("secondary", 0x7BD2385E, 0x7BD1B116),
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def report(main: Path, secondary: Path, decoder: Path) -> dict:
    paths = {"main": main, "secondary": secondary}
    data = {name: path.read_bytes() for name, path in paths.items()}
    sources = {}
    for name, (base, size, digest) in INPUTS.items():
        if len(data[name]) != size or sha(data[name]) != digest:
            raise ValueError(f"Expected the complete physically acquired GM1 {name} program")
        sources[name] = {"path": str(paths[name]), "bytes": size,
                         "sha256": digest, "file_zero_base": hex(base)}
    regions = []
    for name, component, start, end in REGIONS:
        base = INPUTS[component][0]
        disassembly, count = checked_disassembly(
            paths[component], data[component], decoder, base, start, end)
        regions.append({"name": name, "component": component,
                        "start": hex(start), "end_exclusive": hex(end),
                        "bytes": end-start, "instruction_count": count,
                        "native_sha256": sha(data[component][start-base:end-base]),
                        "raw_annotations_match_source": True,
                        "disassembly": disassembly})
    calls = []
    for component, address, target in CALLS:
        offset = address-INPUTS[component][0]
        opcode = data[component][offset]
        if opcode not in (0xCD, 0xDD):
            raise ValueError(f"Missing relative call at {address:#x}")
        actual = (address+struct.unpack_from(
            "<h" if opcode == 0xCD else "<i", data[component], offset+1)[0]) & 0xFFFFFFFF
        if actual != target:
            raise ValueError(f"Different call target at {address:#x}")
        calls.append({"component": component, "address": hex(address),
                      "target": hex(target)})
    strings = []
    for address, expected in ((0x403945DC, b"A:\\GM1.AHX\0"),
                              (0x403945E7, b"A:\\GM1E.AHX\0")):
        offset = address-INPUTS["main"][0]
        if data["main"][offset:offset+len(expected)] != expected:
            raise ValueError("AHX filename differs")
        strings.append({"address": hex(address), "bytes_hex": expected.hex()})
    return {
        "schema": 1,
        "scope": "GM1 AHX image-input and NOR-programming code; factory line and GM5 method unknown",
        "sources": sources,
        "verifier": {"path": "tools/gm1_factory_verify.py",
                     "sha256": sha(Path(__file__).read_bytes())},
        "decoder": {"path": str(decoder), "sha256": sha(decoder.read_bytes()),
                    "machine_argument": 332},
        "mechanical_checks": {"regions": regions, "calls": calls,
                              "literal_strings": strings},
        "manual_review": {
            "job": "Startup code calls 0x40158fe8 with modes zero and one on different predicates. Mode one bypasses the AHX reader. The other reviewed branch tries A:\\GM1.AHX, then A:\\GM1E.AHX; the staging destination is 0xb3000000. Successful fallback records mode three.",
            "reader": "0x4024f40f requires file size at least 0x600010. Its data loop advances 48 text bytes and 16 decoded bytes and calls parser 0x4024f63f.",
            "parser": "The parser requires S3 for data, decodes an eight-hex-digit address, compares it with the caller's sequential offset, stores at staging base plus that offset, and checks one's-complement additive checksum and CRLF. It returns seven for other S records; strict S7 validation and complete image acceptance are not established.",
            "programming": "On a successful read/extent check, call 0x40159204 enters 0x7bd23171. This reaches core 0x7bd235f9. A hardware-dependent branch erases through 0x7bd1b0b0 and programs staged bytes through 0x7bd1b116. Those helpers contain concrete 16-bit NOR command/data writes and status polling; no target routine was executed by this research.",
            "nor_addresses": "Reviewed command writes use 0x80000aaa and 0x80000554. A core branch supplies destination 0x80000000 and source 0xb3000000. The relation of this write alias to the USB read mapping is not independently measured.",
            "initial_provisioning": "This path resides in the existing main/secondary firmware. By itself it cannot explain first programming of a completely blank external flash. A preprogrammed bootstrap, silicon ROM loader or external programming method would have to supply executable code first.",
        },
        "limits": {
            "factory_line_method_identified": False,
            "gm5_equivalent_verified": False,
            "activation_procedure_verified": False,
            "complete_acceptance_conditions_proven": False,
            "usb_flash_writer_verified": False,
            "camera_contacted_by_this_verifier": False,
            "image_or_sd_marker_created": False,
            "flash_or_settings_written": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main_program", type=Path)
    parser.add_argument("secondary_program", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = report(args.main_program, args.secondary_program, args.decoder)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Verified {len(REGIONS)} native regions, {len(CALLS)} calls and two GM1 AHX filenames.")


if __name__ == "__main__":
    main()
