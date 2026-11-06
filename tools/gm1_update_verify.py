#!/usr/bin/env python3
"""Pin GM1 native updater/key/cipher/signature paths against physical programs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from gh2_debug_verify import checked_disassembly
from gm1_factory_verify import INPUTS

REGIONS = (
    ("key_startup_copy", "main", 0x4000017D, 0x400001AF),
    ("key_header_and_version_dispatch", "secondary", 0x7BD49642, 0x7BD4976B),
    ("version_two_cipher_dispatch", "secondary", 0x7BD4976B, 0x7BD498A0),
    ("key_profile_and_unsigned_allowance", "secondary", 0x7BD4A254, 0x7BD4A36A),
    ("cipher_three_class", "main", 0x40286C59, 0x40286DCF),
    ("standard_and_short_round_initializers", "main", 0x4028767C, 0x40287708),
    ("normal_aes_decrypt_initializer", "main", 0x40286FA7, 0x40287013),
    ("aes_round_expansion", "main", 0x40286DCF, 0x40286FA7),
    ("cbc_decrypt_loop", "main", 0x40287810, 0x402878AF),
    ("crc32_implementation", "main", 0x4028791E, 0x40287990),
    ("signature_or_unsigned_branch", "secondary", 0x7BD499E7, 0x7BD49A88),
    ("component_sha256_check", "secondary", 0x7BD49BA5, 0x7BD49C33),
    ("signature_wrapper", "main", 0x40287A94, 0x40287B16),
    ("ecdsa_verification_core", "main", 0x40014E8C, 0x40014F3E),
)
CALLS = (
    ("secondary", 0x7BD4A358, 0x7BD49642),
    ("secondary", 0x7BD4A365, 0x7BD4975F),
    ("secondary", 0x7BD497D8, 0x40286A5D),
    ("secondary", 0x7BD49848, 0x40286C7A),
    ("secondary", 0x7BD49877, 0x40286CF3),
    ("secondary", 0x7BD49883, 0x40286CD5),
    ("secondary", 0x7BD4988D, 0x40286CA9),
    ("main", 0x40286D65, 0x4028767C),
    ("main", 0x40287693, 0x40286FA7),
    ("main", 0x402876B9, 0x40286EE1),
    ("secondary", 0x7BD49A55, 0x402888E1),
    ("secondary", 0x7BD49A7A, 0x40287A94),
    ("main", 0x40287B03, 0x40014E8C),
    ("secondary", 0x7BD49BA7, 0x402885A1),
    ("secondary", 0x7BD49BC3, 0x402887BF),
    ("secondary", 0x7BD49C10, 0x402888A4),
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def report(main: Path, secondary: Path, decoder: Path) -> dict:
    paths = {"main": main, "secondary": secondary}
    data = {name: path.read_bytes() for name, path in paths.items()}
    sources = {}
    for name, (base, size, digest) in INPUTS.items():
        if len(data[name]) != size or sha(data[name]) != digest:
            raise ValueError(f"Expected complete physical GM1 {name} control")
        sources[name] = {"path": str(paths[name]), "bytes": size,
                         "sha256": digest, "file_zero_base": hex(base)}
    regions = []
    for name, component, start, end in REGIONS:
        base = INPUTS[component][0]
        disassembly, count = checked_disassembly(
            paths[component], data[component], decoder, base, start, end)
        regions.append({"name": name, "component": component, "start": hex(start),
                        "end_exclusive": hex(end), "instruction_count": count,
                        "native_sha256": sha(data[component][start-base:end-base]),
                        "raw_annotations_match_source": True, "disassembly": disassembly})
    calls = []
    for component, address, target in CALLS:
        offset = address-INPUTS[component][0]
        opcode = data[component][offset]
        if opcode not in (0xCD, 0xDD):
            raise ValueError(f"Missing relative call at {address:#x}")
        actual = (address+struct.unpack_from(
            "<h" if opcode == 0xCD else "<i", data[component], offset+1)[0]) & 0xFFFFFFFF
        if actual != target:
            raise ValueError(f"Call differs at {address:#x}")
        calls.append({"component": component, "address": hex(address), "target": hex(target)})
    def main_word(address):
        return struct.unpack_from("<I", data["main"], address-0x40000000)[0]
    copy = tuple(main_word(a) for a in (0x40000191, 0x40000197, 0x400001A1))
    if copy != (0x405A3884, 0x405AB54C, 0x70000000):
        raise ValueError("Key initializer mapping differs")
    key_ram = struct.unpack_from("<I", data["secondary"], 0x14A352)[0]
    key_flash = copy[0]+key_ram-copy[2]
    key = data["main"][key_flash-0x40000000:key_flash-0x40000000+16]
    if key_ram != 0x70007BDC or key_flash != 0x405AB460 or key.hex() != "350481b566d22d5b89dc46775e644622":
        raise ValueError("Traced key differs")
    vtable = struct.unpack_from("<10I", data["main"], 0x42FAA8)
    if vtable != (0x40286C76, 0x40286CA9, 0x40286CB1, 0x40286CD0, 0x40286CF3,
                  0x40286CFF, 0x40286D05, 0x40286D4E, 0x40286D97, 0x40286DB3):
        raise ValueError("Cipher-three virtual methods differ")
    expected_crc = []
    for value in range(256):
        current = value
        for _ in range(8):
            current = (current >> 1) ^ (0xEDB88320 if current & 1 else 0)
        expected_crc.append(current)
    if tuple(expected_crc) != struct.unpack_from("<256I", data["main"], 0x431D2C):
        raise ValueError("CRC32 polynomial table differs")
    public_pointer = struct.unpack_from("<I", data["secondary"], 0x21CF18)[0]
    if public_pointer != 0x7BE1CE64:
        raise ValueError("Signature profile pointer differs")
    return {
        "schema": 1, "scope": "GM1 native version-two update decoding/authentication paths, offline only",
        "sources": sources,
        "verifier": {"path": "tools/gm1_update_verify.py", "sha256": sha(Path(__file__).read_bytes())},
        "decoder": {"path": str(decoder), "sha256": sha(decoder.read_bytes()), "machine_argument": 332},
        "mechanical_checks": {"regions": regions, "relative_calls": calls,
                              "cipher_three_vtable": [hex(x) for x in vtable],
                              "crc32_reflected_polynomial": "0xedb88320", "crc32_table_verified": True},
        "key_mapping": {"initializer_source": hex(copy[0]), "initializer_end_exclusive": hex(copy[1]),
                        "initializer_destination": hex(copy[2]), "key_flash": hex(key_flash),
                        "key_ram": hex(key_ram), "bytes": 16, "key_hex": key.hex()},
        "manual_review": {
            "cipher": "Cipher selector three constructs the 128-bit class whose decrypt initializer uses 0x4028767c. That initializer obtains standard AES rounds/Nk, divides the round count by two, and invokes the same inverse key expansion. Ten rounds become five; CBC IV is entry offset sixty.",
            "integrity": "Outer digest selector three uses the reflected CRC32 implementation/table. The component path hashes decoded bytes with SHA-256 and compares thirty-two bytes to entry offset twenty-eight.",
            "signature": "The nonzero inner marker branch hashes 76+92*count bytes of inner header/directory and verifies raw signature bytes at body offset thirty-two through 0x40287a94 and 0x40014e8c. The normal supplied profile points to P-256 public coordinates at 0x7be1ce64.",
            "unsigned_mode": "A zero first marker byte is rejected unless context+92 is nonzero; when allowed, both signature and component-SHA checks are skipped on the reviewed branch. Job 0x7bd4a254 sets context+92 when runtime byte 0x70903814 is zero. Meaning, default value and complete writer/caller behavior of that byte are unresolved; no input was sent to a camera.",
            "validation": "Complete six-component decoding and independent signature verification are recorded separately in evidence/gm1-v11-decoded.json and evidence/gm1-directory-signature.json.",
        },
        "limits": ["Native behavior is manually interpreted, not emulated by this verifier.",
                   "An unsigned branch is established statically, but its activation and camera acceptance are untested.",
                   "No GM5 equivalence, private signing key, modified update, target execution or flash write is established."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main_program", type=Path)
    parser.add_argument("secondary_program", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = report(args.main_program, args.secondary_program, args.decoder)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Verified GM1 key mapping, {len(REGIONS)} native regions, {len(CALLS)} calls, cipher table and CRC32 table.")


if __name__ == "__main__":
    main()
