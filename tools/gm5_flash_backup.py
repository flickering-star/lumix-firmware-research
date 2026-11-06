#!/usr/bin/env python3
"""Read fixed GM5 NOR/main/program2 intervals; verified resume only.

Uses the established 100 ms pacing and stops on the first unexpected response.
Captures are private local files. No RAM policy or firmware write is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from gm1_capture_verify import BASE, BLOCK, GM5_NOR_BYTES, SECONDARY_BASE, SECONDARY_BYTES, verify_capture


def prepare_prefix(capture: Path, output: Path, component: str = "nor") -> dict:
    verified = verify_capture(capture, allow_incomplete=True)
    size = verified["verified_prefix_bytes"]
    if component == "nor":
        modes, base, limit, native_mode = ("nor-backup", "resume-nor-backup"), BASE, GM5_NOR_BYTES, "resume-nor-backup"
    elif component == "program2":
        modes, base, limit, native_mode = ("secondary", "resume-secondary"), SECONDARY_BASE, SECONDARY_BYTES, "resume-secondary"
    elif component == "program":
        modes, base, limit, native_mode = ("program", "resume"), BASE, 0x800000, "resume"
    else:
        raise ValueError("Unknown fixed GM5 component")
    if (verified["model"] != "DMC-GM5" or verified["mode"] not in modes
            or int(verified["program_file_base"], 16) != base):
        raise ValueError(f"Expected a verified GM5 {component} backup prefix")
    if not 0 < size < limit or size % BLOCK:
        raise ValueError("Expected an incomplete, nonempty, block-aligned backup prefix")
    prefix = output / "verified-prefix.bin"
    with Path(verified["program_file"]).open("rb") as source, prefix.open("xb") as target:
        shutil.copyfileobj(source, target)
    if hashlib.sha256(prefix.read_bytes()).hexdigest() != verified["program_sha256"]:
        raise ValueError("Prefix changed while copied; camera access has not started")
    manifest = {"schema": 1, "parent_capture": verified["capture"], "prefix_bytes": size,
                "prefix_sha256": verified["program_sha256"], "native_resume_mode": native_mode,
                "program_file_base": verified["program_file_base"],
                "next_program_address": verified["next_program_address"], "parent_verification": verified}
    with (output / "resume-manifest.json").open("x") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", type=Path, help="Previous verified GM5 NOR backup capture")
    parser.add_argument("--component", choices=("nor", "program", "program2"), default="nor",
                        help="Fixed whole-NOR, 8 MiB main or program2 interval; never an arbitrary address")
    parser.add_argument("--prepare-only", action="store_true", help="Compile/check only; no USB enumeration")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = Path(tempfile.mkdtemp(prefix="gm5-flash-backup-" if args.component == "nor" else f"gm5-{args.component}-readback-",
                                   dir=root / "captures"))
    output.chmod(0o700)
    try:
        prefix = prepare_prefix(args.resume, output, args.component) if args.resume else None
        for src, name in (("gm5_flash_backup_macos.c", "probe-source.c"),
                          ("gm1_usb_probe_macos.c", "gm1_usb_probe_macos.c")):
            (output / name).write_bytes((root / "tools" / src).read_bytes())
        binary = output / "gm5-flash-backup"
        definitions = ["-DPROBE_GM5_MAIN_ONLY"] if args.component == "program" else []
        target = 0x800000 if args.component == "program" else SECONDARY_BYTES if args.component == "program2" else GM5_NOR_BYTES
        target_path = output/"build-target.json"
        target_path.write_text(json.dumps({"component": args.component, "target_bytes": target,
                                          "compiler_definitions": definitions}, indent=2)+"\n")
        subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-Wno-deprecated-declarations", *definitions, str(output / "probe-source.c"),
                        "-framework", "IOKit", "-framework", "CoreFoundation", "-o", str(binary)], check=True)
        subprocess.run([str(binary), "selftest"], check=True)
        with (output / "tool-hashes.json").open("x") as stream:
            json.dump({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (output / "probe-source.c", output / "gm1_usb_probe_macos.c", binary, target_path)}, stream, indent=2)
            stream.write("\n")
        print(f"Backup evidence: {output}", flush=True)
        if prefix:
            print(f"Preserved {prefix['prefix_bytes']} verified bytes; next {prefix['next_program_address']}.", flush=True)
        if args.prepare_only:
            print("Preparation complete; no USB access attempted.")
            return
        action = ("resume-secondary" if prefix else "backup-secondary") if args.component == "program2" else (
            "resume" if prefix else "backup")
        command = [str(binary), action, str(output / "result")]
        if prefix:
            command.append(str(output / "verified-prefix.bin"))
        run = subprocess.run(command)
        try:
            verified = verify_capture(output, allow_incomplete=True)
            with (output / "verification.json").open("x") as stream:
                json.dump(verified, stream, indent=2)
                stream.write("\n")
            print(f"Packet-verified {verified['verified_prefix_bytes']} / {target} bytes; complete={verified['complete']}.", flush=True)
        except (ValueError, OSError, KeyError) as error:
            raise ValueError(f"Capture needs inspection before resume: {error}") from error
        raise SystemExit(run.returncode)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Backup stopped: {error}\nEvidence retained: {output}\n")


if __name__ == "__main__":
    main()
