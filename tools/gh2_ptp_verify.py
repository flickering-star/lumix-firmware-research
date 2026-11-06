#!/usr/bin/env python3
"""Recheck GH2 PTP dispatch and its GM5 operation-list control offline.

No camera operations or packets are produced. Native semantics are manually
reviewed; the lookup below models only the inspected table dispatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from gh2_debug_verify import BODY_SHA256, MAIN_BASE, checked_disassembly, verify_input


REGIONS = (
    ("opcode_range_and_hash_dispatch", 0x401F1E85, 0x401F1ED2),
    ("device_info_format_selection", 0x401F1ED2, 0x401F1EEE),
    ("normal_operation_list_copy", 0x401F265F, 0x401F2676),
    ("normal_operation_list_serialization", 0x401F284A, 0x401F286D),
    ("alternate_operation_list_copy", 0x401F2A00, 0x401F2A17),
    ("unsupported_dispatch_branch", 0x401F1FC9, 0x401F1FD7),
    ("operation_not_supported_response", 0x401F4835, 0x401F4841),
)
CALLS = ((0x401F1EDD, 0x401F2A00), (0x401F1EE6, 0x401F265F),
         (0x401F1FC9, 0x401F4835))
NORMAL = (0x1001, 0x1002, 0x1003, 0x1004, 0x1005, 0x1006, 0x1007, 0x1008,
          0x1009, 0x100A, 0x100C, 0x100D, 0x1014, 0x1015, 0x1016, 0x101B)
ALTERNATE = (0x1001, 0x1002, 0x1003, 0x1004, 0x1005, 0x1006, 0x1007, 0x1008,
             0x1009, 0x100A, 0x100B, 0x100F, 0x1010, 0x1014, 0x1015, 0x1016,
             0x101B, 0x9801, 0x9802, 0x9803, 0x9805)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lookup(pairs: list[tuple[int, int]], opcode: int) -> int:
    if not 0x1001 <= opcode <= 0x9805:
        return 0x401F1FC9
    key = opcode-0x1000
    slot = key & 31
    for _ in range(32):
        found, target = pairs[slot]
        if found == key:
            return target
        if found == 0:
            return 0x401F1FC9
        slot = (slot+1) & 31
    raise ValueError("Unexpected full PTP hash table")


def make_report(body: Path, decoder: Path, gm5_observation: Path) -> dict:
    data = body.read_bytes()
    verify_input(data)
    observation = json.loads(gm5_observation.read_text())
    measured = tuple(int(s, 16) for s in observation["device_info"]["operations"])
    if measured != NORMAL or observation["device_info"]["dataset_sha256"] != "35306eead9b8a752e7659d455925a7c5d2b38918e23594ea3022f97d602a8aa1":
        raise ValueError("Recorded GM5 operation-list control differs")
    regions = []
    for name, start, end in REGIONS:
        output, count = checked_disassembly(body, data, decoder, MAIN_BASE, start, end)
        regions.append({"name": name, "start": hex(start), "end_exclusive": hex(end),
                        "body_offset": hex(start-MAIN_BASE), "bytes": end-start,
                        "sha256": sha(data[start-MAIN_BASE:end-MAIN_BASE]),
                        "instructions": count, "raw_annotations_match_source": True,
                        "disassembly": output})
    calls = []
    for at, target in CALLS:
        off = at-MAIN_BASE
        if data[off] != 0xCD or (at+struct.unpack_from("<h", data, off+1)[0]) & 0xFFFFFFFF != target:
            raise ValueError("PTP relative-call link differs")
        calls.append({"address": hex(at), "target": hex(target)})
    lists = []
    for address, expected in ((0x407F2A2E, NORMAL), (0x407F2A67, ALTERNATE)):
        actual = struct.unpack_from("<"+"H"*len(expected), data, address-MAIN_BASE)
        if actual != expected:
            raise ValueError("PTP operation-list bytes differ")
        lists.append({"address": hex(address), "entries": len(actual),
                      "operations": [hex(x) for x in actual]})
    start = 0x407F2C28-MAIN_BASE
    table = data[start:start+256]
    pairs = list(struct.iter_unpack("<II", table))
    present = {key+0x1000 for key, target in pairs if key}
    if present != set(NORMAL) | set(ALTERNATE) or len(present) != 23:
        raise ValueError("PTP table inventory differs")
    lookups = []
    for key, target in pairs:
        if not key:
            continue
        opcode = key+0x1000
        if lookup(pairs, opcode) != target:
            raise ValueError("PTP hash lookup differs")
        lookups.append({"opcode": hex(opcode), "branch": hex(target)})
    absent = []
    for opcode in (0x70, 0x9B, 0x1000, 0x100E, 0x9102, 0x9103, 0x9104, 0x9703, 0x9806):
        if lookup(pairs, opcode) != 0x401F1FC9:
            raise ValueError("Expected unsupported lookup differs")
        absent.append(hex(opcode))
    return {
        "schema": 1, "scope": "GH2 PTP dispatch comparison; no new GM5 commands established",
        "source": {"path": str(body), "bytes": len(data), "sha256": BODY_SHA256},
        "verifier": {"path": "tools/gh2_ptp_verify.py", "sha256": sha(Path(__file__).read_bytes()),
                     "decoder": str(decoder), "decoder_sha256": sha(decoder.read_bytes())},
        "mechanical_checks": {"regions": regions, "calls": calls,
                              "operation_lists": lists,
                              "dispatch_table": {"address": "0x407f2c28", "slots": 32,
                                                 "sha256": sha(table), "active_entries": lookups,
                                                 "active_set_equals_union_of_lists": True},
                              "lookup_model_controls": {"present_operations": 23,
                                                        "unsupported_examples": absent}},
        "gm5_positive_control": {"report": str(gm5_observation), "model": "DMC-GM5",
                                 "device_version": "1.1", "dataset_sha256": observation["device_info"]["dataset_sha256"],
                                 "all_16_measured_operations_equal_gh2_normal_list": True,
                                 "new_device_query_performed": False},
        "manual_review": {
            "dispatch": "The reviewed dispatcher bounds the operation to 0x1001..0x9805, subtracts 0x1000, hashes with mask 31, probes eight-byte key/branch records and returns unsupported on an empty slot. It jumps indirectly to the matched branch.",
            "device_info": "Operation 0x1001 reaches 0x401f1ed2. State word 0x744ddf36 equal to 5 chooses 0x401f2a00 and its 21-entry alternate list; the other branch calls 0x401f265f, whose reviewed serialization copies the 16-entry normal list with count 16. This state word is not the descriptor-mode byte or the saved maintenance mode.",
            "unsupported": "Branch 0x401f1fc9 calls 0x401f4835, which stores response code 0x2005 at RAM 0x744dccc6. The selected native regions support the lookup model; this is not a full CPU or camera emulator.",
            "limits": "All 23 table operations belong to the two embedded lists. No manufacturer-specific opcode or diagnostic memory-reader target appears in this reviewed table. This does not exhaust other USB transports or prove any GM5 implementation beyond the measured operation-list equality.",
        },
        "limits": {"camera_contacted": False, "packet_produced": False,
                   "target_code_executed": False, "plaintext_dump_obtained": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--gm5-observation", type=Path, default=Path("evidence/gm5-usb-pc-ptp.json"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError("Output already exists")
        report = make_report(args.body, args.decoder, args.gm5_observation)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Verification failed: {error}\n")


if __name__ == "__main__":
    main()
