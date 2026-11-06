#!/usr/bin/env python3
"""Bounded offline AES-key checks in the physically read GM1 RAM initializer.

This tests a stated candidate set, not every key/cipher/transform. It never
contacts a camera or writes an update. A negative result excludes only these
literal windows with AES-CBC/ECB and this component alignment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

INITIALIZER_SHA256 = "adc677a6184a3762271469a1c4ee52c109a6959f15df30fd68ff73538e22f349"
KNOWN_PREFIX_SHA256 = "f0e7a9103888098d5b9d9c9c83ae40afb2b7b3591931f911decdd6e1ce4dcc12"
OFFICIAL_SHA256 = "3e8b4aab23f79db160cd016af0e466011f047add07bb7441c642f6b70df30d90"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decrypt(data: bytes, key: bytes, mode: str, iv: bytes = bytes(16)) -> bytes:
    command = ["openssl", "enc", "-d", f"-aes-{8*len(key)}-{mode}", "-K", key.hex(), "-nopad"]
    if mode == "cbc":
        command += ["-iv", iv.hex()]
    return subprocess.check_output(command, input=data, stderr=subprocess.PIPE)


def make_report(initializer_path: Path, known_path: Path, official_path: Path) -> dict:
    initializer, known, official = (p.read_bytes() for p in (initializer_path, known_path, official_path))
    if (len(initializer) != 32768 or sha(initializer) != INITIALIZER_SHA256
            or len(known) != 64 or sha(known) != KNOWN_PREFIX_SHA256
            or sha(official) != OFFICIAL_SHA256):
        raise ValueError("Expected the pinned GM1 initializer, physical 64-byte prefix and official 1.1 update")
    ciphertext = official[0x600:0x640]
    initializer_start, initializer_end = 0x84, 0x84 + 0x7CC8
    counts, matches, candidates = {}, [], []
    explicit = (0, 8, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38, 0x40, 0x48, 0x50, 0x60, 0x80)
    for size, unique in ((16, 14), (32, 28)):
        offsets = {initializer_start + n for n in explicit}
        offsets.update(i for i in range(initializer_start, initializer_end-size+1, 4)
                       if len(set(initializer[i:i+size])) >= unique)
        counts[str(size)] = len(offsets)
        for offset in sorted(offsets):
            key = initializer[offset:offset+size]
            candidates.append({"key_bytes": size, "ram_initializer_offset": hex(offset-initializer_start)})
            plain = decrypt(ciphertext, key, "cbc")
            if plain[16:] == known[16:]:
                # CBC's later plaintext blocks do not depend on the initial IV.
                derived_iv = bytes(a ^ b for a, b in zip(plain[:16], known[:16]))
                if decrypt(ciphertext, key, "cbc", derived_iv) != known:
                    raise ValueError("CBC known-plaintext verification differs")
                matches.append({"mode": "cbc", "key_hex": key.hex(), "iv_hex": derived_iv.hex(),
                                "ram_initializer_offset": hex(offset-initializer_start)})
            if decrypt(ciphertext, key, "ecb") == known:
                matches.append({"mode": "ecb", "key_hex": key.hex(),
                                "ram_initializer_offset": hex(offset-initializer_start)})
    return {"schema": 1, "scope": "Offline literal-key hypothesis checks in one acquired GM1 data initializer",
            "source": {str(p): {"bytes": len(data), "sha256": sha(data)} for p, data in
                       ((initializer_path, initializer), (known_path, known), (official_path, official))},
            "verifier": {"path": "tools/gm1_initializer_key_probe.py", "sha256": sha(Path(__file__).read_bytes())},
            "openssl_version": subprocess.check_output(["openssl", "version"], text=True).strip(),
            "candidate_rule": "Explicit early RAM offsets plus four-byte-aligned literal windows with at least 14/16 or 28/32 distinct byte values, inside the traced initializer only",
            "candidate_counts_by_key_bytes": counts, "candidate_offsets": candidates,
            "modes": ["AES-128-CBC", "AES-256-CBC", "AES-128-ECB", "AES-256-ECB"],
            "cbc_check": "Compare known blocks 2..4 independent of IV; derive and confirm IV only on a match",
            "official_component_ciphertext_offset": "0x600", "known_plaintext_bytes": len(known),
            "matches": matches,
            "limits": ["No conclusion about nonliteral keys, other locations, obfuscation, other cipher modes or framing.",
                       "The traced GM1 initializer starts with font/GUI records; its offset 0x28 is not the GH2 update-key field.",
                       "No GM5 key or native updater consumer is established by this bounded test."],
            "camera_contacted": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("initializer", type=Path)
    parser.add_argument("known_prefix", type=Path)
    parser.add_argument("official", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = make_report(args.initializer, args.known_prefix, args.official)
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(f"Tested {sum(report['candidate_counts_by_key_bytes'].values())} literal key windows; matches: {len(report['matches'])}.")


if __name__ == "__main__":
    main()
