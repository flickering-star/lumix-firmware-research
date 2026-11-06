#!/usr/bin/env python3
"""Verify GH2's vendor-SCSI dispatch and saved-service-state gates offline.

This reads one pinned firmware body and invokes the host MN103 decoder. It
neither builds USB packets nor opens a device. Native semantics are manually
reviewed; the small table lookup below is a host model, not firmware execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from gh2_debug_verify import BODY_SHA256, MAIN_BASE, checked_disassembly, verify_input


TABLE_ADDRESS = 0x407F1CF0
REGIONS = (
    ("bulk_out_mode_and_pending_gate", 0x401E762F, 0x401E76F4),
    ("cbw_fields_and_cdb_copy", 0x401EA3EA, 0x401EA4C2),
    ("scsi_lookup_and_vendor_gates", 0x401EA54B, 0x401EA647),
    ("pending_service_restore", 0x401E6B40, 0x401E6B77),
    ("special_scsi_subcommand_dispatch", 0x401F0741, 0x401F077A),
    ("alternate_pending_service_restore", 0x401F8F1A, 0x401F8F51),
    ("ptp_mode_and_pending_clear", 0x401F8740, 0x401F87EE),
    ("storage_mode_and_pending_clear", 0x401F87EE, 0x401F88F5),
    ("service_mode_and_pending_clear", 0x401F88F5, 0x401F8977),
)
CALLS = (
    (0x401EA25B, 0x401EA3EA),
    (0x401EA261, 0x401EA54B),
    (0x401EA5A6, 0x401EBBBD),
    (0x401EA5FD, 0x401F0741),
    (0x401F0767, 0x401F077A),
    (0x401F076E, 0x401F0927),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lookup(table: list, operation: int) -> int | None:
    if not 0 <= operation <= 229:
        return None
    key = operation+1
    slot = key & 31
    for _ in range(32):
        found, target = table[slot]
        if found == key:
            return target
        if found == 0:
            return None
        slot = (slot+1) & 31
    raise ValueError("Unexpected full/invalid SCSI hash table")


def make_report(body: Path, decoder: Path) -> dict:
    data = body.read_bytes()
    verify_input(data)
    off = TABLE_ADDRESS-MAIN_BASE
    table_bytes = data[off:off+32*8]
    table = list(struct.iter_unpack("<II", table_bytes))
    controls = []
    for operation, expected in ((0x00, 0x401EA647), (0x12, 0x401EA660),
                                (0xE2, 0x401EA592), (0xE4, 0x401EA592),
                                (0xE5, 0x401EA5ED), (0x70, None),
                                (0x9B, None), (0xE6, None)):
        actual = lookup(table, operation)
        if actual != expected:
            raise ValueError(f"SCSI lookup differs for {operation:#x}")
        controls.append({"operation": hex(operation),
                         "target": hex(actual) if actual is not None else None})

    regions = []
    for name, start, end in REGIONS:
        output, count = checked_disassembly(body, data, decoder, MAIN_BASE, start, end)
        regions.append({"name": name, "start": hex(start), "end_exclusive": hex(end),
                        "body_offset": hex(start-MAIN_BASE), "bytes": end-start,
                        "sha256": sha256(data[start-MAIN_BASE:end-MAIN_BASE]),
                        "instructions": count, "raw_annotations_match_source": True,
                        "disassembly": output})
    calls = []
    for address, expected in CALLS:
        at = address-MAIN_BASE
        if data[at] not in (0xCD, 0xDD):
            raise ValueError(f"Expected call at {address:#x}")
        target = (address+struct.unpack_from("<h" if data[at] == 0xCD else "<i", data, at+1)[0]) & 0xFFFFFFFF
        if target != expected:
            raise ValueError(f"Call target differs at {address:#x}")
        calls.append({"address": hex(address), "target": hex(target)})

    stores = []
    for reg, opcode in enumerate((0x82, 0x86, 0x8A, 0x8E)):
        pattern = bytes((0xFC, opcode))+struct.pack("<I", 0x744DD1F2)
        cursor = 0x400
        while True:
            at = data.find(pattern, cursor, 0x8C0400)
            if at < 0:
                break
            cursor = at+1
            stores.append({"address": hex(MAIN_BASE+at), "source_register": f"d{reg}"})
    stores.sort(key=lambda x: int(x["address"], 16))
    expected_stores = (0x401E6B6E, 0x401E76B4, 0x401EC10D, 0x401F86B4,
                       0x401F877E, 0x401F8849, 0x401F895B, 0x401F8F49)
    if [int(x["address"], 16) for x in stores] != list(expected_stores):
        raise ValueError("Immediate byte-store inventory differs")

    return {
        "schema": 1,
        "scope": "Static GH2 SCSI/service-state comparison; no GM5 reachability claim",
        "source": {"path": str(body), "sha256": BODY_SHA256, "bytes": len(data)},
        "verifier": {"path": "tools/gh2_scsi_verify.py", "sha256": sha256(Path(__file__).read_bytes()),
                     "decoder": str(decoder), "decoder_sha256": sha256(decoder.read_bytes())},
        "mechanical_checks": {"regions": regions, "calls": calls,
                              "scsi_lookup_controls": controls,
                              "immediate_byte_stores_to_pending_mode": stores},
        "scsi_table": {"address": hex(TABLE_ADDRESS), "body_offset": hex(off),
                       "bytes": len(table_bytes), "sha256": sha256(table_bytes),
                       "entries": [{"slot": i, "stored_key": key,
                                    "operation": hex(key-1) if key else None,
                                    "target": hex(target) if key else None}
                                   for i, (key, target) in enumerate(table)]},
        "manual_interpretation": {
            "cdb": "The CBW reader copies 4+4+4+1+1+1 header bytes followed by a 16-byte CDB to 0x744dd21c. The dispatcher uses CDB byte zero as its operation.",
            "e2_e4": "CDB opcodes 0xe2 and 0xe4 share 0x401ea592. They reach 0x401ebbbd only if saved mode 0x744dd1f2 is 2 or 4.",
            "e5": "CDB opcode 0xe5 reaches 0x401f0741 only if saved mode is 2. That helper dispatches CDB byte two values 0x3e and 0x3d. No packet was generated or transmitted.",
            "rejection": "The failed vendor gates reach 0x401ea61d, setting sense fields 5/0x20/0. This is a command-rejection path, not a memory read.",
            "pending_mode": "The reviewed nonzero immediate byte store to the saved mode, 0x401e76b4, copies the current descriptor mode after 0x401e7659 requires mode 2. It then temporarily selects storage mode 1. Restore routines require the saved state before returning to maintenance phase 3.",
            "inventory_limits": "The inventory covers exact FC 82/86/8a/8e absolute byte-store encodings in the main mapped program range. Other widths, computed destinations and aliases are not excluded; this is not a whole-program reachability proof.",
            "protocol_layers": "Raw maintenance operations 0x70 and 0x9b do not occur as operation keys in this SCSI table. Their presence in a different dispatcher does not make them direct SCSI CDB opcodes.",
        },
        "limits": {"normal_pc_mode_memory_read_established": False,
                   "gm5_equivalence_verified": False, "camera_contacted": False,
                   "firmware_executed_or_emulated": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError("Output already exists")
        report = make_report(args.body, args.decoder)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Verification failed: {error}\n")


if __name__ == "__main__":
    main()
