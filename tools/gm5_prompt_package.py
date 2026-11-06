#!/usr/bin/env python3
"""Build locally verified GM5 unsigned prompt-test containers, host files only.

Every encrypted payload remains byte-identical to the official GM5 1.1 image.
Only the marker, optionally header policy flags, and outer CRC are changed.
Each candidate is independently decoded again and all eight hashes must pass.
This tool never contacts a camera, writes an SD card or starts an update.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

from panasonic_upd import parse
from panasonic_v2_decode import OFFICIAL_HASHES
from panasonic_signature_verify import verify as verify_signature

KEY = "f630c6cfad87f78031327ba55193fa4c"
PUBLIC = bytes.fromhex(
    "274fab5aed54d05774099739f1aa0518329a64a9ad9772986bf201148adc2e0e7"
    "64e7f31e1495235a85473d02db6c21d7b298f9f9e30a62009a994276b4134d4")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def build(image: Path, decoder: Path, output: Path, advertised_version: int | None = None) -> dict:
    original = image.read_bytes()
    if sha(original) != OFFICIAL_HASHES["GM5"]:
        raise ValueError("Expected the pinned intact official GM5 1.1 image")
    entries = parse(original)
    if len(entries) != 8:
        raise ValueError("Expected all eight GM5 components")
    signed_start, signed_end = 0x2A0, 0x2A0+76+92*len(entries)
    if not verify_signature(PUBLIC, hashlib.sha256(original[signed_start:signed_end]).digest(),
                            original[0x220:0x260]):
        raise ValueError("Official directory signature failed")
    official_versions = struct.unpack_from("<HH", original, 0x1C)
    if advertised_version is not None and not 0x0111 < advertised_version <= 0xFFFF:
        raise ValueError("Advertised version must be a halfword above the installed 0x0111 control")
    control = subprocess.check_output([str(decoder.resolve()), "--selftest"], text=True).strip()
    if output.exists():
        raise ValueError("Choose a new output directory")
    output.mkdir(parents=True, exist_ok=False)
    (output / "builder-source.py").write_bytes(Path(__file__).read_bytes())
    variants = []
    specifications = (("standard-version", False), ("relaxed-version", True)) if advertised_version is None else (
        (f"advertised-{advertised_version:04x}", False),)
    for name, relax in specifications:
        candidate = bytearray(original)
        candidate[0x200] = 0
        if advertised_version is not None:
            struct.pack_into("<HH", candidate, 0x1C, advertised_version, advertised_version)
        flags_before = struct.unpack_from("<I", original, 0x20)[0]
        flags_after = flags_before & ~15 if relax else flags_before
        struct.pack_into("<I", candidate, 0x20, flags_after)
        candidate[0x2A0:0x2E0] = candidate[:0x40]
        struct.pack_into("<I", candidate, 0x40, zlib.crc32(candidate[0x200:]))
        parsed = parse(bytes(candidate), allow_unsigned=True)
        if parsed != entries:
            raise ValueError("Component directory changed unexpectedly")
        signature_valid = verify_signature(PUBLIC, hashlib.sha256(candidate[signed_start:signed_end]).digest(),
                                           candidate[0x220:0x260])
        signed_input_unchanged = candidate[signed_start:signed_end] == original[signed_start:signed_end]
        if signature_valid != signed_input_unchanged:
            raise ValueError("Directory signature positive/negative result differs from expected header edits")
        path = output / name / "GM5__V11.bin"
        path.parent.mkdir()
        with path.open("xb") as stream:
            stream.write(candidate)
        components = []
        with tempfile.TemporaryDirectory(prefix="gm5-prompt-decode-") as directory:
            for entry in parsed:
                start, length = entry["file_offset"], entry["size"]
                if candidate[start:start+length] != original[start:start+length]:
                    raise ValueError("A firmware payload changed")
                plaintext = Path(directory) / (entry["name"]+".bin")
                subprocess.run([str(decoder.resolve()), str(path), str(plaintext), KEY,
                                entry["field16_hex"], str(start), str(length)],
                               check=True, capture_output=True, text=True)
                raw = plaintext.read_bytes()
                digest = sha(raw)
                if len(raw) != length or digest != entry["field32_hex"]:
                    raise ValueError(f"Candidate {entry['name']} does not decode to its declared SHA-256")
                components.append({"name": entry["name"], "bytes": length,
                                   "ciphertext_unchanged": True, "plaintext_sha256": digest,
                                   "declared_sha256_matches": True})
        changes = [{"file_offset": hex(i), "official": a, "candidate": b}
                   for i, (a, b) in enumerate(zip(original, candidate)) if a != b]
        allowed = set(range(0x40, 0x44)) | {0x200}
        if advertised_version is not None:
            allowed |= set(range(0x1C, 0x20)) | set(range(0x2BC, 0x2C0))
        if relax:
            allowed |= set(range(0x20, 0x24)) | set(range(0x2C0, 0x2C4))
        if any(int(change["file_offset"], 16) not in allowed for change in changes):
            raise ValueError("Change outside the permitted header fields")
        variants.append({"variant": name, "image": artifact(path),
                         "all_eight_payloads_unchanged": True, "all_eight_decoded_hashes_match": True,
                         "outer_crc32_verified": True, "header_copy_verified": True,
                         "flags_before": hex(flags_before), "flags_after": hex(flags_after),
                         "version_words_unchanged": advertised_version is None,
                         "advertised_halfwords_before": [hex(v) for v in official_versions],
                         "advertised_halfwords_after": [hex(v) for v in struct.unpack_from("<HH", candidate, 0x1C)],
                         "payload_version_metadata_unchanged": True, "byte_changes": changes,
                         "signed_directory_unchanged": signed_input_unchanged,
                         "ecdsa_directory_signature_valid": signature_valid,
                         "signature_bytes_unchanged": True,
                         "components": components})
    return {
        "schema": 1, "scope": "Local unsigned GM5 update-prompt candidates; camera acceptance untested",
        "source": artifact(image), "builder": artifact(Path(__file__)),
        "decoder": artifact(decoder), "decoder_selftest": control,
        "variants": variants,
        "signature_note": "The marker-only candidate leaves the signed directory intact and its ECDSA signature valid; candidates editing duplicated header flags or version invalidate it. All candidates select the zero-marker unsigned path.",
        "intended_path": "GM5 version-two unsigned marker branch after RAM 0x70a68490 is set to zero",
        "relaxed_flags_basis": "The inspected header validator skips its version comparison when header flags & 0x0f is zero. Complete camera eligibility is still to be tested.",
        "testing_stage": "Observe the camera's update confirmation prompt; stop before approving installation.",
        "limits": {"camera_contacted": False, "sd_card_written": False,
                   "firmware_code_changed": False, "calibration_payload_changed": False,
                   "camera_acceptance_verified": False, "firmware_flash_performed": False,
                   "full_physical_backup_complete": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/panasonic-aes5"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--advertised-version", type=lambda value: int(value, 0),
                        help="Prompt-only unsigned test: set both advertised header halfwords, preserving every payload")
    args = parser.parse_args()
    result = build(args.image, args.decoder, args.out, args.advertised_version)
    with (args.out / "package-report.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    for variant in result["variants"]:
        print(f"{variant['variant']}: all eight payloads unchanged and decoded SHA-256 checks passed; {variant['image']['path']}")


if __name__ == "__main__":
    main()
