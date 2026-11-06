#!/usr/bin/env python3
"""Apply a hash-pinned firmware patch recipe offline; never contacts a camera."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_recipe(data: bytes, recipe: dict) -> tuple[bytes, dict]:
    if recipe.get("schema") != 1 or len(data) != recipe["input_bytes"]:
        raise ValueError("Recipe schema or input length differs")
    matching = [v for v in recipe["variants"] if v["input_sha256"] == sha(data)]
    if len(matching) != 1:
        raise ValueError("Input SHA-256 is not an exact supported baseline")
    variant = matching[0]
    result = bytearray(data)
    occupied = set()
    if not variant["patches"]:
        raise ValueError("Recipe has no patches")
    for patch in variant["patches"]:
        offset = int(patch["offset"], 0)
        before, after = bytes.fromhex(patch["before"]), bytes.fromhex(patch["after"])
        interval = set(range(offset, offset+len(before)))
        if (not 0 < len(before) == len(after) <= 64 or before == after
                or offset < 0 or offset+len(before) > len(data) or occupied & interval):
            raise ValueError("Invalid or overlapping patch interval")
        if data[offset:offset+len(before)] != before:
            raise ValueError("Original patch bytes differ")
        result[offset:offset+len(after)] = after
        occupied.update(interval)
    output = bytes(result)
    if sha(output) != variant["output_sha256"]:
        raise ValueError("Output SHA-256 differs from reviewed recipe")
    return output, {"schema": 1, "recipe_id": recipe["id"], "model": recipe["model"],
                    "input_sha256": sha(data), "output_sha256": sha(output),
                    "bytes": len(output), "patches": variant["patches"],
                    "camera_contacted": False, "update_container_created": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="New private output directory")
    args = parser.parse_args()
    try:
        output, report = apply_recipe(args.input.read_bytes(), json.loads(args.recipe.read_text()))
        args.out.mkdir(parents=True, mode=0o700, exist_ok=False)
        path = args.out/"program.patched.bin"
        with path.open("xb") as stream:
            stream.write(output)
        path.chmod(0o400)
        report["recipe_sha256"] = sha(args.recipe.read_bytes())
        (args.out/"report.json").write_text(json.dumps(report, indent=2)+"\n")
        print(f"Prepared {path}; SHA-256 {report['output_sha256']}")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Patch refused: {error}\n")


if __name__ == "__main__":
    main()
