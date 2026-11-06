#!/usr/bin/env python3
"""Verify the GM1 update-directory ECDSA signature offline with two methods.

Reads the public verification key in recovered GM1 program2. No signing key,
signature generation, camera command or update-package creation is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from panasonic_upd import parse
from panasonic_v2_decode import OFFICIAL_HASHES

P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)
SECONDARY_SHA256 = "7e8c7d96a95a505d5500fafbd076a56e95f27267708c1f02deb2606fcd304968"
PUBLIC_PROFILES = {
    "GM1": (SECONDARY_SHA256, 0x21CF18, 0x21CE64),
    "GM5": ("90dd3e4a19c6008571f1623e4d849f245b279473f43e3b13f8b763e6c94a53a5", 0x22A710, 0x22A65C),
}


def add(left, right):
    if left is None:
        return right
    if right is None:
        return left
    x, y = left
    u, v = right
    if x == u and (y+v) % P == 0:
        return None
    slope = ((3*x*x-3)*pow(2*y, -1, P) if left == right
             else (v-y)*pow(u-x, -1, P)) % P
    result = (slope*slope-x-u) % P
    return result, (slope*(x-result)-y) % P


def multiply(scalar, point):
    result = None
    while scalar:
        if scalar & 1:
            result = add(result, point)
        point = add(point, point)
        scalar >>= 1
    return result


def verify(public: bytes, digest: bytes, signature: bytes) -> bool:
    if len(public) != 64 or len(digest) != 32 or len(signature) != 64:
        return False
    point = (int.from_bytes(public[:32], "little"), int.from_bytes(public[32:], "little"))
    x, y = point
    if not (0 <= x < P and 0 <= y < P) or (y*y-x*x*x+3*x-B) % P:
        return False
    if multiply(N, point) is not None:
        return False
    r = int.from_bytes(signature[:32], "little")
    s = int.from_bytes(signature[32:], "little")
    if not (0 < r < N and 0 < s < N):
        return False
    inverse = pow(s, -1, N)
    hashed = int.from_bytes(digest, "little")
    result = add(multiply(hashed*inverse % N, G), multiply(r*inverse % N, point))
    return result is not None and result[0] % N == r


def der_integer(raw: bytes) -> bytes:
    big = int.from_bytes(raw, "little").to_bytes(32, "big").lstrip(b"\0") or b"\0"
    if big[0] & 128:
        big = b"\0"+big
    return b"\x02"+bytes([len(big)])+big


def openssl_verify(public: bytes, digest: bytes, signature: bytes, openssl: str) -> bool:
    encoded = der_integer(signature[:32])+der_integer(signature[32:])
    encoded = b"\x30"+bytes([len(encoded)])+encoded
    spki = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d03010703420004")
    spki += public[:32][::-1]+public[32:][::-1]
    with tempfile.TemporaryDirectory(prefix="panasonic-directory-check-") as directory:
        root = Path(directory)
        (root / "public.der").write_bytes(spki)
        (root / "signature.der").write_bytes(encoded)
        # Native uint256 operations treat the SHA-256 byte output as little endian.
        (root / "digest.bin").write_bytes(digest[::-1])
        result = subprocess.run(
            [openssl, "pkeyutl", "-verify", "-pubin", "-keyform", "DER",
             "-inkey", str(root / "public.der"), "-in", str(root / "digest.bin"),
             "-sigfile", str(root / "signature.der")], capture_output=True, text=True)
        if result.returncode not in (0, 1):
            raise ValueError(f"OpenSSL verification failed to run: {result.stderr.strip()}")
        return result.returncode == 0


def report(image: Path, secondary: Path, openssl: str, key_model: str = "GM1") -> dict:
    raw = image.read_bytes()
    model = raw[12:24].split(b"\0", 1)[0].decode("ascii")
    source_digest = hashlib.sha256(raw).hexdigest()
    if model not in OFFICIAL_HASHES or source_digest != OFFICIAL_HASHES[model]:
        raise ValueError("Expected a pinned official GM1/GM5 image")
    entries = parse(raw, expected_model=model)
    program2 = secondary.read_bytes()
    key_hash, profile_pointer, key_offset = PUBLIC_PROFILES[key_model]
    if hashlib.sha256(program2).hexdigest() != key_hash:
        raise ValueError(f"Expected the verified {key_model} secondary program")
    if struct.unpack_from("<I", program2, profile_pointer)[0] != 0x7BC00000+key_offset:
        raise ValueError("Public-key profile pointer differs")
    public = program2[key_offset:key_offset+64]
    start, end = 0x2A0, 0x2A0+76+92*len(entries)
    directory = raw[start:end]
    digest = hashlib.sha256(directory).digest()
    signature = raw[0x220:0x260]
    native_math = verify(public, digest, signature)
    host_crypto = openssl_verify(public, digest, signature, openssl)
    if native_math != host_crypto:
        raise ValueError("Independent signature verifiers disagree")
    altered = bytes([digest[0] ^ 1])+digest[1:]
    altered_signature = bytes([signature[0] ^ 1])+signature[1:]
    negative_digest = verify(public, altered, signature)
    negative_signature = verify(public, digest, altered_signature)
    if model == key_model and (not native_math or negative_digest or negative_signature):
        raise ValueError("Signature positive/negative controls failed")
    return {
        "schema": 1, "scope": "Official update-directory signature against recovered model public key",
        "source": {"path": str(image), "bytes": len(raw), "sha256": source_digest},
        "model": model, "key_model": key_model,
        "key_source": {"path": str(secondary), "sha256": key_hash,
                       "linked_address": hex(0x7BC00000+key_offset), "bytes": 64, "hex": public.hex()},
        "algorithm": "ECDSA P-256 with SHA-256; raw uint256 fields and hash interpreted little endian",
        "directory": {"file_start": hex(start), "file_end_exclusive": hex(end),
                      "bytes": len(directory), "sha256": digest.hex(),
                      "component_count": len(entries)},
        "signature": {"file_start": "0x220", "bytes": 64, "hex": signature.hex(),
                      "layout": "32-byte little-endian r followed by 32-byte little-endian s"},
        "independent_math_valid": native_math, "openssl_valid": host_crypto,
        "openssl_version": subprocess.check_output([openssl, "version"], text=True).strip(),
        "controls": {"modified_hash_accepted": negative_digest,
                     "modified_signature_accepted": negative_signature},
        "verifier": {"path": "tools/panasonic_signature_verify.py",
                     "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "limits": ["Each public key verifies its recorded model; a cross-model failure does not disprove the other model's signature.",
                   "Signature validity and static call tracing do not establish every hardware acceptance condition.",
                   "No private signing key, signing function, modified update or camera operation is produced."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--gm1-secondary", "--secondary", dest="secondary", required=True, type=Path)
    parser.add_argument("--key-model", choices=tuple(PUBLIC_PROFILES), default="GM1")
    parser.add_argument("--openssl", default="openssl")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = report(args.image, args.secondary, args.openssl, args.key_model)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"{result['model']} signature against {args.key_model} key: {result['openssl_valid']}; two verifiers agree.")


if __name__ == "__main__":
    main()
