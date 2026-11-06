#!/usr/bin/env python3
"""Copy an exact tested GM5 candidate to its identified SD card, then eject it.

Explicit card UUID and fixed package digest; preserves the previous candidate locally.
No formatting, camera USB commands or installation is implemented here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import uuid

from gm5_emulator import sha
from gm5_reflash_control import validate_scope, save_json
from gm5_virtual_install import BACKUP, BACKUP_SHA, installed

PACKAGE = Path("work/gm5-reflash-control-2/GM5__V11.bin")
PACKAGE_SHA = "f978123c4eafb4a8bd0961c46ee013eb161babda6020eb1e3cbd0c68833dc4c8"
PREVIOUS_SHA = "45a7da844d497f9c52d90a1a7db73e2b54fb18a38d3a639b602320a7df269ce3"
POLICY_PACKAGE = Path("work/gm5-policy-zero-1/GM5__V11.bin")
POLICY_SHA = "86832e6eafa90b453894237805dafe128f61d346066f73a3752a8071d8286f16"
REGION_PACKAGE = Path("work/gm5-region-package-2/GM5__V11.bin")
REGION_SHA = "4954b517462b8ee5f900945496b882ddfa45f97b540f0d1dad6dcdf706ea50c7"


def disk_info(identifier: str) -> dict:
    return plistlib.loads(subprocess.check_output(["diskutil", "info", "-plist", identifier]))


def prepare(output: Path, candidate: str = "unchanged", card_uuid: str | None = None) -> dict:
    if card_uuid is None:
        raise ValueError("An explicitly identified --card-uuid is required")
    card_uuid = str(uuid.UUID(card_uuid)).upper()
    if candidate not in ("unchanged", "policy-zero", "language-unlock"):
        raise ValueError("Unsupported fixed candidate")
    policy = candidate == "policy-zero"
    region = candidate == "language-unlock"
    package, package_sha = (REGION_PACKAGE, REGION_SHA) if region else (
        (POLICY_PACKAGE, POLICY_SHA) if policy else (PACKAGE, PACKAGE_SHA))
    raw = package.read_bytes()
    if sha(raw) != package_sha or sha(BACKUP.read_bytes()) != BACKUP_SHA:
        raise ValueError("Exact tested package or protected backup changed")
    if region:
        from gm5_region_emulator import inputs, candidate as region_candidate
        from gm5_region_package import validate as validate_region
        main, _, _ = inputs()
        validate_region(raw, region_candidate(main))
        ready = json.loads(Path("evidence/gm5-region-readiness.json").read_text())
        if ready["package"]["sha256"] != package_sha or ready["repository_tests"]["passed"] != 81:
            raise ValueError("Exact region candidate readiness receipt differs")
    elif policy:
        from gm5_policy_package import patched, validate
        _, main, _, _ = installed()
        validate(raw, patched(main))
    else:
        validate_scope(raw)
    native_path = Path("work/gm5-region-package-native-2/summary.json" if region else (
        "work/gm5-policy-zero-native-1/summary.json" if policy else "work/gm5-reflash-control-native-2/summary.json"))
    native = json.loads(native_path.read_text())
    if native["passed"] != (6 if region else 8 if policy else 7) or native["package"]["sha256"] != package_sha:
        raise ValueError("Exact-package native validation receipt differs")
    if output.exists():
        raise ValueError("Evidence output exists")
    listing = plistlib.loads(subprocess.check_output(["diskutil", "list", "-plist", "external"]))
    matches = [p for disk in listing.get("AllDisksAndPartitions", []) for p in disk.get("Partitions", [])
               if p.get("VolumeUUID", "").upper() == card_uuid]
    if len(matches) != 1:
        raise ValueError("Exactly one expected external LUMIX card must be present")
    info = disk_info(matches[0]["DeviceIdentifier"])
    if (info.get("VolumeUUID", "").upper() != card_uuid or info.get("Internal") is not False
            or not info.get("RemovableMedia") or not info.get("Writable")
            or info.get("FilesystemType") != "msdos" or info.get("VolumeName") != "LUMIX"):
        raise ValueError("Expected writable removable external FAT LUMIX card")
    mount = Path(info["MountPoint"])
    destination = mount/"GM5__V11.bin"
    others = [p.name for p in mount.iterdir() if p.is_file() and p.suffix.lower() in (".bin", ".upd", ".fw")
              and p.name != destination.name]
    if others:
        raise ValueError(f"Other possible firmware files are present: {others}")
    previous = destination.read_bytes() if destination.exists() else None
    if previous is not None and sha(previous) not in (PREVIOUS_SHA, PACKAGE_SHA, POLICY_SHA, REGION_SHA):
        raise ValueError("Existing card candidate differs from either known control")
    usage = os.statvfs(mount)
    if usage.f_bavail*usage.f_frsize < len(raw)+1024*1024:
        raise ValueError("Insufficient card free space for a separate verified staging copy")
    prefix = "gm5-region-card-" if region else "gm5-policy-card-" if policy else "gm5-minimal-card-"
    capture = Path(tempfile.mkdtemp(prefix=prefix, dir="work"))
    capture.chmod(0o700)
    (capture/"preparation-source.py").write_bytes(Path(__file__).read_bytes())
    if previous is not None:
        old = capture/"previous-GM5__V11.bin"
        with old.open("xb") as stream: stream.write(previous)
        old.chmod(0o400)
        if old.read_bytes() != previous: raise ValueError("Local previous-candidate preservation failed")
    latest = disk_info(info["DeviceIdentifier"])
    if (latest.get("VolumeUUID", "").upper() != card_uuid
            or latest.get("MountPoint") != str(mount)
            or latest.get("ParentWholeDisk") != info["ParentWholeDisk"]):
        raise ValueError("Card identity changed before copying")
    staged = mount/".gm5-control-stage"
    with staged.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if staged.read_bytes() != raw:
        raise ValueError("Staging-file readback differs")
    os.replace(staged, destination)
    with destination.open("r+b") as stream: os.fsync(stream.fileno())
    if destination.read_bytes() != raw:
        raise ValueError("Final card-file readback differs")
    record = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
              "stage": "Prepared three-byte Japanese-language unlock; not installed" if region else (
                  "Prepared one-byte main policy-zero candidate; not installed" if policy else
                  "Prepared unchanged-installed-program2 physical control; not installed"),
              "candidate": candidate, "source": str(package), "destination": str(destination), "volume_uuid": card_uuid,
              "device_at_copy": info["DeviceIdentifier"], "whole_disk_at_copy": info["ParentWholeDisk"],
              "bytes": len(raw), "sha256": package_sha, "readback_byte_identical": True,
              "previous_sha256": sha(previous) if previous is not None else None,
              "previous_preserved_directory": str(capture), "component": "program" if policy or region else "program2",
              "plaintext_unchanged_from_installed_backup": not (policy or region),
              "one_byte_policy_patch": policy, "three_byte_language_patch": region,
              "settings_calibration_payloads_included": False,
              "source_sha256": sha(Path(__file__).read_bytes()), "card_formatted": False,
              "camera_contacted_by_copy_tool": False, "physical_flash_performed": False,
              "safely_ejected": False}
    save_json(capture/"copied-before-eject.json", record)
    result = subprocess.run(["diskutil", "eject", "/dev/"+info["ParentWholeDisk"]],
                            check=True, capture_output=True, text=True)
    record["safely_ejected"] = True
    record["eject_result"] = result.stdout.strip()
    save_json(output, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--candidate", choices=("unchanged", "policy-zero", "language-unlock"), default="unchanged")
    parser.add_argument("--card-uuid", required=True, help="UUID of the owner's explicitly identified external LUMIX card")
    args = parser.parse_args()
    result = prepare(args.out, args.candidate, args.card_uuid)
    print(f"Verified {result['bytes']} bytes, SHA256 {result['sha256']}; card safely ejected")


if __name__ == "__main__":
    main()
