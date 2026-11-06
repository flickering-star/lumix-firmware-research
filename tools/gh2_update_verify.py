#!/usr/bin/env python3
"""Recheck GH2's embedded update key and its legacy update-consumer links.

Version-specific, offline evidence verification. Reads official update samples,
disassembles selected native regions, and uses host OpenSSL for a positive
control. Camera instructions and downloaded host programs are never executed.
The descriptions of native code are manual interpretations, not an emulator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from gh2_debug_verify import (
    BODY_SHA256, MAIN_BASE, SECONDARY_BASE, checked_disassembly, verify_input,
)


UPDATE_HASHES = {
    "gh2": "e192ba2a7dba4167e4100efc896c5475faffd51164bd949e600964430454e817",
    "gm5": "d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243",
}
REGIONS = (
    ("key_initialized_data_copy", MAIN_BASE, 0x40000195, 0x400001B3),
    ("update_header_reader", SECONDARY_BASE, 0x7BCD5AB6, 0x7BCD5B67),
    ("key_context_setter", SECONDARY_BASE, 0x7BCD5A8A, 0x7BCD5AB6),
    ("legacy_header_validation", SECONDARY_BASE, 0x7BCD5FAA, 0x7BCD6047),
    ("update_job_to_key_and_decode", SECONDARY_BASE, 0x7BCD6107, 0x7BCD61F9),
    ("digest_and_cipher_selection", SECONDARY_BASE, 0x7BCD5B67, 0x7BCD5C1D),
    ("payload_read", SECONDARY_BASE, 0x7BCD5C1D, 0x7BCD5C65),
    ("decrypt_init_and_update_dispatch", SECONDARY_BASE, 0x7BCD5CE8, 0x7BCD5D20),
    ("digest_and_inner_header_checks", SECONDARY_BASE, 0x7BCD5E3B, 0x7BCD5ECF),
    ("md5_and_aes_object_wrappers", MAIN_BASE, 0x401555AE, 0x401556E1),
    ("md5_initial_state", MAIN_BASE, 0x40003C5C, 0x40003C88),
    ("aes_context_initialization", MAIN_BASE, 0x40060419, 0x400604E3),
    ("cbc_decrypt_and_ecb_branch", MAIN_BASE, 0x400605A6, 0x4006067C),
    ("aes_block_decrypt", MAIN_BASE, 0x400609B2, 0x40060C47),
    ("aes_round_key_expansion", MAIN_BASE, 0x40060C47, 0x40060E1F),
    ("generic_settings_export_wrapper", MAIN_BASE, 0x400F021D, 0x400F0258),
    ("settings_formatter_to_file_export", MAIN_BASE, 0x40025FB6, 0x40026010),
)
CALLS = (
    (0x7BCD61B7, 0x7BCD5FAA), (0x7BCD61CE, 0x7BCD5A8A),
    (0x7BCD61F4, 0x7BCD5B67), (0x7BCD5AA8, 0x7BC519C8),
    (0x7BCD5BDA, 0x40155618), (0x7BCD5BE5, 0x40155684),
    (0x7BCD5BF1, 0x40155670), (0x7BCD5BFB, 0x40155650),
    (0x7BCD5C09, 0x40155660), (0x40155679, 0x4006042C),
    (0x40155662, 0x40060469), (0x40155652, 0x40060478),
    (0x401556A6, 0x400604B0), (0x401556D6, 0x400605A6),
    (0x400604DA, 0x40060D59), (0x40060D5D, 0x40060C47),
    (0x4006061B, 0x400609B2), (0x400FAE7B, 0x7BCD6107),
    (0x40025FC8, 0x401DF73F), (0x40025FD7, 0x400F021D),
    (0x40025FED, 0x401DF73F), (0x40025FFC, 0x400F021D),
    (0x400F024F, 0x400F010D),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def header_fields(data: bytes) -> dict:
    return {name: hex(struct.unpack_from("<I", data, offset)[0])
            for name, offset in (("format_at_0x08", 0x08),
                                 ("field_at_0x2c", 0x2C),
                                 ("field_at_0x30", 0x30),
                                 ("field_at_0x34", 0x34))}


def make_report(body: Path, gh2: Path, gm5: Path, decoder: Path,
                openssl: Path) -> dict:
    data = body.read_bytes()
    verify_input(data)
    samples = {"gh2": gh2.read_bytes(), "gm5": gm5.read_bytes()}
    for name, raw in samples.items():
        if sha256(raw) != UPDATE_HASHES[name]:
            raise ValueError(f"Official {name.upper()} sample differs")

    regions = []
    for name, base, start, end in REGIONS:
        output, count = checked_disassembly(body, data, decoder, base, start, end)
        regions.append({"name": name, "file_zero_base": hex(base),
                        "start": hex(start), "end_exclusive": hex(end),
                        "body_offset": hex(start-base), "bytes": end-start,
                        "native_sha256": sha256(data[start-base:end-base]),
                        "instruction_count": count,
                        "raw_annotations_match_source": True,
                        "disassembly": output})
    calls = []
    for at, expected in CALLS:
        base = SECONDARY_BASE if at >= 0x7BBC0000 else MAIN_BASE
        off = at-base
        opcode = data[off]
        if opcode not in (0xCD, 0xDD):
            raise ValueError(f"Expected relative call at {at:#x}")
        target = (at+struct.unpack_from("<h" if opcode == 0xCD else "<i", data, off+1)[0]) & 0xFFFFFFFF
        if target != expected:
            raise ValueError(f"Call target differs at {at:#x}")
        calls.append({"address": hex(at), "target": hex(target)})

    # Constants are read from the instructions whose raw bytes were checked.
    load_start = struct.unpack_from("<I", data, 0x40000197-MAIN_BASE)[0]
    load_end = struct.unpack_from("<I", data, 0x4000019D-MAIN_BASE)[0]
    ram_start = struct.unpack_from("<I", data, 0x400001A7-MAIN_BASE)[0]
    if (load_start, load_end, ram_start) != (0x407F4CD0, 0x407F6384, 0x74000000):
        raise ValueError("Key initializer mapping differs")
    key_offset = 0x7F50F8
    key = data[key_offset:key_offset+16]
    key_ram = ram_start + MAIN_BASE + key_offset - load_start
    consumer_ram = struct.unpack_from("<I", data, 0x7BCD61C8-SECONDARY_BASE)[0]
    if key_ram != consumer_ram or key != bytes.fromhex("90b43b5ce34c6e667fb28376b5fa5c27"):
        raise ValueError("Embedded key does not map to its update consumer")

    vtable_at = 0x4024999C
    vtable = struct.unpack_from("<10I", data, vtable_at-MAIN_BASE)
    if vtable != (0x4015563D, 0x4015564D, 0x4015565D, 0x4015566D,
                  0x40155684, 0x4015568B, 0x40155691, 0x401556A1,
                  0x401556B1, 0x401556C9):
        raise ValueError("Cipher object's function table differs")

    control = samples["gh2"]
    iv = control[0x80:0x90]
    decoded = subprocess.check_output([
        str(openssl), "enc", "-d", "-aes-128-cbc", "-K", key.hex(),
        "-iv", iv.hex(), "-nopad",
    ], input=control[0x200:])
    md5 = hashlib.md5(decoded).digest()
    if decoded != data or md5 != control[0x40:0x50]:
        raise ValueError("Native-key AES control does not reproduce the pinned plaintext")

    filenames = []
    for off, expected in ((0x2304AC, b"B:\\ROMDATA.BIN\0"),
                          (0x2304BB, b"A:\\ROMDATA.BIN\0"),
                          (0x2304CA, b"B:\\FIRMWARE.BIN\0"),
                          (0x2304DA, b"A:\\FIRMWARE.BIN\0")):
        if data[off:off+len(expected)] != expected:
            raise ValueError("Firmware-related filename differs")
        address = MAIN_BASE+off
        filenames.append({"name": expected[:-1].decode("ascii"), "body_offset": hex(off),
                          "main_mapping_address": hex(address),
                          "exact_little_endian_address_occurrences": data.count(struct.pack("<I", address))})

    return {
        "schema": 1,
        "scope": "Static legacy GH2 updater; GM5 plaintext and its actual cipher remain unknown",
        "inputs": {"body": {"path": str(body), "sha256": BODY_SHA256},
                   **{name: {"path": str(path), "sha256": UPDATE_HASHES[name],
                             "bytes": len(samples[name]), "header_fields": header_fields(samples[name])}
                      for name, path in (("gh2", gh2), ("gm5", gm5))}},
        "verifier": {"path": "tools/gh2_update_verify.py", "sha256": sha256(Path(__file__).read_bytes()),
                     "decoder_path": str(decoder), "decoder_sha256": sha256(decoder.read_bytes()),
                     "openssl_path": str(openssl),
                     "openssl_version": subprocess.check_output([str(openssl), "version"], text=True).strip()},
        "mechanical_checks": {"regions": regions, "relative_calls": calls},
        "embedded_key": {"body_offset": hex(key_offset), "flash_address": hex(MAIN_BASE+key_offset),
                         "hex": key.hex(), "copy_load_start": hex(load_start),
                         "copy_load_end_exclusive": hex(load_end), "copy_ram_start": hex(ram_start),
                         "consumer_ram_address": hex(key_ram), "consumer_instruction": "0x7bcd61c6",
                         "context_copy_call": "0x7bcd61ce", "key_bytes": 16},
        "positive_control": {"mode": "AES-128-CBC", "iv_offset": "0x80", "iv": iv.hex(),
                             "ciphertext_offset": "0x200", "full_plaintext_equals_pinned_body": True,
                             "plaintext_sha256": sha256(decoded), "plaintext_md5": md5.hex(),
                             "md5_equals_official_header_bytes_0x40_to_0x50": True,
                             "decoded_bytes_saved_by_verifier": False},
        "cipher_dispatch_table": {"address": hex(vtable_at), "body_offset": hex(vtable_at-MAIN_BASE),
                                  "entries": [hex(x) for x in vtable],
                                  "decrypt_initializer_slot": "0x1c", "decrypt_update_slot": "0x24"},
        "manual_static_interpretation": {
            "key": "Startup copies the 16-byte key to RAM 0x74000028. The updater copies it into its update context, then passes it to the AES object with a 128-bit key-size setting.",
            "iv_and_mode": "The updater takes the IV from outer header offset 0x80 and selects mode 1. The core decrypt loop decrypts each ciphertext block and XORs it with the previous ciphertext/initial IV, agreeing with CBC.",
            "legacy_header": "0x7bcd5ab6 requires UPD followed by zero and format 0x101. 0x7bcd5faa accepts digest selector 0 or 2 at 0x2c, zero at 0x30, and cipher selector 0 or 2 at 0x34, with additional model/version and cross-field checks.",
            "digest": "Digest selector 2 constructs an MD5 object; the decrypt job compares the computed digest against header offset 0x40. The independent full-file AES control reproduces that MD5.",
            "gm5_difference": "The GM5 sample has format 0x200 and value 3 at both 0x2c and 0x34. These fail the selected legacy checks. This does not assign a cipher, digest or key-derivation meaning to value 3 in GM5's unexamined updater.",
            "extra_file_writer": "0x400f021d passes a caller-supplied buffer/length to the known file writer. Its traced callers at 0x40025fd7 and 0x40025ffc first call the settings text formatter 0x401df73f. This route does not establish an executable firmware export.",
            "filenames": "Exact direct little-endian pointers to the four filename starts were not found. Computed, relative or aliased references are not excluded. No read/write consumer or activation recipe has been established for these names.",
        },
        "unresolved_filenames": filenames,
        "limits": {"gm5_decrypted": False, "gm5_key_recovered": False,
                   "sd_firmware_export_established": False,
                   "camera_or_lan_contacted": False, "camera_instructions_executed": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path)
    parser.add_argument("--gh2-update", type=Path, default=Path("work/legacy-control/GH2__V12.bin"))
    parser.add_argument("--gm5-update", type=Path, default=Path("firmware/official-gm5-v11/GM5__V11.bin"))
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--openssl", type=Path, default=Path("/usr/bin/openssl"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError("Output already exists")
        report = make_report(args.body, args.gh2_update, args.gm5_update, args.decoder, args.openssl)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Verification failed: {error}\n")


if __name__ == "__main__":
    main()
