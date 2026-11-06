#!/usr/bin/env python3
"""Verify the reviewed GH2 USB service-entry regions and GM5 descriptor controls.

Offline only: reads pinned plaintext and saved USB observations, and invokes the
host disassembler. The descriptor model expresses manually reviewed semantics;
they do not execute firmware or establish a GM5 service-entry procedure.
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


REGIONS = (
    ("boot_state_override", MAIN_BASE, 0x40003891, 0x400038BB),
    ("boot_input_predicate", SECONDARY_BASE, 0x7BCCB3B7, 0x7BCCB3F7),
    ("temporary_override_event", MAIN_BASE, 0x400D6475, 0x400D64D0),
    ("prepare_service_selection", MAIN_BASE, 0x400D6524, 0x400D6556),
    ("service_eligibility", MAIN_BASE, 0x400D6556, 0x400D6587),
    ("connection_service_branch", MAIN_BASE, 0x400D50D6, 0x400D50FF),
    ("connection_request", MAIN_BASE, 0x400E9A8F, 0x400E9B17),
    ("enqueue_mode_record", MAIN_BASE, 0x401E678D, 0x401E67CE),
    ("settings_word_accessor", MAIN_BASE, 0x40155FF0, 0x40156017),
    ("message_dispatch", MAIN_BASE, 0x401F805D, 0x401F80B6),
    ("mode_record_dispatch", MAIN_BASE, 0x401F8356, 0x401F8380),
    ("ptp_mode_setup", MAIN_BASE, 0x401F8740, 0x401F87EE),
    ("storage_mode_setup", MAIN_BASE, 0x401F87EE, 0x401F88F5),
    ("service_mode_setup", MAIN_BASE, 0x401F88F5, 0x401F8977),
    ("device_descriptor_dispatch", MAIN_BASE, 0x401E8DB3, 0x401E8DE9),
    ("service_device_descriptor", MAIN_BASE, 0x401E8DE9, 0x401E8E5C),
    ("normal_device_descriptors", MAIN_BASE, 0x401E8E5C, 0x401E8FE7),
    ("configuration_descriptor", MAIN_BASE, 0x401E8FE7, 0x401E9173),
    ("configuration_caller", MAIN_BASE, 0x401E71DF, 0x401E7201),
    ("bulk_phase_dispatch", MAIN_BASE, 0x401E6AA3, 0x401E6AE4),
    ("pending_mode_to_maintenance_phase", MAIN_BASE, 0x401E6B40, 0x401E6B77),
)

CALLS = (
    (0x40003891, 0x7BCCB3B7),
    (0x400D50DD, 0x400D6556),
    (0x400D50F6, 0x400E9A8F),
    (0x400E9B0B, 0x401E678D),
    (0x401E67C4, 0x401F70C4),
    (0x401F80AE, 0x401F8356),
    (0x401F8368, 0x401F87EE),
    (0x401F8370, 0x401F8740),
    (0x401F8378, 0x401F88F5),
    (0x401F896D, 0x401E9808),
    (0x401E8DC7, 0x401E8DE9),
    (0x401E8DCE, 0x401E8E5C),
    (0x401E8DDC, 0x401E8EE3),
    (0x401E71E9, 0x401E8FE7),
    (0x401E6AC9, 0x401EEE32),
)


def configuration_model(mode: int, high_speed_layout: bool) -> bytes:
    """401e8fe7, with its argument equal to the current descriptor-mode byte.

    This equality is observed at caller 401e71e3..401e71e9. The speed name
    describes the 512-byte layout selected by hardware-register bit 0x20.
    """
    if mode not in (1, 2, 3):
        raise ValueError("Only the three reviewed descriptor modes are modeled")
    three = mode in (2, 3)
    packet = 512 if high_speed_layout else 64
    interface = {1: (8, 6, 0x50), 2: (0xFF, 0xA0, 0xB0), 3: (6, 1, 1)}[mode]
    result = bytes((9, 2, 39 if three else 32, 0, 1, 1, 0, 0xC0, 1,
                    9, 4, 0, 0, 3 if three else 2, *interface, 0))
    for address in (1, 0x82):
        result += bytes((7, 5, address, 2)) + struct.pack("<H", packet) + b"\0"
    if three:
        result += bytes((7, 5, 0x83, 3))
        result += struct.pack("<H", 8 if mode == 3 else packet)
        result += bytes((8 if high_speed_layout else 16,))
    return result


def make_report(body: Path, decoder: Path, observation: Path) -> dict:
    data = body.read_bytes()
    verify_input(data)
    calls = []
    for at, expected in CALLS:
        off = at - MAIN_BASE
        opcode = data[off]
        if opcode not in (0xCD, 0xDD):
            raise ValueError(f"Expected a relative call at {at:#x}")
        displacement = struct.unpack_from("<h" if opcode == 0xCD else "<i", data, off+1)[0]
        target = (at + displacement) & 0xFFFFFFFF
        if target != expected:
            raise ValueError(f"Call target differs at {at:#x}")
        calls.append({"address": hex(at), "target": hex(target)})

    table_address = 0x407F31A4
    table = data[table_address-MAIN_BASE:table_address-MAIN_BASE+64*8]
    pairs = list(struct.iter_unpack("<II", table))
    matches = [(i, value) for i, (key, value) in enumerate(pairs) if key == 0xD042]
    if matches != [(2, 0x401F80A8)]:
        raise ValueError("D042 mode-message table entry differs")

    regions = []
    for name, base, start, end in REGIONS:
        output, count = checked_disassembly(body, data, decoder, base, start, end)
        native = data[start-base:end-base]
        regions.append({
            "name": name, "file_zero_base": hex(base), "start": hex(start),
            "end_exclusive": hex(end), "body_offset": hex(start-base),
            "bytes": len(native), "native_sha256": hashlib.sha256(native).hexdigest(),
            "instruction_count": count, "raw_annotations_match_source": True,
            "disassembly": output,
        })

    observed_raw = observation.read_bytes()
    observed = json.loads(observed_raw)
    controls = []
    for mode, name in ((1, "pc"), (3, "ptp")):
        configs = observed[name]["configurations"]
        if len(configs) != 1:
            raise ValueError(f"Expected one saved GM5 {name} configuration")
        actual = bytes.fromhex(configs[0]["hex"])
        expected = configuration_model(mode, True)
        if actual != expected:
            raise ValueError(f"Mode {mode} model differs from measured GM5 {name} bytes")
        controls.append({"gh2_model_mode": mode, "gm5_observed_mode": name,
                         "bytes": len(actual), "byte_for_byte_match": True,
                         "hex": actual.hex()})

    layouts = [{"gh2_mode": mode, "high_speed_layout": speed,
                "bytes": len(configuration_model(mode, speed)),
                "hex": configuration_model(mode, speed).hex(),
                "provenance": "Manual semantic model of 0x401e8fe7; not a GH2 or GM5 live capture"}
               for mode in (1, 2, 3) for speed in (False, True)]
    return {
        "schema": 1,
        "scope": "Offline GH2 1.2 service-selection study, compared with saved normal GM5 USB descriptors",
        "source": {"path": str(body), "bytes": len(data), "sha256": BODY_SHA256},
        "verifier": {"path": "tools/gh2_usb_entry_verify.py",
                     "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     "shared_helpers": "tools/gh2_debug_verify.py",
                     "shared_helpers_sha256": hashlib.sha256(Path(__file__).with_name("gh2_debug_verify.py").read_bytes()).hexdigest()},
        "decoder": {"path": str(decoder), "sha256": hashlib.sha256(decoder.read_bytes()).hexdigest(),
                    "machine_argument": 332},
        "mechanical_checks": {
            "relative_calls": calls,
            "mode_message_table": {"address": hex(table_address), "entries": 64,
                                   "sha256": hashlib.sha256(table).hexdigest(),
                                   "message": "0xd042", "slot": 2, "branch": "0x401f80a8"},
            "regions": regions,
        },
        "manual_static_review": {
            "service_usb_identity": {"vid": "0x04da", "pid": "0x2370",
                                     "bcd_device": "0x0100", "interface": "ff/a0/b0",
                                     "bulk_out": "0x01", "bulk_in": "0x82", "interrupt_in": "0x83"},
            "settings_state": {"address": "0x74001e30", "update_buffer_relative_byte": "0x2f8",
                               "word_coordinate_if_same_layout": "H017 Lc",
                               "setter_accepts": [0, 1, 2],
                               "note": "GH2 consumer only; no GM1/GM5 field identity inferred"},
            "boot_override": "0x40003891 calls input predicate 0x7bccb3b7; a return value of 1 makes it store 2 to settings RAM 0x74001e30. Physical key mapping remains unresolved.",
            "selection_prepare": "0x400d6524 sets volatile selected_mode 0x7435b18a to 2 when settings_word != 1 or override 0x7435b189 == 2; otherwise it arms override from 0 to 1.",
            "eligibility": "0x400d6556 requires settings_word != 1 or override == 2, then selected_mode == 3 or (connection_state == 1 and selected_mode == 2). This predicate alone does not request a USB mode change.",
            "override_event": "0x400d6475 requires input word at +8 to contain bit 0x80, state helper 0x400d84a2 == 1, settings_word == 1 and override == 1, then sets RAM override to 2. Physical event mapping remains unresolved.",
            "request_chain": "0x400d50f6 passes selected_mode to 0x400e9a8f; it maps 0/1/2 to the first word of the D042 record queued by 0x401e678d. Worker branch 0x401f80a8 calls 0x401f8356; record values 0/1/2 choose storage/PTP/vendor initialization.",
            "descriptor_mode": {"address": "0x744dd1ed", "values": {"1": "storage", "2": "vendor service", "3": "PTP"}},
            "bulk_phase": {"address": "0x744dd1e6", "note": "Separate from descriptor mode: phases 1/2 choose mass-storage handling; phases 3/4 call binary diagnostic receive handler 0x401eee32."},
            "nearby_fixed_settings": "0x7400b938 selects normal PID variants; 0x7400b93c selects some transfer sizes. Neither is established as a debug-enable flag.",
        },
        "descriptor_positive_controls": {"source": str(observation),
                                         "source_sha256": hashlib.sha256(observed_raw).hexdigest(),
                                         "results": controls},
        "configuration_model_outputs": layouts,
        "limitations": {
            "semantic_models_independently_executed_on_firmware": False,
            "complete_physical_entry_sequence_established": False,
            "gh2_service_transport_tested": False,
            "gm5_service_interface_or_reader_equivalence_established": False,
            "camera_contacted_by_this_study": False,
            "settings_changed_or_firmware_executed": False,
            "descriptor_matches_prove_identical_firmware": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--gm5-observation", type=Path, default=Path("evidence/gm5-usb-pc-ptp.json"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = make_report(args.body, args.decoder, args.gm5_observation)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Verification failed: {error}\n")


if __name__ == "__main__":
    main()
