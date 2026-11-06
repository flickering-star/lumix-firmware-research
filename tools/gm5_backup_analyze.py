#!/usr/bin/env python3
"""Verify a complete GM5 NOR capture and carve private native-emulator inputs.

This tool reads saved files only. It does not contact a camera or create an
update package. Exact earlier physical windows must match the complete dump.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from gm1_capture_verify import BASE, GM5_NOR_BYTES, verify_capture
from gm5_emulator import MAIN, SECONDARY

REFERENCES = (
    "gm5-usb-window-Hqd18GAn",
    "gm5-usb-updater-window-qX2cjoe6",
    "gm5-usb-initializer-ujPIpkWZ",
    "gm5-usb-update-entry-Fd6ZOqs0",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def analyze(capture: Path, output: Path) -> dict:
    verified = verify_capture(capture)
    if (not verified["complete"] or verified["model"] != "DMC-GM5"
            or verified["mode"] not in ("nor-backup", "resume-nor-backup")
            or int(verified["program_file_base"], 16) != BASE
            or verified["verified_prefix_bytes"] != GM5_NOR_BYTES):
        raise ValueError("A complete, packet-verified GM5 32 MiB NOR capture is required")
    raw = Path(verified["program_file"]).read_bytes()
    if len(raw) != GM5_NOR_BYTES or sha(raw) != verified["program_sha256"]:
        raise ValueError("Complete NOR file changed after verification")
    references = []
    for name in REFERENCES:
        old = verify_capture(capture.resolve().parent/name)
        before = Path(old["program_file"]).read_bytes()
        offset = int(old["program_file_base"], 16)-BASE
        if offset < 0 or raw[offset:offset+len(before)] != before:
            raise ValueError(f"Earlier physical flash window differs: {name}")
        references.append({"capture": name, "flash_start": old["program_file_base"],
                           "bytes": len(before), "sha256": sha(before), "matches_complete_dump": True})
    components = []
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    for name, offset, size, linked, official in (
        ("program", 0, 0x800000, 0x40000000, MAIN),
        ("program2", 0x1400000, 0x360000, 0x7BC00000, SECONDARY),
    ):
        stock = Path(official[0]).read_bytes()
        if len(stock) != size or sha(stock) != official[2]:
            raise ValueError(f"Verified official {name} input differs")
        body = raw[offset:offset+size]
        path = output/f"installed-{name}.bin"
        path.write_bytes(body)
        path.chmod(0o600)
        components.append({"name": name, "path": str(path.resolve()), "flash_start": hex(BASE+offset),
                           "linked_address": hex(linked), "bytes": len(body), "sha256": sha(body),
                           "official_sha256": sha(stock), "byte_identical_to_official": body == stock,
                           "byte_differences_at_same_offsets": sum(a != b for a, b in zip(body, stock)),
                           "comparison_note": "Same-offset count includes alignment shifts; it is not a count of semantic changes."})
    report = {"schema": 1, "scope": "Complete GM5 mapped NOR readback and private emulator component extraction",
              "capture_verification": verified, "earlier_flash_windows": references, "components": components,
              "physical_policy_source": {"address": "0x406b1bdc", "value": raw[0x6B1BDC]},
              "verifier_sha256": sha(Path(__file__).read_bytes()), "camera_contacted": False,
              "limits": ["Sequential acquisition, with three matching anchors after the battery replacement; not an atomic snapshot.",
                         "Covers the mapped NOR range only, not every independent storage device or volatile RAM.",
                         "Private program slices are native-emulator inputs, not flashable update packages.",
                         "No tested hardware recovery programmer or firmware writer is supplied."]}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = analyze(args.capture, args.out)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Analysis stopped: {error}\n")
    print(f"Verified {report['capture_verification']['verified_prefix_bytes']} NOR bytes; private program slices: {args.out}")


if __name__ == "__main__":
    main()
