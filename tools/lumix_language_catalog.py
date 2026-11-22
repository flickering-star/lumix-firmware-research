#!/usr/bin/env python3
"""Inspect or patch the complete native language catalog in a decrypted program."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.lumix_updater.languages import PROFILES, apply_languages
from apps.lumix_updater.preservation import check_preserved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=PROFILES, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    source = args.input.read_bytes()
    revision = struct.unpack_from("<H", source, 0x6A0)[0]
    target, report = apply_languages(source, args.model)
    check_preserved(target, "program", args.model, revision)
    report.update(source_sha256=hashlib.sha256(source).hexdigest(),
                  target_sha256=hashlib.sha256(target).hexdigest())
    if args.out:
        args.out.mkdir(mode=0o700, parents=True, exist_ok=False)
        (args.out / "program.bin").write_bytes(target)
        (args.out / "language-catalog.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
