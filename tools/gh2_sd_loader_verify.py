#!/usr/bin/env python3
"""Recheck GH2 factory SD-input paths and one marker consumer offline.

Pins a GH2 plaintext and an official Panasonic lens-file control, then checks
native bytes and call links. No S-record image, USB packet or camera operation
is produced. Native semantics are manual interpretations, not an emulator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from gh2_debug_verify import BODY_SHA256, MAIN_BASE, SECONDARY_BASE, checked_disassembly, verify_input


LENS_SHA256 = "ce9499157483ec1570cce8317d9606bdacc361fa8bc40664474c31be2c9ccc9e"
REGIONS = (
    ("startup_factory_and_service_branches", MAIN_BASE, 0x4000385A, 0x400038BB),
    ("startup_input_predicates", SECONDARY_BASE, 0x7BCCB358, 0x7BCCB477),
    ("additional_hardware_predicate", MAIN_BASE, 0x401457B9, 0x401457DF),
    ("sd_factory_job", MAIN_BASE, 0x40060E1F, 0x40060FF3),
    ("ahx_file_reader", MAIN_BASE, 0x400F9154, 0x400F9246),
    ("hex_byte_decoder", MAIN_BASE, 0x400F9246, 0x400F928D),
    ("hex_address_decoder", MAIN_BASE, 0x400F928D, 0x400F9384),
    ("s3_record_parser", MAIN_BASE, 0x400F9384, 0x400F946A),
    ("programming_preparation", MAIN_BASE, 0x400F946A, 0x400F9804),
    ("programming_core_ram_copy", MAIN_BASE, 0x400F9ED1, 0x400F9EED),
    ("parallel_flash_helpers_and_copies", SECONDARY_BASE, 0x7BCB827A, 0x7BCB833F),
    ("marker_read_and_ram_flag", MAIN_BASE, 0x40154FF3, 0x40155025),
    ("lens_header_marker_consumer", MAIN_BASE, 0x400F8B32, 0x400F8C90),
)
CALLS = (
    (0x40003861, 0x7BCCB371), (0x4000386E, 0x40060E1F),
    (0x4000387C, 0x7BCCB431), (0x4000388A, 0x40060E1F),
    (0x7BCCB3A3, 0x401457B9), (0x7BCCB463, 0x401457B9),
    (0x40060F09, 0x40154FF3), (0x40060F2F, 0x400F9154),
    (0x40060F58, 0x400F9154), (0x40060FA1, 0x400F946A),
    (0x400F91DD, 0x400F9384), (0x400F93ED, 0x400F928D),
    (0x400F9414, 0x400F9246), (0x400F97C7, 0x400F9ED1),
    (0x400F8C04, 0x4015501C),
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_report(body: Path, lens: Path, decoder: Path) -> dict:
    data = body.read_bytes()
    verify_input(data)
    lens_data = lens.read_bytes()
    if sha(lens_data) != LENS_SHA256 or lens_data[:2] != b"PL":
        raise ValueError("Pinned official lens control differs")
    regions = []
    for name, base, start, end in REGIONS:
        output, count = checked_disassembly(body, data, decoder, base, start, end)
        regions.append({"name": name, "file_zero_base": hex(base),
                        "start": hex(start), "end_exclusive": hex(end),
                        "body_offset": hex(start-base), "bytes": end-start,
                        "sha256": sha(data[start-base:end-base]), "instructions": count,
                        "raw_annotations_match_source": True, "disassembly": output})
    calls = []
    for at, expected in CALLS:
        base = SECONDARY_BASE if at >= 0x7BBC0000 else MAIN_BASE
        off = at-base
        if data[off] not in (0xCD, 0xDD):
            raise ValueError(f"Missing relative call at {at:#x}")
        target = (at+struct.unpack_from("<h" if data[off] == 0xCD else "<i", data, off+1)[0]) & 0xFFFFFFFF
        if target != expected:
            raise ValueError(f"Relative call differs at {at:#x}")
        calls.append({"address": hex(at), "target": hex(target)})
    strings = []
    for offset, expected in ((0x20D5B4, b"A:\\GH2.AHX\0"),
                             (0x20D5BF, b"A:\\GH2E.AHX\0"),
                             (0x249CE4, b"A:\\ESFFFFFF.BIN\0rb\0")):
        if data[offset:offset+len(expected)] != expected:
            raise ValueError("Factory-input string differs")
        strings.append({"body_offset": hex(offset), "main_address": hex(MAIN_BASE+offset),
                        "bytes_hex": expected.hex()})
    source = struct.unpack_from("<I", data, 0x400F9ED4-MAIN_BASE)[0]
    source_end = struct.unpack_from("<I", data, 0x400F9EDC-MAIN_BASE)[0]
    if (source, source_end) != (0x400F9804, 0x400F9ECD):
        raise ValueError("Programming-core RAM-copy constants differ")

    return {
        "schema": 1,
        "scope": "Static GH2 factory SD inputs; not a GM5 procedure or plaintext dump",
        "source": {"path": str(body), "bytes": len(data), "sha256": BODY_SHA256},
        "verifier": {"path": "tools/gh2_sd_loader_verify.py", "sha256": sha(Path(__file__).read_bytes()),
                     "decoder": str(decoder), "decoder_sha256": sha(decoder.read_bytes())},
        "mechanical_checks": {"regions": regions, "calls": calls, "literal_strings": strings},
        "ahx_manual_review": {
            "startup": "Predicate 0x7bccb371 requires drive decoder result 3, raw AF/AE LOCK 0x400, DISPLAY predicate and hardware predicate 0x401457b9. It calls the factory job with mode zero. Normal temporary service entry uses a different predicate/drive result.",
            "hardware_gate": "The additional predicate requires bit 0x02 of MMIO 0x9c00c082 to remain clear across ten reads and has a state-update side effect. The physical signal's name is unresolved here.",
            "files": "Mode zero tries A:\\GH2.AHX, then A:\\GH2E.AHX. It stages decoded bytes at 0xb5000000; successful fallback selects job mode 3 for the programming helper.",
            "record_format": "The parser recognizes ASCII S3 data records, reads an eight-hex-character address and checks it against the caller's sequential expected offset. Data is stored at staging base plus that offset. It checks an additive one's-complement checksum and CRLF; the caller advances 48 text bytes and 16 decoded bytes per data record.",
            "termination_limits": "The helper returns 7 for a non-S3 record beginning with S. Full strict S7 trailer validation is not established. This is a description of the inspected reader, not a complete generic S-record validator.",
            "programming": "The job calls 0x400f946a after its additional extent check. That helper preserves selected existing data in the staged image, copies native programming routines into RAM, then calls the copied core indirectly. A reviewed helper issues 16-bit command/data writes and polls the target. This is an image-input/programming direction, not a firmware-export routine.",
            "copied_core": {"source_start": hex(source), "source_end_exclusive": hex(source_end),
                            "source_bytes": source_end-source, "copy_helper": "0x400f9ed1",
                            "indirect_call": "0x400f97fe"},
            "validation_limits": "No AES operation was identified in the reviewed S3 record parser. That does not establish complete image acceptance or the absence of other checks in every programming branch.",
        },
        "marker_manual_review": {
            "startup": "A separate predicate 0x7bccb431 uses drive result 1 with the same raw keys and additional hardware predicate, then calls the factory job with mode one.",
            "effect": "Mode one calls 0x40154ff3, which opens A:\\ESFFFFFF.BIN in rb mode. Successful open sets RAM byte 0x7435d728 to 1, closes the file, and returns. The file's contents are not read in this routine.",
            "consumer": "Getter 0x4015501c is called at 0x400f8c04 in a header validator that first requires second byte L and classifies first-byte O/S/P/R/Q. A nonzero flag skips several later metadata comparisons, after the initial structure checks.",
            "lens_control": "The official H-FS12032 lens update has PL magic and matching header field positions. This establishes a lens-file control for the inspected validator; it does not establish that GH2 accepts that particular 2020 lens version.",
            "limits": "The remaining flag consumers are not fully classified. No link to a text shell, body-firmware AES-key extraction or a GM5 counterpart is established.",
        },
        "official_lens_control": {"path": str(lens), "bytes": len(lens_data), "sha256": LENS_SHA256,
                                  "official_model_page": "https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/fs12032.html",
                                  "magic": lens_data[:2].decode(),
                                  "u16_at_0x02": hex(struct.unpack_from("<H", lens_data, 2)[0]),
                                  "u16_at_0x04": hex(struct.unpack_from("<H", lens_data, 4)[0]),
                                  "u32_at_0x0c": hex(struct.unpack_from("<I", lens_data, 12)[0]),
                                  "u16_at_0x10": hex(struct.unpack_from("<H", lens_data, 16)[0])},
        "s_record_reference": "https://www.nxp.com/docs/en/reference-manual/DSPFAQ11478_LINKER.UM.pdf",
        "limits": {"camera_or_lens_contacted": False, "sd_image_or_marker_written": False,
                   "target_code_executed": False, "gm5_support_established": False,
                   "plaintext_dump_mechanism_established": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path)
    parser.add_argument("--lens-control", type=Path, default=Path("work/lens-control/ES102012.lin"))
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError("Output already exists")
        report = make_report(args.body, args.lens_control, args.decoder)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Verification failed: {error}\n")


if __name__ == "__main__":
    main()
