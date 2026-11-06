#!/usr/bin/env python3
"""Check GH2 service-button mapping and USB preparation against pinned inputs.

Reads local firmware, a service manual, and historical host binaries. Invokes
host disassemblers only; never loads the Windows binaries or contacts a device.
The semantic conclusions in the report remain manual static interpretations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from gh2_debug_verify import MAIN_BASE, SECONDARY_BASE, checked_disassembly
from gh2_usb_entry_verify import make_report as verify_entry


MANUAL_SHA256 = "e885754a31db62848ddace241f27995f6b0e62bd06e199baeb373d4d39430f8c"
PE_HASHES = {
    "mkeusb01.sys": "2528eaafc48e8bb87f2828963897f5ec7698314337cda98853d662bb51d25801",
    "mkeusb01.dll": "504052d9e34d4d97578ca84bcbac21c688782c11e1e603a69ca86dbd86ca2458",
}
REGIONS = (
    ("initialized_data_copy", MAIN_BASE, 0x40002000, 0x40002034),
    ("all_related_boot_predicates", SECONDARY_BASE, 0x7BCCB358, 0x7BCCB477),
    ("boot_predicate_calls", MAIN_BASE, 0x4000385A, 0x400038BB),
    ("absolute_difference_helper", SECONDARY_BASE, 0x7BC515A0, 0x7BC515AC),
    ("analog_input_acquisition", SECONDARY_BASE, 0x7BCCA443, 0x7BCCA497),
    ("rear_key_decoders", SECONDARY_BASE, 0x7BCCA999, 0x7BCCAA55),
    ("drive_lever_decoder", SECONDARY_BASE, 0x7BCCAA55, 0x7BCCAAC5),
    ("raw_to_ui_key_mapping", SECONDARY_BASE, 0x7BCCAFE2, 0x7BCCB08A),
    ("key_event_and_repeat_fields", SECONDARY_BASE, 0x7BCCB1B5, 0x7BCCB25B),
    ("setup_packet_decode", MAIN_BASE, 0x401E966D, 0x401E96BF),
    ("setup_request_type", MAIN_BASE, 0x401E96EB, 0x401E970A),
    ("setup_request_dispatch", MAIN_BASE, 0x401E74CD, 0x401E755B),
    ("vendor_bulk_preparation", MAIN_BASE, 0x401EED80, 0x401EEE32),
    ("endpoint_preparation_helper", MAIN_BASE, 0x401EA03C, 0x401EA0A6),
    ("bulk_receive_to_command_state", MAIN_BASE, 0x401EEFC2, 0x401EF059),
    ("binary_header_decode", MAIN_BASE, 0x401EF4B2, 0x401EF592),
)
CALLS = (
    (0x7BCCB35E, 0x7BCCAA02),
    (0x7BCCB3C3, 0x7BCCAA55),
    (0x7BCCB3CF, 0x7BCCA999),
    (0x7BCCB3DF, 0x7BCCB358),
    (0x7BCCA9BE, 0x7BC515A0),
    (0x7BCCAA2A, 0x7BC515A0),
    (0x7BCCB06F, 0x7BCCB1B5),
    (0x401E74E6, 0x401E966D),
    (0x401E74F1, 0x401E96EB),
    (0x401E7549, 0x401EED80),
    (0x401EED94, 0x401EEDAD),
    (0x401EED9B, 0x401EEDEF),
    (0x401EEDCC, 0x401EA03C),
    (0x401EEEAB, 0x401EF0A5),
    (0x401EF015, 0x401EF4B2),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pe_offset(data: bytes, address: int) -> int:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe+4] != b"PE\0\0" or struct.unpack_from("<H", data, pe+4)[0] != 0x14C:
        raise ValueError("Expected the pinned i386 PE input")
    optional = pe + 24
    base = struct.unpack_from("<I", data, optional+28)[0]
    sections = optional + struct.unpack_from("<H", data, pe+20)[0]
    for i in range(struct.unpack_from("<H", data, pe+6)[0]):
        at = sections + 40*i
        _, rva, size, raw = struct.unpack_from("<4I", data, at+8)
        if rva <= address-base < rva+size:
            return raw + address-base-rva
    raise ValueError(f"PE address outside backed sections: {address:#x}")


def checked_pe_region(path: Path, data: bytes, decoder: Path,
                      start: int, end: int) -> dict:
    output = subprocess.check_output([
        str(decoder), "-d", "--x86-asm-syntax=intel",
        f"--start-address={start:#x}", f"--stop-address={end:#x}", str(path),
    ], text=True)
    cursor = start
    count = 0
    for line in output.splitlines():
        match = re.match(r"^\s*([0-9a-f]+):\s*([0-9a-f ]+)\t", line)
        if not match:
            continue
        at, raw = int(match[1], 16), bytes.fromhex(match[2])
        off = pe_offset(data, at)
        if at != cursor or data[off:off+len(raw)] != raw or "(bad)" in line:
            raise ValueError(f"PE instruction bytes/continuity differ at {at:#x}")
        cursor += len(raw)
        count += 1
    if cursor != end:
        raise ValueError(f"PE region ended at {cursor:#x}, expected {end:#x}")
    begin = pe_offset(data, start)
    return {"source": str(path), "start": hex(start), "end_exclusive": hex(end),
            "bytes": end-start, "native_sha256": sha256(data[begin:begin+end-start]),
            "instruction_count": count, "raw_annotations_match_source": True,
            "disassembly": output}


def make_report(body: Path, decoder: Path, observation: Path,
                manual: Path, fz30_root: Path, pe_decoder: Path) -> dict:
    entry = verify_entry(body, decoder, observation)
    data = body.read_bytes()
    if sha256(manual.read_bytes()) != MANUAL_SHA256:
        raise ValueError("GH2 service-manual input differs")
    regions = []
    for name, base, start, end in REGIONS:
        output, count = checked_disassembly(body, data, decoder, base, start, end)
        regions.append({"name": name, "file_zero_base": hex(base),
                        "start": hex(start), "end_exclusive": hex(end),
                        "body_offset": hex(start-base), "bytes": end-start,
                        "native_sha256": sha256(data[start-base:end-base]),
                        "instruction_count": count, "raw_annotations_match_source": True,
                        "disassembly": output})
    calls = []
    for at, expected in CALLS:
        base = SECONDARY_BASE if at >= 0x7BBC0000 else MAIN_BASE
        off = at-base
        opcode = data[off]
        if opcode not in (0xCD, 0xDD):
            raise ValueError(f"Relative call missing at {at:#x}")
        target = (at + struct.unpack_from("<h" if opcode == 0xCD else "<i", data, off+1)[0]) & 0xFFFFFFFF
        if target != expected:
            raise ValueError(f"Relative call differs at {at:#x}")
        calls.append({"address": hex(at), "target": hex(target)})

    load_start = struct.unpack_from("<I", data, 0x40002018-MAIN_BASE)[0]
    load_end = struct.unpack_from("<I", data, 0x4000201E-MAIN_BASE)[0]
    ram_start = struct.unpack_from("<I", data, 0x40002028-MAIN_BASE)[0]
    if (load_start, load_end, ram_start) != (0x407F6384, 0x4080CFF8, 0x743551F4):
        raise ValueError("Initialized-data copy constants differ")
    table_offset = 0x80BFCC
    table_ram = ram_start + MAIN_BASE + table_offset - load_start
    if table_ram != 0x7436AA3C:
        raise ValueError("Key mapping initializer does not map to its consumer")
    table_raw = data[table_offset:table_offset+160]
    key_map = dict(struct.iter_unpack("<II", table_raw))
    if set(key_map) != {1 << n for n in range(20)}:
        raise ValueError("Expected twenty distinct input key bits")
    for raw, ui in ((0x800, 0x40), (0x400, 0x400), (0x80, 0x80),
                    (0x100, 0x20), (0x200, 0x2000), (0x1000, 0x10)):
        if key_map[raw] != ui:
            raise ValueError("Reviewed key mapping differs")
    fixed_base = 0xEC0400
    key_centers = struct.unpack_from("<4H", data, fixed_base+0x7400B106-0x74003B38)
    drive_centers = struct.unpack_from("<4H", data, fixed_base+0x7400B0D0-0x74003B38)
    if key_centers != (0, 198, 395, 593) or drive_centers != (0, 270, 538, 810):
        raise ValueError("Reviewed analog reference values differ")

    binaries = {}
    for filename, expected in PE_HASHES.items():
        path = fz30_root/filename
        raw = path.read_bytes()
        if sha256(raw) != expected:
            raise ValueError(f"Historical host input differs: {filename}")
        binaries[filename] = (path, raw)
    pe_regions = []
    for filename, start, end in (
        ("mkeusb01.dll", 0x1000102D, 0x10001032),
        ("mkeusb01.dll", 0x10001032, 0x10001037),
        ("mkeusb01.dll", 0x100019A0, 0x10001A50),
        ("mkeusb01.dll", 0x10001A50, 0x10001ADA),
        ("mkeusb01.sys", 0x10CBC, 0x10D3A),
        ("mkeusb01.sys", 0x114A3, 0x114E8),
        ("mkeusb01.sys", 0x10D3A, 0x10DB5),
    ):
        path, raw = binaries[filename]
        pe_regions.append(checked_pe_region(path, raw, pe_decoder, start, end))
    for filename, at, expected, opcode in (
        ("mkeusb01.dll", 0x1000102D, 0x100019A0, 0xE9),
        ("mkeusb01.dll", 0x10001032, 0x10001A50, 0xE9),
        ("mkeusb01.sys", 0x1149C, 0x10CBC, 0xE8),
        ("mkeusb01.sys", 0x114E1, 0x10D3A, 0xE8),
        ("mkeusb01.sys", 0x10D97, 0x102CA, 0xE8),
    ):
        raw = binaries[filename][1]
        off = pe_offset(raw, at)
        if raw[off] != opcode or at+5+struct.unpack_from("<i", raw, off+1)[0] != expected:
            raise ValueError(f"Historical host call/branch differs at {at:#x}")

    return {
        "schema": 1,
        "scope": "Static GH2 service-input and USB-preparation follow-up; no GM5 compatibility or hardware validation",
        "source": entry["source"],
        "verifier": {"path": "tools/gh2_usb_service_verify.py", "sha256": sha256(Path(__file__).read_bytes()),
                     "entry_verifier": entry["verifier"], "decoder": entry["decoder"],
                     "pe_decoder": str(pe_decoder), "pe_decoder_sha256": sha256(pe_decoder.read_bytes())},
        "earlier_entry_checks_reperformed": {
            "reference": "evidence/gh2-usb-maintenance-entry.json",
            "regions": len(entry["mechanical_checks"]["regions"]),
            "instructions": sum(x["instruction_count"] for x in entry["mechanical_checks"]["regions"]),
            "relative_calls": len(entry["mechanical_checks"]["relative_calls"]),
            "descriptor_positive_controls": entry["descriptor_positive_controls"],
        },
        "mechanical_checks": {"regions": regions, "relative_calls": calls,
                              "historical_host_regions": pe_regions},
        "key_mapping": {
            "initializer_body_offset": hex(table_offset), "initializer_sha256": sha256(table_raw),
            "copy_load_start": hex(load_start), "copy_load_end_exclusive": hex(load_end),
            "copy_ram_start": hex(ram_start), "consumer_ram_address": hex(table_ram),
            "raw_to_ui_bits": {hex(k): hex(v) for k, v in key_map.items()},
            "default_analog_key_centers": key_centers, "default_drive_centers": drive_centers,
            "matching_rule": "Absolute difference from a calibration reference is less than 59; these are default flash values, not measurements of the owner's camera",
            "manual_interpretation": {
                "DISPLAY": {"raw": "0x800", "ui": "0x40", "ladder": "REAR_KEYIN2, 2.4 kilohms from the input"},
                "AF_AE_LOCK": {"raw": "0x400", "ui": "0x400", "ladder": "REAR_KEYIN1, 2.4 kilohms from the input"},
                "DELETE": {"raw": "0x80", "ui": "0x80", "ladder": "REAR_KEYIN1, 13.8 kilohms from the input"},
                "startup": "The predicate requires drive result 2, raw AF/AE LOCK 0x400 and DISPLAY 0x800, with settings state 1. This agrees with the manual's documented temporary service entry; the drive-position label is corroborated by that procedure rather than an independent live measurement.",
                "override": "The separate RAM-override consumer's UI event bit 0x80 maps to DELETE. Full timing/state activation remains unresolved; no standalone button recipe is established.",
            },
        },
        "service_manual": {"url": "https://www.partstown.com/modelManual/PAN-DMCGH2_sm.pdf?v=1670948469862",
                           "path": str(manual), "sha256": MANUAL_SHA256, "bytes": manual.stat().st_size,
                           "order_number": "DSC1011058CE", "pdf_pages": 85,
                           "reviewed_pdf_pages": [14, 21, 60], "schematic_printed_page": "S-5"},
        "usb_preparation_manual_review": {
            "setup_fields": {"bmRequestType": "0x744dd1f8", "bRequest": "0x744dd1f9",
                             "wValue": "0x744dd1fa", "wIndex": "0x744dd1fc", "wLength": "0x744dd1fe"},
            "routing": "0x401e96eb decodes (bmRequestType & 0x60) >> 5. Vendor type reaches 0x401eed80 only when descriptor mode is 2.",
            "request_zero": "0x401eed80 accepts bRequest zero; wIndex zero calls 0x401eedad, nonzero calls 0x401eedef. wValue is not read in these two routines.",
            "index_zero": "Clears two maintenance-state words, sets bulk phase 3 and receive state 5, prepares an endpoint and control status. No flash-writing routine is identified in this reviewed path.",
            "index_nonzero": "Restores bulk phase 3, readies pending transfer state and resets the transfer cursor. Historical host calls name the matching control preparation preBulkRead_CZ30.",
            "scope": "These are transfer-preparation operations after vendor mode selection. They do not establish entry from ordinary PC/PTP mode, a key-extraction command, or complete request validation.",
        },
        "historical_host_comparison": {
            "sources": [{"path": str(p), "bytes": len(raw), "sha256": sha256(raw)} for p, raw in binaries.values()],
            "pre_bulk_write": {"export": "preBulkWrite_CZ30", "export_thunk": "0x10001032",
                               "body": "0x10001a50", "ioctl": "0x230034",
                               "driver_handler": "0x10d3a", "urb_function": "0x17 URB_FUNCTION_VENDOR_DEVICE",
                               "usb_request_type": "0x40", "request": 0, "index": 0,
                               "value": "Caller-supplied 16-bit value", "length": 0},
            "pre_bulk_read": {"export": "preBulkRead_CZ30", "ioctl": "0x230030",
                              "driver_handler": "0x10cbc", "request": 0, "index": 1,
                              "provenance": "Static review of the pinned host binaries; selected instructions and call links checked above"},
            "abi_sources": ["https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usb/ns-usb-_urb_control_vendor_or_class_request",
                            "https://raw.githubusercontent.com/microsoft/win32metadata/main/generation/WinSDK/RecompiledIdlHeaders/shared/usb.h"],
            "interpretation": "The older host's request-zero/index-zero OUT preparation agrees with the GH2 camera-side path; this is independent static evidence, not a captured transaction.",
        },
        "limitations": {"physical_camera_contacted": False, "firmware_or_windows_driver_executed": False,
                        "gm5_service_entry_confirmed": False, "gm5_vendor_requests_sent": False,
                        "complete_ram_override_sequence_established": False,
                        "packet_validation_fully_traced": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--gm5-observation", type=Path, default=Path("evidence/gm5-usb-pc-ptp.json"))
    parser.add_argument("--manual", type=Path, default=Path("work/gh2-service-inputs/GH2-service.pdf"))
    parser.add_argument("--fz30-root", type=Path, default=Path("work/service-software/fz30-files"))
    parser.add_argument("--pe-decoder", type=Path, default=Path("/usr/bin/objdump"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = make_report(args.body, args.decoder, args.gm5_observation,
                             args.manual, args.fz30_root, args.pe_decoder)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Verification failed: {error}\n")


if __name__ == "__main__":
    main()
