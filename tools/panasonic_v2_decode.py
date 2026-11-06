#!/usr/bin/env python3
"""Decode pinned official GM1/GM5 updates offline and require every SHA-256.

Produces research component files, not an update package or flash image. The key
is extracted from the complete, physically acquired GM1 main-program control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from panasonic_upd import parse

OFFICIAL_HASHES = {
    "GM1": "3e8b4aab23f79db160cd016af0e466011f047add07bb7441c642f6b70df30d90",
    "GM5": "d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243",
}
KEY_SOURCE_HASH = "a96fb6da618b33207db0d357ac5e2513583aaa71dd01df44bed498e63992fabe"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def decode(image: Path, key_source: Path | None, decoder: Path, output: Path,
           physical_secondary: Path | None = None, key_hex: str | None = None) -> dict:
    raw = image.read_bytes()
    model = raw[12:24].split(b"\0", 1)[0].decode("ascii")
    if model not in OFFICIAL_HASHES or sha(raw) != OFFICIAL_HASHES[model]:
        raise ValueError("Expected a pinned, intact official GM1/GM5 1.1 update")
    entries = parse(raw, expected_model=model)
    if struct.unpack_from("<I", raw, 0x2C)[0] != 3 or struct.unpack_from("<I", raw, 0x34)[0] != 3:
        raise ValueError("Expected the recovered CRC32/cipher-three format")
    main = None
    if key_source is not None:
        main = key_source.read_bytes()
        if len(main) != 0x900000 or sha(main) != KEY_SOURCE_HASH:
            raise ValueError("Key source must equal the complete physical GM1 main control")
        key = main[0x5AB460:0x5AB470]
        if key.hex() != "350481b566d22d5b89dc46775e644622":
            raise ValueError("Key bytes differ from the traced initializer")
    else:
        key = bytes.fromhex(key_hex or "")
        if len(key) != 16:
            raise ValueError("An explicit candidate key must contain sixteen bytes")
    control = subprocess.check_output([str(decoder.resolve()), "--selftest"], text=True).strip()
    if output.exists():
        raise ValueError("Output exists; choose a fresh directory")
    secondary = physical_secondary.read_bytes() if physical_secondary is not None else None
    output.mkdir(parents=True, exist_ok=False)
    # Preserve the source versions used for a decoding run as tools evolve.
    (output / "decoder-source.c").write_bytes(Path("tools/panasonic_aes5.c").read_bytes())
    (output / "driver-source.py").write_bytes(Path(__file__).read_bytes())
    components = []
    for entry in entries:
        if entry["flags_raw"] != 3:
            raise ValueError(f"Unsupported component flags for {entry['name']}")
        path = output / f"{entry['index']:02d}_{entry['name']}.decoded.bin"
        subprocess.run([str(decoder.resolve()), str(image), str(path), key.hex(),
                        entry["field16_hex"], str(entry["file_offset"]), str(entry["size"])],
                       check=True, capture_output=True, text=True)
        plaintext = path.read_bytes()
        digest = sha(plaintext)
        if len(plaintext) != entry["size"] or digest != entry["field32_hex"]:
            raise ValueError(f"Plaintext SHA-256 mismatch for {entry['name']}")
        physical_match = None
        if model == "GM1" and entry["name"] == "program" and main is not None:
            physical_match = plaintext == main
        elif model == "GM1" and entry["name"] == "program2" and secondary is not None:
            physical_match = plaintext == secondary
        if physical_match is False:
            raise ValueError(f"Decoded {entry['name']} differs from the physical control")
        component = {**entry, "plaintext_file": str(path), "plaintext_sha256": digest,
                     "plaintext_sha256_matches_directory": True,
                     "physical_control_byte_for_byte_match": physical_match}
        components.append(component)
        print(f"{model} {entry['name']}: {len(plaintext):,} bytes; SHA-256 matches", flush=True)
    report = {
        "schema": 1, "scope": "Offline complete official update decoding; no flashing or repacking",
        "model": model, "source": record(image),
        "key_source": record(key_source) if key_source is not None else {"kind": "explicit candidate; all component hashes required"},
        "key": {"hex": key.hex(), "bytes": 16, **({
                "physical_flash_address": "0x405ab460", "initialized_ram_address": "0x70007bdc",
                "consumer_copy_call": "0x7bd4a358"} if key_source is not None else {})},
        "algorithm": {"name": "Five-round AES-128-CBC", "selector": 3,
                      "standard_aes128_rounds": 10, "selected_rounds": 5,
                      "padding": "none", "iv_source": "Component directory entry +60, 16 bytes",
                      "digest": "SHA-256 of each decoded component",
                      "outer_digest": "CRC32 of encoded body"},
        "decoder": record(decoder), "decoder_source": record(Path("tools/panasonic_aes5.c")),
        "driver": record(Path(__file__)), "host_selftest": control,
        "retained_decoder_source": record(output / "decoder-source.c"),
        "retained_driver_source": record(output / "driver-source.py"),
        "all_component_hashes_match": True, "components": components,
        "limits": ["Component hashes establish exact agreement with the official directory, not signature validity.",
                   "The directory authentication path requires separate verification.",
                   "No encoded update, modified firmware, flash write, or camera operation is produced."],
    }
    with (output / "decode-report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    keys = parser.add_mutually_exclusive_group(required=True)
    keys.add_argument("--key-source", type=Path, help="Complete physical GM1 main-program control")
    keys.add_argument("--key-hex", help="Explicit 16-byte candidate; every component hash must still pass")
    parser.add_argument("--physical-secondary", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/panasonic-aes5"))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = decode(args.image, args.key_source, args.decoder, args.out, args.physical_secondary, args.key_hex)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Decode failed: {error}\n")
    print(f"Verified all {len(result['components'])} {result['model']} components.")


if __name__ == "__main__":
    main()
