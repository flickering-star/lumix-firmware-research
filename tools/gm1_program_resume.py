#!/usr/bin/env python3
"""Verify a GM1 main/secondary program prefix and continue in a fresh directory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from gm1_capture_verify import BASE, BLOCK, PROGRAM_BYTES, SECONDARY_BASE, SECONDARY_BYTES, verify_capture


def prepare_prefix(capture: Path, output: Path) -> dict:
    verified = verify_capture(capture, allow_incomplete=True)
    size = verified["verified_prefix_bytes"]
    if verified["mode"] in ("program", "resume") and int(verified["program_file_base"], 16) == BASE:
        limit, native_mode = PROGRAM_BYTES, "resume"
    elif (verified["mode"] in ("secondary", "secondary-window", "resume-secondary")
          and int(verified["program_file_base"], 16) == SECONDARY_BASE):
        limit, native_mode = SECONDARY_BYTES, "resume-secondary"
    else:
        raise ValueError("Expected a verified main/secondary program prefix")
    if not 0 < size <= limit or size % BLOCK:
        raise ValueError("Expected a nonempty, aligned prefix within the selected component")
    prefix = output / "verified-prefix.bin"
    with Path(verified["program_file"]).open("rb") as source, prefix.open("xb") as target:
        shutil.copyfileobj(source, target)
    if hashlib.sha256(prefix.read_bytes()).hexdigest() != verified["program_sha256"]:
        raise ValueError("Prefix changed while being copied; USB probe was not started")
    manifest = {"schema": 1, "parent_capture": verified["capture"],
                "prefix_bytes": size, "prefix_sha256": verified["program_sha256"],
                "native_resume_mode": native_mode, "program_file_base": verified["program_file_base"],
                "next_program_address": verified["next_program_address"],
                "parent_verification": verified}
    with (output / "resume-manifest.json").open("x") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="Previous main/secondary program or resume capture directory")
    parser.add_argument("--prepare-only", action="store_true", help="Verify/copy and compile; do not enumerate USB")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = Path(tempfile.mkdtemp(prefix="gm1-usb-resume-", dir=root / "captures"))
    try:
        manifest = prepare_prefix(args.capture, output)
        source = output / "probe-source.c"
        source.write_bytes((root / "tools/gm1_usb_probe_macos.c").read_bytes())
        binary = output / "gm1-usb-probe"
        subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-Wno-deprecated-declarations", str(source), "-framework", "IOKit",
                        "-framework", "CoreFoundation", "-o", str(binary)], check=True)
        subprocess.run([str(binary), "selftest"], check=True)
        with (output / "tool-hashes.json").open("x") as stream:
            json.dump({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, binary)}, stream, indent=2)
            stream.write("\n")
        print(f"Verified {manifest['prefix_bytes']} preserved bytes; next address {manifest['next_program_address']}.", flush=True)
        print(f"Resume evidence: {output}", flush=True)
        if args.prepare_only:
            print("Preparation complete; no USB access attempted.")
            return
        run = subprocess.run([str(binary), manifest["native_resume_mode"], str(output / "result"), str(output / "verified-prefix.bin")])
        try:
            report = verify_capture(output, allow_incomplete=True)
            with (output / "verification.json").open("x") as stream:
                json.dump(report, stream, indent=2)
                stream.write("\n")
            print(f"Independently verified {report['verified_prefix_bytes']} total program bytes.", flush=True)
        except (ValueError, OSError, KeyError) as error:
            print(f"Resume stopped before a verified continuation: {error}", flush=True)
            raise SystemExit(1)
        raise SystemExit(run.returncode)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Resume stopped: {error}\nEvidence retained: {output}\n")


if __name__ == "__main__":
    main()
