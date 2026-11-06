#!/usr/bin/env python3
"""Check the staged Git tree for private artifacts, binaries and credentials."""
from __future__ import annotations

from pathlib import PurePosixPath
import re
import subprocess

TEXT_SUFFIXES = {".md", ".py", ".c", ".m", ".h", ".sh", ".json", ".txt", ".igen", ".yml", ".yaml"}
TEXT_NAMES = {".gitignore", ".gitattributes", "COPYING", "LICENSE", "NOTICE", "Makefile"}
PRIVATE_ROOTS = {"work", "captures", "firmware", ".ssh", ".env"}
PATTERNS = (
    ("private-key material", re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("GitHub access token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("personal absolute path", re.compile("/"+"Users"+r"/(?!USERNAME\b)[^/\s<>]+/")),
    ("large embedded hex payload", re.compile(r"\b[0-9a-fA-F]{2048,}\b")),
)


def audit() -> list[str]:
    listing = subprocess.check_output(["git", "ls-files", "--stage", "-z"])
    errors = []
    count = 0
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, blob, stage = metadata.decode().split()
        path = raw_path.decode()
        name = PurePosixPath(path)
        count += 1
        if (stage != "0" or mode not in ("100644", "100755")
                or name.parts[0] in PRIVATE_ROOTS
                or name.name == "PRIVATE.zip"
                or name.suffix not in TEXT_SUFFIXES and name.name not in TEXT_NAMES):
            errors.append(f"{path}: unapproved artifact path/type")
            continue
        raw = subprocess.check_output(["git", "cat-file", "blob", blob])
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{path}: non-text content")
            continue
        if any(byte < 32 and byte not in (9, 10, 13) for byte in raw):
            errors.append(f"{path}: binary/control characters")
        for label, pattern in PATTERNS:
            if pattern.search(text):
                errors.append(f"{path}: {label}")
    print(f"Audited {count} staged-tree files; {len(errors)} findings.")
    return errors


if __name__ == "__main__":
    findings = audit()
    for finding in findings:
        print(finding)
    raise SystemExit(bool(findings))
