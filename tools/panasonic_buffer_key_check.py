#!/usr/bin/env python3
"""Test contiguous 16-byte keys from local buffers against a component digest.

Offline only. Compiles the repository's host AES codec into a temporary helper;
does not execute firmware, contact a camera or save candidate plaintexts.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


CODEC = Path(__file__).resolve().with_name("panasonic_aes5.c")
WRAPPER = r"""
#define main panasonic_codec_cli_main
#include CODEC_PATH
#undef main
int pana_initialize(void) {
    initialize_tables();
    return selftest();
}
int pana_decrypt_cbc(const uint8_t *input, size_t length, uint8_t *output,
                     const uint8_t key[16], const uint8_t iv[16], unsigned rounds) {
    if (!length || length % 16 || length > 16777216 || (rounds != 5 && rounds != 10))
        return 0;
    uint8_t previous[16], schedule[176], block[16];
    memcpy(previous, iv, 16);
    expand_key(key, schedule, rounds);
    for (size_t offset = 0; offset < length; offset += 16) {
        decrypt_block(input + offset, block, schedule, rounds);
        for (unsigned i = 0; i < 16; i++) output[offset + i] = block[i] ^ previous[i];
        memcpy(previous, input + offset, 16);
    }
    return 1;
}
size_t pana_magic_scan(const uint8_t *window, size_t length,
        const uint8_t *cipher, const uint8_t *ivs, const uint8_t *magics,
        unsigned probes, uint32_t *positions, uint32_t *tags, size_t capacity) {
    if (length < 16 || length > 16777216 || !probes || probes > 8) return SIZE_MAX;
    size_t hits = 0;
    uint8_t schedule[176], block[16];
    for (size_t position = 0; position + 16 <= length; position++) {
        if (position && !memcmp(window+position, window+position-1, 16)) continue;
        expand_key(window+position, schedule, 10);
        for (unsigned rounds = 5; rounds <= 10; rounds += 5) {
            for (unsigned probe = 0; probe < probes; probe++) {
                decrypt_block(cipher+16*probe, block, schedule, rounds);
                unsigned equal = 1;
                for (unsigned byte = 0; byte < 4; byte++)
                    if ((block[byte] ^ ivs[16*probe+byte]) != magics[4*probe+byte]) equal = 0;
                if (!equal) continue;
                if (hits == capacity) return SIZE_MAX;
                positions[hits] = (uint32_t)position;
                tags[hits] = (rounds << 16) | probe;
                hits++;
            }
        }
    }
    return hits;
}
"""


class HostCodec:
    def __init__(self, directory: Path):
        compiler = shutil.which("cc")
        if compiler is None:
            raise ValueError("A host C compiler is required")
        source = WRAPPER.replace("CODEC_PATH", json.dumps(str(CODEC)))
        c_path = directory / "helper.c"
        c_path.write_text(source)
        library_path = directory / ("helper.dylib" if sys.platform == "darwin" else "helper.so")
        subprocess.run([compiler, "-std=c11", "-O3", "-fPIC",
                        "-dynamiclib" if sys.platform == "darwin" else "-shared",
                        str(c_path), "-o", str(library_path)], check=True, capture_output=True)
        self.library = C.CDLL(str(library_path))
        self.library.pana_initialize.restype = C.c_int
        if self.library.pana_initialize() != 1:
            raise ValueError("Host codec's independent AES controls failed")
        self.decrypt = self.library.pana_decrypt_cbc
        pointer = C.POINTER(C.c_ubyte)
        self.decrypt.argtypes = [pointer, C.c_size_t, pointer, pointer, pointer, C.c_uint]
        self.decrypt.restype = C.c_int
        self.magic_scan = self.library.pana_magic_scan
        u32pointer = C.POINTER(C.c_uint32)
        self.magic_scan.argtypes = [pointer, C.c_size_t, pointer, pointer, pointer,
                                   C.c_uint, u32pointer, u32pointer, C.c_size_t]
        self.magic_scan.restype = C.c_size_t

    def digest(self, ciphertext: bytes, key: bytes, iv: bytes, rounds: int) -> str:
        if len(key) != 16 or len(iv) != 16:
            raise ValueError("AES-128 key and IV must each contain 16 bytes")
        source = (C.c_ubyte * len(ciphertext)).from_buffer_copy(ciphertext)
        output = (C.c_ubyte * len(ciphertext))()
        k = (C.c_ubyte * 16).from_buffer_copy(key)
        v = (C.c_ubyte * 16).from_buffer_copy(iv)
        if self.decrypt(source, len(ciphertext), output, k, v, rounds) != 1:
            raise ValueError("Invalid component length or round count")
        return hashlib.sha256(bytes(output)).hexdigest()

    def probe_window(self, window: bytes, probes: list[dict]) -> list[dict]:
        if not 16 <= len(window) <= 16*1024*1024 or not 1 <= len(probes) <= 8:
            raise ValueError("Probe or input extent outside the bounded scanner")
        def array(data):
            return (C.c_ubyte * len(data)).from_buffer_copy(data)
        ciphertext = b"".join(p["ciphertext"][:16] for p in probes)
        ivs = b"".join(p["iv"] for p in probes)
        magics = b"".join(p["magic"] for p in probes)
        if len(ciphertext) != len(probes)*16 or len(ivs) != len(probes)*16 or len(magics) != len(probes)*4:
            raise ValueError("Each probe requires one block, one IV and a four-byte magic")
        positions, tags = (C.c_uint32 * 1024)(), (C.c_uint32 * 1024)()
        count = self.magic_scan(array(window), len(window), array(ciphertext), array(ivs),
                                array(magics), len(probes), positions, tags, 1024)
        if count == C.c_size_t(-1).value:
            raise ValueError("Magic scan input/capacity limit exceeded")
        return [{"byte_offset": positions[i], "rounds": tags[i] >> 16,
                 "probe_index": tags[i] & 0xFFFF,
                 "key_hex": window[positions[i]:positions[i]+16].hex()} for i in range(count)]


def scan(codec: HostCodec, windows: list[tuple[str, bytes]], ciphertext: bytes,
         iv: bytes, expected_digest: str, rounds: list[int]) -> dict:
    if not ciphertext or len(ciphertext) % 16 or len(ciphertext) > 1024 * 1024:
        raise ValueError("Ciphertext must contain 16-byte blocks, at most 1 MiB")
    if any(not 16 <= len(data) <= 1024 * 1024 for _, data in windows):
        raise ValueError("Each buffer must contain 16 bytes to 1 MiB")
    if sum(len(data) for _, data in windows) > 16 * 1024 * 1024:
        raise ValueError("Combined buffer extent exceeds 16 MiB")
    candidates = {data[i:i+16] for _, data in windows for i in range(len(data)-15)}
    matches = []
    for key in sorted(candidates):
        for count in rounds:
            if codec.digest(ciphertext, key, iv, count) != expected_digest:
                continue
            locations = [{"buffer": name, "byte_offset": i}
                         for name, data in windows for i in range(len(data)-15)
                         if data[i:i+16] == key]
            matches.append({"key_hex": key.hex(), "rounds": count, "locations": locations})
    return {
        "schema": 1,
        "scope": "Contiguous raw 16-byte candidates only; no byte-order transformations or key derivation",
        "codec_source_sha256": hashlib.sha256(CODEC.read_bytes()).hexdigest(),
        "windows": [{"name": name, "bytes": len(data),
                     "sha256": hashlib.sha256(data).hexdigest()} for name, data in windows],
        "candidate_positions": sum(len(data)-15 for _, data in windows),
        "distinct_candidate_keys": len(candidates),
        "ciphertext_bytes": len(ciphertext),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "iv_hex": iv.hex(),
        "expected_plaintext_sha256": expected_digest,
        "aes128_round_counts": rounds,
        "key_matches": matches,
        "camera_or_network_access": False,
    }


def selftest(codec: HostCodec) -> None:
    # NIST SP 800-38A CBC-AES128 first block, including the nonzero IV.
    key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
    iv = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    cipher = bytes.fromhex("7649abac8119b246cee98e9b12e9197d")
    plain = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
    assert codec.digest(cipher, key, iv, 10) == hashlib.sha256(plain).hexdigest()
    hits = codec.probe_window(b"NIST" + key + b"tail", [
        {"ciphertext": cipher, "iv": iv, "magic": plain[:4]}])
    assert hits == [{"byte_offset": 4, "rounds": 10, "probe_index": 0, "key_hex": key.hex()}]
    # Independently acquired GM1 five-round block from the existing codec control.
    key = bytes.fromhex("350481b566d22d5b89dc46775e644622")
    cipher = bytes.fromhex("147069b0d8d7a35b439688d2b8e59278")
    plain = bytes.fromhex("cd6a60a6c34c6893a76ad12db4d8bdf2")
    result = scan(codec, [("unaligned-control", b"A"*7+key+b"Z"*4)], cipher,
                  bytes(16), hashlib.sha256(plain).hexdigest(), [5, 10])
    assert result["key_matches"] == [{"key_hex": key.hex(), "rounds": 5,
                                       "locations": [{"buffer": "unaligned-control", "byte_offset": 7}]}]
    probes = [{"ciphertext": cipher, "iv": bytes(16), "magic": plain[:4]}]
    hits = codec.probe_window(b"A"*7+key+b"Z"*4, probes)
    assert hits == [{"byte_offset": 7, "rounds": 5, "probe_index": 0, "key_hex": key.hex()}]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("windows", nargs="*", type=Path)
    parser.add_argument("--cipher", type=Path)
    parser.add_argument("--iv")
    parser.add_argument("--sha256")
    parser.add_argument("--rounds", type=int, choices=(5, 10), nargs="+", default=[5])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="panasonic-buffer-key-") as temporary:
        codec = HostCodec(Path(temporary))
        selftest(codec)
        if args.selftest and not args.windows:
            print("NIST CBC and unaligned physical GM1 key controls passed; offline only.")
            return 0
        if not args.windows or not args.cipher or not args.iv or not args.sha256:
            parser.error("Provide buffers, --cipher, --iv and --sha256, or --selftest")
        try:
            iv = bytes.fromhex(args.iv)
            digest = bytes.fromhex(args.sha256)
        except ValueError:
            parser.error("IV and digest must be hexadecimal")
        if len(iv) != 16 or len(digest) != 32:
            parser.error("IV must be 16 bytes and SHA256 digest 32 bytes")
        report = scan(codec, [(str(p), p.read_bytes()) for p in args.windows],
                      args.cipher.read_bytes(), iv, digest.hex(), sorted(set(args.rounds)))
    output = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_text(output)
        print(f"Tested {report['distinct_candidate_keys']} distinct candidates; "
              f"matches: {len(report['key_matches'])}; report: {args.out}")
    else:
        print(output, end="")
    return 0 if report["key_matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
