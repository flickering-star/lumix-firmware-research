#!/usr/bin/env python3
"""Read-only firmware triage; does not decrypt, repack, or identify a CPU by guess."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

MAGICS = {"ELF": b"\x7fELF", "gzip": b"\x1f\x8b\x08", "xz": b"\xfd7zXZ\0",
          "squashfs_le": b"hsqs", "cramfs_le": b"\x45\x3d\xcd\x28",
          "romfs": b"-rom1fs-", "uimage": b"\x27\x05\x19\x56",
          "fdt": b"\xd0\x0d\xfe\xed", "zip": b"PK\x03\x04"}
KEYWORDS = re.compile(r"aspect|65:24|cam\.cgi|pictsize|crop|panasonic|lumix|gm5|jpeg|display", re.I)


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    return -sum((n / len(data)) * math.log2(n / len(data)) for n in Counter(data).values())


def inspect(path: Path, window: int = 65536) -> dict:
    if window <= 0:
        raise ValueError("window must be positive")
    data = path.read_bytes()
    if not data:
        raise ValueError("Empty file is not a firmware image")
    signatures = []
    for name, magic in MAGICS.items():
        offset = 0
        count = 0
        samples = []
        while (offset := data.find(magic, offset)) >= 0:
            count += 1
            if len(samples) < 100:
                samples.append(offset)
            offset += 1
        if count:
            signatures.append({"name": name, "hits": count, "sample_offsets": samples,
                               "validated": False})
    strings = []
    count = 0
    for match in re.finditer(rb"[\x20-\x7e]{6,}", data):
        text = match.group().decode("ascii")
        if KEYWORDS.search(text):
            count += 1
            if len(strings) < 500:
                strings.append({"offset": match.start(), "text": text[:400]})
    return {"file": path.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "header_hex": data[:256].hex(), "tail_hex": data[-64:].hex(),
            "container_hint": "UPD magic only; layout not validated for GM5" if data[:4] == b"UPD\0" else "unknown",
            "entropy_bits_per_byte": round(entropy(data), 6),
            "entropy_windows": [{"offset": i, "size": len(data[i:i + window]),
                                 "entropy": round(entropy(data[i:i + window]), 6)}
                                for i in range(0, len(data), window)],
            "signature_candidates": signatures, "keyword_string_count": count,
            "keyword_strings": strings,
            "limitations": ["High entropy can mean compression or encryption; it does not identify a cipher.",
                            "Short magic matches can occur by chance; they are not extracted or validated objects.",
                            "No GM5 partition layout, CPU, checksums or signature mechanism has been established."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--window", type=int, default=65536)
    args = parser.parse_args()
    try:
        report = inspect(args.image, args.window)
        # Do not silently replace an earlier analysis, or accidentally overwrite the input.
        with args.out.open("x", encoding="utf-8") as out:
            json.dump(report, out, indent=2)
            out.write("\n")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"{report['file']}: {report['size']} bytes, SHA-256 {report['sha256']}")
    print(f"Container: {report['container_hint']}; report: {args.out}")


if __name__ == "__main__":
    main()
