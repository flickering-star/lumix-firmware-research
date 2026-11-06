#!/usr/bin/env python3
"""Check crypto-library bytes in the acquired GM1 program; no USB access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from gh2_debug_verify import checked_disassembly, verify_input

BASE = 0x40000000
PREFIX_BYTES = 6 * 1024 * 1024
PREFIX_SHA256 = "7e78740681383e6b62636026683682455c486e2a281cffd80222846ce48de4d6"


def report(source: Path, gh2: Path, decoder: Path) -> dict:
    data = source.read_bytes()
    if len(data) < PREFIX_BYTES or hashlib.sha256(data[:PREFIX_BYTES]).hexdigest() != PREFIX_SHA256:
        raise ValueError("Expected the acquired GM1 six-MiB prefix")
    control = gh2.read_bytes()
    verify_input(control)
    tables = []
    for name, address, offset in (("aes_sbox", 0x4042FAD0, 0x20B388),
                                  ("aes_inverse_sbox", 0x4042FBD0, 0x20B488)):
        raw = data[address-BASE:address-BASE+256]
        if raw != control[offset:offset+256]:
            raise ValueError("AES table differs from independently verified GH2 control")
        tables.append({"name": name, "address": hex(address), "bytes": 256,
                       "sha256": hashlib.sha256(raw).hexdigest(), "matches_gh2_control": True})
    initial_values = (0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
                      0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19)
    operands = (0x402885A3, 0x402885AA, 0x402885B3, 0x402885BC,
                0x402885C5, 0x402885CE, 0x402885D7, 0x402885E0)
    for address, value in zip(operands, initial_values):
        if struct.unpack_from("<I", data, address-BASE)[0] != value:
            raise ValueError("SHA-256 initial-state constant differs")
    call = 0x40286EE5
    if data[call-BASE] != 0xCD or call + struct.unpack_from("<h", data, call-BASE+1)[0] != 0x40286DCF:
        raise ValueError("AES key-schedule call differs")
    regions = []
    for name, start, end in (("aes_key_schedule", 0x40286DCF, 0x40286EE1),
                             ("aes_schedule_wrapper", 0x40286EE1, 0x40286EEA),
                             ("aes_inverse_table_load", 0x402871D0, 0x402871D6),
                             ("sha256_initial_state", 0x402885A1, 0x402885F7)):
        text, count = checked_disassembly(source, data, decoder, BASE, start, end)
        regions.append({"name": name, "start": hex(start), "end_exclusive": hex(end),
                        "native_sha256": hashlib.sha256(data[start-BASE:end-BASE]).hexdigest(),
                        "instruction_count": count, "raw_annotations_match_source": True,
                        "disassembly": text})
    return {"schema": 1, "scope": "GM1 crypto-library identification; updater consumers/key/signatures remain untraced",
            "source": {"path": str(source), "prefix_bytes": PREFIX_BYTES,
                       "prefix_sha256": PREFIX_SHA256, "acquisition": "captures/gm1-usb-resume-3atwz8co"},
            "verifier": {"path": "tools/gm1_crypto_verify.py",
                         "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "control": {"path": str(gh2), "sha256": hashlib.sha256(control).hexdigest()},
            "tables": tables, "sha256_initial_values": [hex(v) for v in initial_values],
            "regions": regions,
            "limits": ["Library presence does not establish the algorithm selected by the GM1/GM5 updater.",
                       "No update key or public-key signature requirement is established.",
                       "The verifier reads files and runs only the host disassembler."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--gh2", type=Path, default=Path("work/legacy-control/GH2__V12.body.decoded.bin"))
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = report(args.source, args.gh2, args.decoder)
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("Verified GM1 AES tables/key-schedule region and SHA-256 initializer.")


if __name__ == "__main__":
    main()
