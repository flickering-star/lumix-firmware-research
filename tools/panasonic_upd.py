#!/usr/bin/env python3
"""Inspect/carve the observed GM5 UPD layout; never repack or flash a camera.

Layout inferred from official GM5 1.1 bytes. Destination fields remain candidates
until a camera-side consumer is traced. The optional Olympus transform follows
the Altsoph/mx3 OE research: a fixed 16-byte permutation and XOR with 0xff.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zlib

BODY_START = 0x200
INNER_HEADER = 0x2A0
COUNT_OFFSET = 0x2E8
TABLE_OFFSET = 0x2EC
ENTRY_SIZE = 0x5C
PAYLOAD_START = 0x600
FLASH_BYTES_FROM_MANUAL = 32 * 1024 * 1024
OLYMPUS_ORDER = (1, 3, 0, 2, 6, 4, 7, 5, 11, 10, 9, 8, 13, 14, 12, 15)
INVERT = bytes(i ^ 255 for i in range(256))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def olympus_transform(data: bytes, *, inverse: bool = False) -> bytes:
    """Decode OE obfuscation, or reverse it; this does not identify GM5 encoding."""
    if len(data) % 16:
        raise ValueError("Olympus transform requires a multiple of 16 bytes")
    output = bytearray(len(data))
    for destination, source in enumerate(OLYMPUS_ORDER):
        if inverse:
            destination, source = source, destination
        output[destination::16] = data[source::16].translate(INVERT)
    return bytes(output)


def statistics(data: bytes) -> dict:
    counts = Counter(data)
    entropy = -sum((n / len(data)) * math.log2(n / len(data)) for n in counts.values())
    strings = list(re.finditer(rb"[\x20-\x7e]{12,}", data))
    keywords = re.compile(rb"panasonic|lumix|cam\.cgi|aspectratio|readmem|memdump|firmware", re.I)
    return {
        "entropy_bits_per_byte": round(entropy, 9),
        "zero_bytes": counts[0],
        "ff_bytes": counts[255],
        "ascii_strings_12plus": len(strings),
        "longest_ascii_string_12plus": max((m.end() - m.start() for m in strings), default=0),
        "keyword_strings": [
            {"offset": m.start(), "text": m.group().decode("ascii")[:300]}
            for m in strings if keywords.search(m.group())
        ][:30],
    }


def parse(data: bytes, *, expected_model: str = "GM5", allow_unsigned: bool = False) -> list[dict]:
    """Reject corrupt or structurally different containers before carving."""
    if len(data) < PAYLOAD_START:
        raise ValueError("Image is shorter than the observed GM5 header/directory")
    if expected_model not in ("GM1", "GM5"):
        raise ValueError("Unsupported expected model")
    if data[:4] != b"UPD\0" or data[12:24].split(b"\0", 1)[0] != expected_model.encode("ascii"):
        raise ValueError(f"Expected the observed {expected_model} UPD variant")
    if struct.unpack_from("<II", data, 4) != (BODY_START, BODY_START):
        raise ValueError("Unsupported outer header fields")
    if data[INNER_HEADER:INNER_HEADER + 0x40] != data[:0x40]:
        raise ValueError("Outer and inner header copies differ")
    marker = data[BODY_START:BODY_START + 12]
    if marker != b"panasonic\0\0\0" and not (allow_unsigned and marker == b"\0anasonic\0\0\0"):
        raise ValueError("Inner vendor marker differs")
    if struct.unpack_from("<I", data, 0x3C)[0] != len(data) - BODY_START:
        raise ValueError("Body length field does not match file length")
    if struct.unpack_from("<I", data, 0x40)[0] != zlib.crc32(data[BODY_START:]):
        raise ValueError("Outer body CRC32 mismatch")
    count = struct.unpack_from("<I", data, COUNT_OFFSET)[0]
    if not 0 < count <= (PAYLOAD_START - TABLE_OFFSET) // ENTRY_SIZE:
        raise ValueError("Directory count exceeds the observed directory bounds")
    entries = []
    names = set()
    for index in range(count):
        at = TABLE_OFFSET + index * ENTRY_SIZE
        raw_name, relative, size, destination, flags, field32, field16, reserved = struct.unpack_from(
            "<12s4I32s16s16s", data, at)
        name_bytes = raw_name.split(b"\0", 1)[0]
        if not re.fullmatch(rb"[A-Za-z0-9_]{1,12}", name_bytes):
            raise ValueError(f"Invalid component name at {at:#x}")
        name = name_bytes.decode("ascii")
        if name in names:
            raise ValueError("Duplicate component name")
        names.add(name)
        start = BODY_START + relative
        if not size or size % 16 or start < PAYLOAD_START or start + size > len(data):
            raise ValueError(f"Component {name} has an invalid payload range")
        entries.append({
            "index": index, "name": name, "entry_offset": at,
            "stored_file_offset": relative, "file_offset": start, "size": size,
            "destination_offset_candidate": destination, "flags_raw": flags,
            "field32_hex": field32.hex(), "field16_hex": field16.hex(),
            "reserved16_hex": reserved.hex(),
        })
    for left, right in zip(sorted(entries, key=lambda e: e["file_offset"]),
                           sorted(entries, key=lambda e: e["file_offset"])[1:]):
        if left["file_offset"] + left["size"] > right["file_offset"]:
            raise ValueError("Overlapping component payloads")
    return entries


def coverage(entries: list[dict]) -> dict:
    ranges = sorted((e["destination_offset_candidate"],
                     e["destination_offset_candidate"] + e["size"]) for e in entries)
    cursor = 0
    gaps = []
    for start, end in ranges:
        if start < cursor or end > FLASH_BYTES_FROM_MANUAL:
            return {"fits_manual_flash_without_overlap": False,
                    "meaning": "Destination-field interpretation unresolved"}
        if start > cursor:
            gaps.append({"start": cursor, "end_exclusive": start, "bytes": start - cursor})
        cursor = end
    if cursor < FLASH_BYTES_FROM_MANUAL:
        gaps.append({"start": cursor, "end_exclusive": FLASH_BYTES_FROM_MANUAL,
                     "bytes": FLASH_BYTES_FROM_MANUAL - cursor})
    covered = sum(end - start for start, end in ranges)
    return {"fits_manual_flash_without_overlap": True,
            "flash_bytes_from_manual": FLASH_BYTES_FROM_MANUAL,
            "payload_bytes": covered,
            "coverage_percent": 100 * covered / FLASH_BYTES_FROM_MANUAL,
            "uncovered_ranges": gaps,
            "meaning": "Hypothetical flash coverage if the destination fields are byte offsets; not CPU addresses"}


def inspect(data: bytes, *, check_olympus: bool = False) -> dict:
    entries = parse(data)
    for entry in entries:
        payload = data[entry["file_offset"]:entry["file_offset"] + entry["size"]]
        digest = sha256(payload)
        entry.update(encoded_sha256=digest, statistics=statistics(payload),
                     field32_matches_encoded_sha256=(digest == entry["field32_hex"]))
        if check_olympus:
            transformed = olympus_transform(payload)
            transformed_hash = sha256(transformed)
            entry["olympus_transform_check"] = {
                "transformed_sha256": transformed_hash,
                "statistics": statistics(transformed),
                "roundtrip_identical": olympus_transform(transformed, inverse=True) == payload,
                "field32_matches_transformed_sha256": transformed_hash == entry["field32_hex"],
                "meaning": "Candidate transform only; round-trip success is not proof of decoding",
            }
    ordered = sorted(entries, key=lambda e: e["file_offset"])
    contiguous = (ordered[0]["file_offset"] == PAYLOAD_START
                  and all(a["file_offset"] + a["size"] == b["file_offset"]
                          for a, b in zip(ordered, ordered[1:]))
                  and ordered[-1]["file_offset"] + ordered[-1]["size"] == len(data))
    return {
        "schema": 1, "size": len(data), "sha256": sha256(data), "model": "GM5",
        "format_scope": "Observed official GM5 1.1 UPD variant; structural validation only",
        "body_start": BODY_START, "payload_start": PAYLOAD_START,
        "body_crc32_hex": f"{zlib.crc32(data[BODY_START:]):08x}",
        "body_crc32_matches": True, "duplicated_header_matches": True,
        "header_hex": data[:0x44].hex(),
        "unknown_inner_64_byte_field_hex": data[0x220:0x260].hex(),
        "component_count": len(entries), "payloads_contiguously_cover_file_tail": contiguous,
        "components": entries, "destination_coverage_hypothesis": coverage(entries),
        "limitations": [
            "CRC32 validates accidental-corruption detection; it does not establish camera authentication.",
            "Destination field names and coverage are hypotheses until the updater consumer is traced.",
            "The 32-byte and 16-byte metadata fields are not established as hashes, keys, IVs or signatures.",
            "High entropy and 16-byte alignment do not identify a cipher or exclude compression.",
            "No executable architecture, plaintext firmware, camera command or flashable modification is produced.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--carve", type=Path, help="New directory for unchanged encoded components")
    parser.add_argument("--olympus-check", action="store_true")
    args = parser.parse_args()
    try:
        if args.out.exists() or (args.carve is not None and args.carve.exists()):
            raise ValueError("Output already exists; choose new paths")
        data = args.image.read_bytes()
        report = inspect(data, check_olympus=args.olympus_check)
        if args.carve is not None:
            args.carve.mkdir(parents=True, exist_ok=False)
            for entry in report["components"]:
                name = f"{entry['index']:02d}_{entry['name']}.encoded.bin"
                with (args.carve / name).open("xb") as output:
                    start = entry["file_offset"]
                    output.write(data[start:start + entry["size"]])
                entry["carved_file"] = name
        with args.out.open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"{report['model']}: {report['component_count']} components; body CRC32 verified")
    print(f"SHA-256 {report['sha256']}; report: {args.out}")


if __name__ == "__main__":
    main()
