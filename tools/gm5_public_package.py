#!/usr/bin/env python3
"""Reproduce the exact tested GM5 language package from locally supplied inputs.

Offline only. Requires the exact official template and reviewed patched main;
no body-specific NOR backup, historical capture paths or SD-card UUID is needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

from gm5_prompt_package import KEY
from gm5_region_package import validate
from panasonic_upd import parse, PAYLOAD_START, TABLE_OFFSET, ENTRY_SIZE
from panasonic_v2_decode import OFFICIAL_HASHES

MAIN_SHA = "5364cde77a78a40fce270bf1c24642a9fbd2e6d7d3501bb38d8b806548a48d67"
PACKAGE_SHA = "4954b517462b8ee5f900945496b882ddfa45f97b540f0d1dad6dcdf706ea50c7"


def build(template_path: Path, main_path: Path, codec: Path, output: Path) -> dict:
    template, main = template_path.read_bytes(), main_path.read_bytes()
    digest = lambda data: hashlib.sha256(data).hexdigest()
    if digest(template) != OFFICIAL_HASHES["GM5"] or len(main) != 0x800000 or digest(main) != MAIN_SHA:
        raise ValueError("Only the reviewed official GM5 1.1 template and patched main are supported")
    entry = next(e for e in parse(template) if e["name"] == "program")
    subprocess.run([str(codec.resolve()), "--selftest"], check=True, capture_output=True)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    encoded = output/"encoded-main.data"
    subprocess.run([str(codec.resolve()), "--encrypt", str(main_path.resolve()), str(encoded.resolve()),
                    KEY, entry["field16_hex"], "0", str(len(main))], check=True, capture_output=True)
    ciphertext = encoded.read_bytes()
    if len(ciphertext) != len(main):
        raise ValueError("Encoded component length differs")
    raw = bytearray(template[:PAYLOAD_START])+ciphertext
    raw[0x200] = 0
    raw[0x220:0x260] = bytes(64)
    struct.pack_into("<HH", raw, 0x1C, 0x0114, 0x0114)
    struct.pack_into("<I", raw, 0x3C, len(raw)-0x200)
    raw[0x2A0:0x2E0] = raw[:0x40]
    struct.pack_into("<I", raw, 0x2E8, 1)
    raw[TABLE_OFFSET:PAYLOAD_START] = bytes(PAYLOAD_START-TABLE_OFFSET)
    struct.pack_into("<12s4I32s16s16s", raw, TABLE_OFFSET, b"program", PAYLOAD_START-0x200,
                     len(main), 0, 3, hashlib.sha256(main).digest(), bytes.fromhex(entry["field16_hex"]),
                     bytes.fromhex(entry["reserved16_hex"]))
    struct.pack_into("<I", raw, 0x40, zlib.crc32(raw[0x200:]))
    validate(bytes(raw), main)
    if digest(raw) != PACKAGE_SHA:
        raise ValueError("Encoded package differs from the physically tested candidate")
    package = output/"GM5__V11.bin"
    package.write_bytes(raw)
    decoded = output/"decoded-roundtrip.data"
    subprocess.run([str(codec.resolve()), str(package.resolve()), str(decoded.resolve()), KEY,
                    entry["field16_hex"], str(PAYLOAD_START), str(len(main))], check=True, capture_output=True)
    if decoded.read_bytes() != main:
        raise ValueError("Codec round trip differs")
    package.chmod(0o400)
    record = {"schema": 1, "package_sha256": PACKAGE_SHA, "main_sha256": MAIN_SHA,
              "bytes": len(raw), "roundtrip_exact": True,
              "matches_physically_tested_package": True, "camera_contacted": False,
              "template_sha256": digest(template), "codec_sha256": digest(codec.read_bytes()),
              "builder_sha256": digest(Path(__file__).read_bytes()),
              "calibration_settings_or_resource_payloads_included": False}
    (output/"build-report.json").write_text(json.dumps(record, indent=2)+"\n")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--main", required=True, type=Path)
    parser.add_argument("--codec", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = build(args.template, args.main, args.codec, args.out)
        print(f"Reproduced exact tested GM5 package: {report['package_sha256']}")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Package refused: {error}\n")


if __name__ == "__main__":
    main()
