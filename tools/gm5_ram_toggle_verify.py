#!/usr/bin/env python3
"""Independently verify fixed-address GM5 RAM toggle/enable/restore captures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from gm1_capture_verify import GM5_CONTROL, check_frame, request, wire

BLOCKS = [
    (0x4061E400, "dispatch-table.bin"), (0x4036CC00, "dispatch-branch.bin"),
    (0x4036E000, "write-handler.bin"), (0x702FF800, "usb-mode.bin"),
    (0x70A68400, "ram-before.bin"),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def report(capture: Path) -> dict:
    result = capture / "result"
    summary = json.loads((result / "summary.json").read_text())
    mode = summary["mode"]
    count = summary["ram_halfword_writes_attempted"]
    events = [json.loads(line) for line in (result / "events.jsonl").read_text().splitlines()]
    allowed_counts = {"ram-toggle-test": (2,), "ram-enable": (1,), "ram-restore": (0, 1)}
    if (mode not in allowed_counts or count not in allowed_counts[mode] or summary["exit_status"]
            or summary["ram_restore_verified"] != (mode != "ram-enable")):
        raise ValueError("Not a successful bounded RAM experiment")
    if any(e["event"] == "api_result" and e["result"] != "0x00000000" for e in events):
        raise ValueError("API failure in claimed successful experiment")
    identities = [e for e in events if e["event"] == "registry_identity"]
    if len(identities) != 1 or identities[0].get("product_name") != "DMC-GM5" or any(
            identities[0].get(k) != v for k, v in {"vendor_id": 0x04DA, "product_id": 0x2370,
            "interface": [255, 160, 176], "configuration": 1, "alternate_setting": 0, "endpoints": 3}.items()):
        raise ValueError("GM5 registry identity differs")
    transfers = [e for e in events if e["event"] in
                 ("control_attempt", "bulk_out_attempt", "bulk_in_type", "bulk_in")]
    sequence = [("settings", 0x3F80+i) for i in range(16)]
    sequence += [("block", item) for item in BLOCKS]
    if mode in ("ram-toggle-test", "ram-enable"):
        sequence += [("write", 0), ("block", (0x70A68400, "ram-cleared.bin"))]
    if mode in ("ram-toggle-test", "ram-restore") and count:
        sequence += [("write", 1), ("block", (0x70A68400, "ram-restored.bin"))]
    if len(transfers) != len(sequence)*6:
        raise ValueError("Unexpected transfer count")
    settings = bytearray()
    saved = {}
    for index, (kind, value) in enumerate(sequence):
        group = transfers[index*6:(index+1)*6]
        if [e["event"] for e in group] != ["control_attempt", "bulk_out_attempt", "control_attempt",
                                          "bulk_in_type", "control_attempt", "bulk_in"]:
            raise ValueError("Two-stage USB ordering differs")
        if [group[n]["setup_hex"] for n in (0, 2, 4)] != [
                "4000000000000000", "4000000001000000", "4000000001000000"]:
            raise ValueError("Unexpected USB preparation request")
        outgoing, incoming = wire(group[1]), wire(group[5])
        expected_type = 1 if kind == "block" else 8
        size = 1030 if kind == "block" else 16
        if wire(group[3]) != bytes([expected_type]):
            raise ValueError("Response type differs")
        check_frame(incoming, size, expected_type)
        if kind == "write":
            expected = bytearray.fromhex("0800ff9c9084a6700000000000000000")
            expected[8] = value
            expected[14] = sum(expected[1:14]) & 255
            if outgoing != expected or incoming[3] != 1 or any(incoming[4:14]):
                raise ValueError("Write address/value/frame or successful ACK differs")
        else:
            parsed = request(outgoing, "DMC-GM5")
            if kind == "settings":
                if parsed["operation"] != 0x38 or parsed["index"] != value or incoming[3] != 0x36 or any(incoming[6:14]):
                    raise ValueError("Settings control differs")
                settings.extend(incoming[4:6])
            else:
                address, filename = value
                if parsed["operation"] != 0x5C or parsed["index"] != (address-0x40000000)//1024 or incoming[3] != 5:
                    raise ValueError("Readback address/frame differs")
                data = incoming[4:-2]
                if data != (result / filename).read_bytes():
                    raise ValueError("Saved readback differs from USB bytes")
                saved[filename] = data
    if settings != GM5_CONTROL or settings != (result / "fixed-markers.bin").read_bytes():
        raise ValueError("Repeated GM5 settings control differs")
    if (struct.unpack_from("<I", saved["dispatch-table.bin"], 0x304)[0] != 0x4036CE71
            or saved["dispatch-branch.bin"][0x271:0x279] != bytes.fromhex("cd1512f018df0004")
            or sha(saved["write-handler.bin"][0x86:0xF7]) != "a292e0ed6f22e631cb7876bf74e6491b4b5a5a642f15f8160425ad112a80c354"
            or saved["usb-mode.bin"][0x5D] != 0):
        raise ValueError("Native handler/mode guard differs")
    values = [struct.unpack_from("<H", saved[name], 0x90)[0]
              for name in ("ram-before.bin", "ram-cleared.bin", "ram-restored.bin") if name in saved]
    expected_values = {"ram-toggle-test": [1, 0, 1], "ram-enable": [1, 0],
                       "ram-restore": [0, 1] if count else [1]}[mode]
    if values != expected_values:
        raise ValueError("RAM transition/restoration differs")
    intents = [e for e in events if e["event"] == "ram_halfword_write_intent"]
    expected_intents = [("0x70a68490", value) for kind, value in sequence if kind == "write"]
    if [(e["address"], e["value"]) for e in intents] != expected_intents:
        raise ValueError("Write-intent log differs")
    if summary["control_requests_attempted"] != len(sequence)*3 or summary["bulk_writes_attempted"] != len(sequence):
        raise ValueError("Summary transfer counters differ")
    if summary["program_block_bytes"] != len(saved)*1024 or summary["settings_bytes"] != 32:
        raise ValueError("Summary readback extent differs")
    return {
        "schema": 1, "scope": "Demonstrated volatile GM5 RAM flag control; firmware flashing remains untested",
        "capture": str(capture), "mode": mode, "complete": True, "model": "DMC-GM5",
        "address": "0x70a68490", "halfword_values_read_back": values,
        "halfword_writes_verified": count, "original_value_restored": mode != "ram-enable",
        "full_ram_block_restored_identically": saved["ram-before.bin"] == saved.get("ram-restored.bin"),
        "changed_offsets_after_clear": [hex(i) for i, (a, b) in enumerate(
            zip(saved["ram-before.bin"], saved.get("ram-cleared.bin", saved["ram-before.bin"]))) if a != b],
        "native_guards": {"operation": "0x9c", "dispatch_table": "0x4061e494",
                          "branch": "0x4036ce71", "handler": "0x4036e086", "usb_mode": 0},
        "settings_words_verified": 16, "block_responses_verified": len(saved), "write_acks_verified": count,
        "artifacts": {name: {"bytes": len(data), "sha256": sha(data)} for name, data in saved.items()},
        "events_sha256": sha((result / "events.jsonl").read_bytes()),
        "ram_source_sha256": sha((capture / "ram-control-source.c").read_bytes()),
        "shared_source_sha256": sha((capture / "shared-read-source.c").read_bytes()),
        "verifier": {"path": "tools/gm5_ram_toggle_verify.py", "sha256": sha(Path(__file__).read_bytes())},
        "limits": {"flash_written": False, "settings_written": False,
                   "unsigned_image_accepted": False, "sd_update_invoked": False,
                   "persistence_across_disconnect_or_reboot_tested": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = report(args.capture)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    values = " -> ".join(str(value) for value in result["halfword_values_read_back"])
    print(f"Verified {result['mode']}: {result['write_acks_verified']} write ACK(s), readbacks {values}.")


if __name__ == "__main__":
    main()
