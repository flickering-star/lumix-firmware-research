#!/usr/bin/env python3
"""Verify the GH2 1.2 diagnostic-code findings against one pinned plaintext.

This is a version-specific evidence verifier, not an automatic shell detector.
It reads a local decoded body and invokes the host MN103 disassembler. It has no
device, network, packet-generation, firmware-execution or flashing operations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


BODY_SHA256 = "7501269737da3fcba4b9483d9171b291b9c96bf08780eaa83b24128cffd512ea"
BODY_MD5 = "35cb77e2ef08df9ef334ff1e496b0b02"
MAIN_BASE = 0x3FFFFC00
SECONDARY_BASE = 0x7B2FFC00
TABLE_OFFSET = 0x7F2464
TABLE_ADDRESS = 0x407F2064

# Names/semantics below come from manual static review. The verifier checks the
# table-to-branch-to-reader links and records the unchanged instructions.
READERS = (
    (0x35, 0x401EF189, 0x401EF8AF, "settings_buffer_word",
     "16-bit word index; area selects a bounded settings buffer"),
    (0x38, 0x401EF181, 0x401EF9AE, "settings_flash_word",
     "16-bit word index; areas 0x10/0x11/0x20 select bounded EEPROM flash banks"),
    (0x46, 0x401EF1C5, 0x401EFC76, "register_window_word",
     "16-bit word index below 0xffff; reads 0x9c000000 + 2*index"),
    (0x70, 0x401EF265, 0x401F01D3, "flash_relative_word",
     "32-bit little-endian word index; reads two bytes at 0x40000000 + 2*index"),
    (0x75, 0x401EF26D, 0x401F022B, "ram_relative_word",
     "32-bit little-endian word index; reads two bytes at 0xb4000000 + 2*index"),
    (0x9B, 0x401EF27D, 0x401F02CB, "absolute_word",
     "32-bit little-endian byte address; directly loads a 16-bit word"),
)

REGIONS = (
    ("main_reset", MAIN_BASE, 0x40000000, 0x40000038, False),
    ("secondary_code_copy", MAIN_BASE, 0x400046E7, 0x40004769, True),
    ("secondary_reset", SECONDARY_BASE, 0x7BBC0000, 0x7BBC00E3, False),
    ("secondary_libc", SECONDARY_BASE, 0x7BC519C8, 0x7BC51AAC, False),
    ("secondary_maintenance_tag_check", SECONDARY_BASE, 0x7BCFC527, 0x7BCFC550, False),
    ("main_maintenance_tag_check", MAIN_BASE, 0x400D7959, 0x400D79C0, False),
    ("receive_state_dispatch", MAIN_BASE, 0x401EEE32, 0x401EEEBA, False),
    ("primary_command_dispatch", MAIN_BASE, 0x401EF0A5, 0x401EF0C6, True),
    ("reader_dispatch_branches", MAIN_BASE, 0x401EF255, 0x401EF28D, True),
    ("response_helpers", MAIN_BASE, 0x401EF37C, 0x401EF49B, False),
    ("settings_buffer_word_read", MAIN_BASE, 0x401EF8AF, 0x401EF92F, False),
    ("settings_flash_word_read", MAIN_BASE, 0x401EF9AE, 0x401EFA2B, True),
    ("register_window_word_read", MAIN_BASE, 0x401EFC76, 0x401EFCD1, False),
    ("flash_relative_word_read", MAIN_BASE, 0x401F01D3, 0x401F022B, True),
    ("ram_relative_word_read", MAIN_BASE, 0x401F022B, 0x401F0283, True),
    ("absolute_word_read", MAIN_BASE, 0x401F02CB, 0x401F0313, True),
    ("log_file_export", MAIN_BASE, 0x400F0283, 0x400F02EF, False),
)


def verify_input(data: bytes) -> None:
    if len(data) != 15598592 or hashlib.sha256(data).hexdigest() != BODY_SHA256:
        raise ValueError("Expected the verified decoded GH2 1.2 body; input differs")
    if hashlib.md5(data).hexdigest() != BODY_MD5:
        raise ValueError("GH2 plaintext MD5 differs from the official package value")


def checked_disassembly(body: Path, data: bytes, decoder: Path,
                        base: int, start: int, end: int) -> tuple[str, int]:
    output = subprocess.check_output(
        [str(decoder.resolve()), str(body), hex(base), hex(start), hex(end), "332"],
        text=True,
    )
    cursor = start
    count = 0
    for line in output.splitlines():
        match = re.fullmatch(r"([0-9a-f]{8})  (.*)\t; ([0-9a-f]+)", line)
        if not match:
            raise ValueError(f"Unrecognized disassembler output: {line!r}")
        at = int(match[1], 16)
        raw = bytes.fromhex(match[3])
        if at != cursor or data[at-base:at-base+len(raw)] != raw:
            raise ValueError(f"Disassembly raw bytes/continuity differ at {at:#x}")
        if "unknown" in match[2]:
            raise ValueError(f"Unknown instruction in reviewed region at {at:#x}")
        cursor += len(raw)
        count += 1
    if cursor != end:
        raise ValueError(f"Region ends at {cursor:#x}, expected {end:#x}")
    return output, count


def make_report(body: Path, decoder: Path) -> dict:
    data = body.read_bytes()
    verify_input(data)
    table = struct.unpack_from("<212I", data, TABLE_OFFSET)
    commands = []
    for opcode, branch, handler, name, semantics in READERS:
        if table[opcode] != branch:
            raise ValueError(f"Command {opcode:#x} branch differs")
        offset = branch - MAIN_BASE
        if data[offset] != 0xCD:
            raise ValueError(f"Command {opcode:#x} expected a relative call")
        target = branch + struct.unpack_from("<h", data, offset+1)[0]
        if target != handler:
            raise ValueError(f"Command {opcode:#x} reader target differs")
        commands.append({"command": hex(opcode), "branch": hex(branch),
                         "handler": hex(handler), "name": name,
                         "static_review": semantics})

    regions = []
    for name, base, start, end, embed in REGIONS:
        output, count = checked_disassembly(body, data, decoder, base, start, end)
        raw = data[start-base:end-base]
        record = {"name": name, "file_zero_base": hex(base),
                  "start": hex(start), "end_exclusive": hex(end),
                  "body_offset": hex(start-base), "bytes": len(raw),
                  "native_sha256": hashlib.sha256(raw).hexdigest(),
                  "instruction_count": count,
                  "raw_annotations_match_source": True,
                  "disassembly_sha256": hashlib.sha256(output.encode()).hexdigest()}
        if embed:
            record["disassembly"] = output
        regions.append(record)

    folded = data.lower()
    literal_search = []
    for term in ("debug", "console", "shell", "telnet", "uart", "assert",
                 "memdump", "readmem", "readflash", "dump", "password",
                 "baud", "115200", "help", "login", "command", "SDLOG"):
        literal_search.append({
            "term": term,
            "counts": {encoding: folded.count(term.lower().encode(encoding))
                       for encoding in ("ascii", "utf-16-le", "utf-16-be")},
        })

    return {
        "schema": 1,
        "scope": "Static GH2 1.2 diagnostic consumers; not GM5 compatibility or hardware validation",
        "source": {"path": str(body), "bytes": len(data), "sha256": BODY_SHA256,
                   "md5": BODY_MD5, "official_package_md5_matches": True,
                   "provenance": "evidence/gh2-settings-consumers.json"},
        "verifier": {"path": "tools/gh2_debug_verify.py",
                     "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "decoder": {"path": str(decoder),
                    "sha256": hashlib.sha256(decoder.read_bytes()).hexdigest(),
                    "build_receipt": "work/toolchain/mn10300/build.json",
                    "machine_argument": 332},
        "secondary_segment": {
            "body_offset": "0x8c0400", "flash_source_start": "0x408c0000",
            "flash_source_end": "0x40ae0000", "copied_bytes": 0x220000,
            "linked_start": "0x7bbc0000", "file_zero_base": hex(SECONDARY_BASE),
            "copy_destination_arithmetic": "0xbbbc0000",
            "support": "Reset vector, USBMNT string reference, libc loops and startup copy agree; alias hardware details not established",
        },
        "dispatch": {
            "entry": "0x401ef0a5", "command_source_state": "0x744dcbe8",
            "table": hex(TABLE_ADDRESS), "body_offset": hex(TABLE_OFFSET),
            "entries": len(table),
            "table_sha256": hashlib.sha256(data[TABLE_OFFSET:TABLE_OFFSET+len(table)*4]).hexdigest(),
            "selected_links_verified": len(commands), "readers": commands,
        },
        "regions": regions,
        "literal_search": {
            "method": "Case-insensitive literal bytes, all offsets in the complete decoded body; UTF-16 searches are not independent alignment proofs",
            "results": literal_search,
            "context_review": {
                "help_ascii": "One substring of a longer printable byte run at body offset 0xe5291c; no prompt/parser context identified",
                "login_ascii": "One substring of a longer printable byte run at body offset 0xe0a96c; no prompt/parser context identified",
                "command_ascii": "All 14 matches are in SD-card driver message tags, not a text command interpreter",
                "sdlog": "Filename and log text at 0x22ff9c..0x230017; no direct little-endian main-mapping pointer to SDLOG.TXT identified",
            },
        },
        "log_exports": {
            "entry": "0x400f0283", "condition": "input byte equals zero",
            "files": [
                {"name": "A:\\develop.bin", "source": "0x74010b38", "bytes": 1024},
                {"name": "A:\\histlog.bin", "source": "0x7400cb38", "bytes": 16384},
                {"name": "A:\\userlog.bin", "source": "0x74019b3c", "bytes": 16384,
                 "entry": "0x400f02c3"},
            ],
            "full_activation_conditions_traced": False,
        },
        "interpretation": {
            "interactive_text_shell_established": False,
            "binary_memory_read_handlers_present": True,
            "bounds_note": "No address-range comparison identified inside 0x70, 0x75 or 0x9b reader bodies; upstream activation and transport conditions remain unresolved",
            "physical_usb_reachability_verified": False,
            "gm5_equivalence_verified": False,
            "firmware_or_camera_instructions_executed": False,
            "camera_contacted": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path)
    parser.add_argument("--decoder", type=Path,
                        default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = make_report(args.body, args.decoder)
        # Preserve any earlier evidence report by requiring a fresh path.
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Verification failed: {error}\n")


if __name__ == "__main__":
    main()
