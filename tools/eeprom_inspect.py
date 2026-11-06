#!/usr/bin/env python3
"""Inspect or compare Lumix EEPROM text exports offline; never edit or restore.

Recognizes the observed GM1 EEPROM DATA INFORMATION layout. Export addresses
are word coordinates in a selected area, not established CPU or flash addresses.
String contents are omitted from inspection reports; comparisons include changed
word values, so keep reports local when the settings may contain personal data.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import struct
import zipfile

MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_WORDS = 0x10000
NAME = re.compile(r"([A-Za-z0-9_-]+)([FU])\.TXT", re.I)
ROW = re.compile(r"H([0-9a-f]{3,4}) ((?:[0-9a-f]{4},){16})", re.I)
KEYWORDS = ("debug", "telnet", "shell", "console", "mdump", "memdump",
            "readmem", "readflash", "bootrom", "uart", "wifi", "wlan")
LANGUAGE_SUFFIX = (0x0000, 0x270F, 0x6363, 0x270F, 0x6363)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse(data: bytes) -> dict:
    if len(data) > MAX_TEXT_BYTES:
        raise ValueError("EEPROM text exceeds the inspection limit")
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("Expected an ASCII EEPROM text export") from exc
    if len(lines) < 8 or lines[0] != "###### EEPROM DATA INFORMATION ######":
        raise ValueError("Missing observed EEPROM export header")
    patterns = (
        r"#@1:([0-9a-f]{2})\s+: AREA\s+: (UPDATE|FIX ADJUST)\s*",
        r"#@2:([0-9a-f]{2})\s+: TYPE\s+: (ROM)\s*",
        r"#@3:([0-9a-f]{4,8})\s+: START ADDRESS\s+: 0x([0-9a-f]+)h\s*",
        r"#@4:([0-9a-f]{4,8})\s+: DATA SIZE\s+: 0x([0-9a-f]+)h\s*",
    )
    fields = []
    for line, pattern in zip(lines[1:5], patterns):
        match = re.fullmatch(pattern, line, re.I)
        if not match:
            raise ValueError("Unrecognized EEPROM metadata line")
        fields.append(match.groups())
    area = int(fields[0][0], 16)
    area_name = fields[0][1].upper()
    storage_type = int(fields[1][0], 16)
    start, count = int(fields[2][0], 16), int(fields[3][0], 16)
    if start != int(fields[2][1], 16) or count != int(fields[3][1], 16):
        raise ValueError("Repeated address/size metadata disagree")
    if (area, area_name) not in {(0x10, "UPDATE"), (0x20, "FIX ADJUST")} or storage_type:
        raise ValueError("Unsupported area or storage type; do not infer another memory space")
    if (not 0 < count <= MAX_WORDS or start % 16 or count % 16
            or start + count > MAX_WORDS):
        raise ValueError("Invalid word range in EEPROM metadata")
    if (lines[5] != "#####################################"
            or lines[6].split() != [f"L{i:x}" for i in range(16)]):
        raise ValueError("Unrecognized EEPROM column labels")
    words = []
    for line in lines[7:]:
        match = ROW.fullmatch(line)
        if not match:
            raise ValueError("Malformed EEPROM data row")
        if int(match[1], 16) * 16 != start + len(words):
            raise ValueError("Missing, duplicate or out-of-order EEPROM row")
        words.extend(int(word, 16) for word in match[2].split(",")[:-1])
        if len(words) > count:
            raise ValueError("EEPROM rows exceed the declared word count")
    if len(words) != count:
        raise ValueError("EEPROM rows do not cover the declared word count")
    return {"area_code": area, "area_name": area_name, "type_code": storage_type,
            "start_word": start, "word_count": count, "row_count": count // 16,
            "source_bytes": len(data), "source_sha256": digest(data), "words": words}


def load_tables(path: Path) -> dict:
    """Read selected TXT members without extracting archive paths or other data."""
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Input exceeds the inspection limit")
    tables = {}

    def add(name: str, data: bytes) -> None:
        match = NAME.fullmatch(PurePosixPath(name).name)
        if not match:
            raise ValueError("Expected a model name ending in F.TXT or U.TXT")
        model, suffix = match[1].upper(), match[2].upper()
        table = parse(data)
        if table["area_code"] != {"F": 0x20, "U": 0x10}[suffix]:
            raise ValueError("Filename suffix and EEPROM area disagree")
        key = model + suffix
        if key in tables:
            raise ValueError("Duplicate model/area in input")
        tables[key] = dict(table, model=model, filename=name)

    if path.suffix.lower() != ".zip":
        if path.stat().st_size > MAX_TEXT_BYTES:
            raise ValueError("EEPROM text exceeds the inspection limit")
        add(path.name, path.read_bytes())
    else:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if (len(members) > 512
                    or sum(member.file_size for member in members) > 64 * 1024 * 1024):
                raise ValueError("Archive exceeds inspection limits")
            for member in members:
                if member.is_dir() or not NAME.fullmatch(PurePosixPath(member.filename).name):
                    continue
                if member.file_size > MAX_TEXT_BYTES:
                    raise ValueError("EEPROM text member exceeds the inspection limit")
                add(member.filename, archive.read(member))
    if not tables:
        raise ValueError("No model F.TXT/U.TXT EEPROM exports found")
    return tables


def coordinate(word: int) -> dict:
    return {"export_word_address": word, "row": f"H{word // 16:03x}",
            "column": f"L{word % 16:x}"}


def inspect(table: dict) -> dict:
    words = table["words"]
    report = {key: value for key, value in table.items() if key != "words"}
    report.update(decoded_bytes=2 * len(words), zero_words=words.count(0),
                  ffff_words=words.count(0xffff), unique_word_values=len(set(words)))
    variants = {}
    for order, fmt in (("little", "<"), ("big", ">")):
        binary = struct.pack(f"{fmt}{len(words)}H", *words)
        counts = Counter(binary)
        hits = []
        for keyword in KEYWORDS:
            for encoding in ("ascii", "utf-16-le", "utf-16-be"):
                for match in re.finditer(re.escape(keyword.encode(encoding)), binary.lower()):
                    hits.append({"keyword": keyword, "encoding": encoding,
                                 "relative_byte_offset": match.start()})
        markers = {}
        for marker in ("Panasonic", "LUMIX", "DMC-" + table.get("model", "")):
            offsets = [m.start() for m in re.finditer(re.escape(marker.encode()), binary)]
            if offsets:
                markers[marker] = offsets
        variants[order] = {
            "sha256": digest(binary),
            "entropy_bits_per_byte": round(-sum(
                count / len(binary) * math.log2(count / len(binary))
                for count in counts.values()), 9),
            "ascii_strings_6plus": len(re.findall(rb"[\x20-\x7e]{6,}", binary)),
            "diagnostic_keyword_hits": hits, "known_text_markers": markers,
        }
    report["word_serializations"] = variants
    report["language_pattern_candidates"] = [
        dict(coordinate(table["start_word"] + i), value_hex=f"{words[i]:04x}",
             relative_byte_offset=2 * i, interpretation="Published language-edit pattern; not a debug flag")
        for i in range(len(words) - 5) if tuple(words[i + 1:i + 6]) == LANGUAGE_SUFFIX
    ]
    groups = defaultdict(list)
    for at in range(0, len(words) - 0x100 + 1, 0x100):
        block = tuple(words[at:at + 0x100])
        if any(block):
            groups[block].append(table["start_word"] + at)
    report["identical_nonzero_256_word_blocks"] = [
        {"start_word_addresses": offsets, "words_per_block": 0x100}
        for offsets in groups.values() if len(offsets) > 1
    ]
    report["limitations"] = [
        "Word coordinates identify the exported area, not a physical flash or CPU address.",
        "Both byte orders are reported; readable markers do not establish processor endianness.",
        "Repeated settings are not proven backup banks, defaults or custom profiles.",
        "String absence cannot exclude numeric flags or diagnostics elsewhere in firmware.",
        "String contents and complete word arrays are omitted; no checksum/authentication claim is made.",
    ]
    return report


def compare(left: dict, right: dict) -> dict:
    for key in ("model", "area_code", "type_code", "start_word", "word_count"):
        if left[key] != right[key]:
            raise ValueError(f"Cannot compare incompatible exports: {key} differs")
    changes = [dict(coordinate(left["start_word"] + i), before_hex=f"{a:04x}",
                    after_hex=f"{b:04x}", xor_hex=f"{a ^ b:04x}")
               for i, (a, b) in enumerate(zip(left["words"], right["words"])) if a != b]
    return {"model": left["model"], "area_code": left["area_code"],
            "area_name": left["area_name"], "before_sha256": left["source_sha256"],
            "after_sha256": right["source_sha256"], "changed_words": len(changes),
            "changes": changes, "meaning": "Observed data changes; no setting meaning inferred"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("inspect", help="Report structure and strings without their contents")
    command.add_argument("input", type=Path)
    command.add_argument("--out", type=Path, required=True)
    command = commands.add_parser("compare", help="Compare matching models/areas at word coordinates")
    command.add_argument("before", type=Path)
    command.add_argument("after", type=Path)
    command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError("Output already exists; choose a new report path")
        if args.command == "inspect":
            tables = load_tables(args.input)
            result = {"schema": 1, "input_sha256": digest(args.input.read_bytes()),
                      "table_count": len(tables), "tables": [inspect(t) for t in tables.values()]}
        else:
            before, after = load_tables(args.before), load_tables(args.after)
            if before.keys() != after.keys():
                raise ValueError("Input table/model sets differ")
            result = {"schema": 1, "tables": [compare(before[key], after[key]) for key in before]}
        with args.out.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
            output.write("\n")
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"Saved offline EEPROM report: {args.out}")


if __name__ == "__main__":
    main()
