#!/usr/bin/env python3
"""Inventory literal cam.cgi fragments in decompiled Java/smali, entirely offline."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl

LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')
REVIEW = re.compile(r"\b(?:telnet|firmware|decrypt\w*|encrypt\w*|mdump\d?|memdump|"
                    r"readmem|readflash|bootrom|rom.?backup|shell)\b", re.I)


def inventory(root: Path) -> dict:
    if not root.is_dir():
        raise ValueError("Input must be a directory of decompiled Java/smali")
    urls = defaultdict(list)
    review = []
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".java", ".smali"}:
            continue
        data = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest()})
        for line_number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            for match in LITERAL.finditer(line):
                literal = match[1]
                location = {"file": relative, "line": line_number}
                if "cam.cgi" in literal:
                    urls[literal].append(location)
                if REVIEW.search(literal):
                    review.append(dict(location, literal=literal))
    if not files:
        raise ValueError("No Java/smali files found")
    entries = []
    for literal, locations in sorted(urls.items()):
        query = literal.partition("?")[2]
        entries.append({"literal": literal, "query_fields": parse_qsl(query, keep_blank_values=True),
                        "locations": locations})
    return {"schema": 1, "source_file_count": len(files), "files": files,
            "unique_cgi_literal_count": len(entries), "cgi_literals": entries,
            "review_candidates": review,
            "limitations": [
                "Literal extraction only: no Java/smali execution or call-graph analysis.",
                "Templates and fragments are retained verbatim; parameters passed to generic builders are not resolved.",
                "Comments and unreachable code can contain matches. File coverage is limited to the supplied directory.",
                "App-side strings do not establish GM5 support, camera memory access, vulnerabilities or firmware keys.",
                "No camera connection, command replay, decryption or firmware modification is performed."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = inventory(args.source)
        with args.out.open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"{report['source_file_count']} files; {report['unique_cgi_literal_count']} unique CGI literals")
    print(f"Report: {args.out}")


if __name__ == "__main__":
    main()
