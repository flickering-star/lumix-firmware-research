#!/usr/bin/env python3
"""Verify clear-component controls in one official Panasonic UPD v2 image.

Reads pinned local TZ30 and GM5 samples. Disassembles the clear TZ30
map module and tests one precisely defined GM5 AES hypothesis using host OpenSSL.
No extracted program or camera instruction is executed; no device is contacted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

from gh2_debug_verify import checked_disassembly


TZ30_SHA256 = "fbc51b27e38008b9aef0146b55d1683035c86c076d1890ed44af232c70309cb2"
GM5_SHA256 = "d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def records(data: bytes, expected_model: bytes) -> list[dict]:
    if len(data) < 0x600 or data[:4] != b"UPD\0" or data[12:28].split(b"\0")[0] != expected_model:
        raise ValueError("Unexpected model or UPD marker")
    if struct.unpack_from("<II", data, 4) != (512, 512):
        raise ValueError("Unexpected header length or format revision")
    if data[:0x40] != data[0x2A0:0x2E0]:
        raise ValueError("Repeated header differs")
    if data[0x200:0x20C] != b"panasonic\0\0\0":
        raise ValueError("Inner vendor marker differs")
    if struct.unpack_from("<I", data, 0x3C)[0] != len(data)-512:
        raise ValueError("Body length differs")
    if struct.unpack_from("<I", data, 0x40)[0] != zlib.crc32(data[512:]):
        raise ValueError("Outer body CRC differs")
    count = struct.unpack_from("<I", data, 0x2E8)[0]
    if not 0 < count <= 64 or 0x2EC+count*0x5C > len(data):
        raise ValueError("Directory bounds differ")
    result = []
    for i in range(count):
        at = 0x2EC+i*0x5C
        name, relative, size, dest, flags, field32, field16, reserved = struct.unpack_from("<12s4I32s16s16s", data, at)
        start = relative+512
        if start < 0x2EC+count*0x5C or start+size > len(data) or size % 16:
            raise ValueError("Component range differs")
        result.append({"name": name.split(b"\0")[0].decode("ascii"),
                       "file_offset": start, "bytes": size, "flags": flags,
                       "destination_candidate": dest, "field32": field32.hex(),
                       "field16": field16.hex()})
    ordered = sorted((r for r in result if r["bytes"]), key=lambda r: r["file_offset"])
    if any(a["file_offset"]+a["bytes"] > b["file_offset"] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Overlapping nonempty components")
    if len({r["name"] for r in result}) != count:
        raise ValueError("Duplicate component names")
    return result


def pack_members(data: bytes) -> dict:
    if len(data) < 28 or data[:4] != b"PACK":
        raise ValueError("Expected PACK marker")
    revision, table_offset, table_size, data_offset, data_size, count = struct.unpack_from("<6I", data, 4)
    if revision != 0x100 or table_offset != 24 or table_size != 4+20*count or data_offset != 24+table_size:
        raise ValueError("PACK header/directory relation differs")
    if data_offset+data_size > len(data):
        raise ValueError("PACK data range differs")
    result = []
    for i in range(count):
        rawname, start, size = struct.unpack_from("<12sII", data, 28+i*20)
        name = rawname.split(b"\0")[0].decode("ascii")
        if not name or Path(name).name != name or "\\" in name:
            raise ValueError("Unexpected PACK member path")
        if start < data_offset or start+size > data_offset+data_size:
            raise ValueError("PACK member range differs")
        raw = data[start:start+size]
        result.append({"name": name, "offset": start, "bytes": size,
                       "sha256": sha(raw), "first_eight_bytes": raw[:8].hex()})
    ordered = sorted(result, key=lambda r: r["offset"])
    if any(a["offset"]+a["bytes"] > b["offset"] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Overlapping PACK members")
    return {"format": hex(revision), "directory_entries": count,
            "data_offset": data_offset, "data_bytes": data_size,
            "padding_after_data_bytes": len(data)-data_offset-data_size, "members": result}


def make_report(tz30: Path, gm5: Path, map_module: Path, decoder: Path,
                openssl: Path) -> dict:
    data, gm5_data = tz30.read_bytes(), gm5.read_bytes()
    if sha(data) != TZ30_SHA256 or sha(gm5_data) != GM5_SHA256:
        raise ValueError("Pinned official BIN input differs")
    tz_records, gm5_records = records(data, b"TZ30"), records(gm5_data, b"GM5")
    clear = []
    packs = {}
    for record in tz_records:
        at, size = record["file_offset"], record["bytes"]
        raw = data[at:at+size]
        if record["flags"] == 2:
            actual = sha(raw)
            if actual != record["field32"] or record["field16"] != "00"*16:
                raise ValueError("Clear-component SHA256/zero-field control differs")
            clear.append({**record, "actual_sha256": actual,
                          "field32_equals_stored_component_sha256": True})
            if raw[:4] == b"PACK":
                packs[record["name"]] = pack_members(raw)
    if [r["name"] for r in clear] != ["storage", "history", "packfile", "web_uploade",
                                       "avchd_info", "map", "map_prog", "gps_assist"]:
        raise ValueError("Clear-component inventory differs")

    module_record = next(r for r in clear if r["name"] == "map_prog")
    module = map_module.read_bytes()
    if sha(module) != module_record["field32"] or len(module) != module_record["bytes"]:
        raise ValueError("Map-module extraction differs from the official component")
    base = 0x79600000
    references = []
    for instruction_offset, literal_offset, string_offset, text in (
        (0x40, 0x42, 0x100F8, b"MwMapLib_Mp_Initialize\r\n\0"),
        (0x73, 0x75, 0x10111, b"MwMapLib_Mp_Initialize - 1\r\n\0"),
        (0x9E, 0xA0, 0x1012E, b"MwMapLib_Mp_Initialize - 2\r\n\0"),
    ):
        address = struct.unpack_from("<I", module, literal_offset)[0]
        if address-base != string_offset or module[string_offset:string_offset+len(text)] != text:
            raise ValueError("Map-module instruction/string link differs")
        references.append({"instruction": hex(base+instruction_offset),
                           "string_address": hex(address), "string_file_offset": hex(string_offset)})
    disassembly, count = checked_disassembly(map_module, module, decoder, base,
                                            base+0x1C, base+0xA6)

    candidates = []
    for record in gm5_records:
        at, size = record["file_offset"], record["bytes"]
        raw = gm5_data[at:at+size]
        candidate = subprocess.check_output([
            str(openssl), "enc", "-d", "-aes-256-cbc", "-nopad",
            "-K", record["field32"], "-iv", record["field16"],
        ], input=raw)
        candidates.append({"component": record["name"],
                           "hypothesis": "AES-256-CBC, directory field32 directly as key, field16 as IV",
                           "candidate_sha256": sha(candidate),
                           "matches_directory_field32": sha(candidate) == record["field32"]})

    return {
        "schema": 1,
        "scope": "Related-camera clear-component controls; does not recover GM5 plaintext or an update key",
        "sources": {"tz30": {"path": str(tz30), "bytes": len(data), "sha256": TZ30_SHA256,
                             "official_url": "https://av.jpn.support.panasonic.com/support/share/eww/en/dsc/tz30_tz31_zs20/TZ30_V12.zip",
                             "body_length_crc_and_repeated_header_verified": True},
                    "gm5": {"path": str(gm5), "bytes": len(gm5_data), "sha256": GM5_SHA256}},
        "verifier": {"path": "tools/tz30_control_verify.py", "sha256": sha(Path(__file__).read_bytes()),
                     "decoder": str(decoder), "decoder_sha256": sha(decoder.read_bytes()),
                     "openssl": str(openssl)},
        "clear_components": clear, "clear_pack_archives": packs,
        "readable_map_code": {"source_path": str(map_module), "sha256": sha(module),
                              "file_zero_base_supported_by_string_refs": hex(base),
                              "instruction_string_links": references,
                              "reviewed_region": {"start": hex(base+0x1C), "end_exclusive": hex(base+0xA6),
                                                  "instructions": count, "raw_annotations_match_source": True,
                                                  "disassembly": disassembly},
                              "role": "Map-library initializer; no updater or GM5 code established"},
        "gm5_bounded_aes_hypothesis": candidates,
        "interpretation": {
            "field32": "All eight flag-2 entries, including the empty storage entry, equal SHA256 of their exact stored component bytes. This is a positive control for those fields in TZ30's format-0x200 image.",
            "gm5": "GM5 has structurally matching directory fields. A plaintext SHA256 interpretation for its flag-3 components is supported by comparison but remains unverified until a genuine decode/read is obtained.",
            "cipher_hypothesis": "Using the directory's 32-byte value directly as an AES-256-CBC key with its 16-byte field as IV is one explicit hypothesis, not a cipher identification. The output digest comparison tests that hypothesis against the inferred plaintext-digest role.",
            "limits": "No main TZ30 program decryption, GM5 decryption, modified firmware creation, camera communication or target-code execution occurred.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tz30", type=Path)
    parser.add_argument("--gm5", type=Path, default=Path("firmware/official-gm5-v11/GM5__V11.bin"))
    parser.add_argument("--map-module", type=Path, default=Path("work/transition-tz30/map_prog.raw"))
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--openssl", type=Path, default=Path("/usr/bin/openssl"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError("Output already exists")
        report = make_report(args.tz30, args.gm5, args.map_module, args.decoder, args.openssl)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Verification failed: {error}\n")


if __name__ == "__main__":
    main()
