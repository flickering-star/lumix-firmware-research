#!/usr/bin/env python3
"""Pin the GM5 preflight and installation paths against retained native bytes.

Offline evidence only. Does not execute firmware or contact a camera.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from gh2_debug_verify import checked_disassembly
from gm1_capture_verify import verify_capture

INPUTS = {
    "main": (0x40000000, 8388608, "e6ce3a0764fd56e0f255d4412d30b1f9f73b5282b333c0fe80f16dc11833078c"),
    "secondary": (0x7BC00000, 3538944, "90dd3e4a19c6008571f1623e4d849f245b279473f43e3b13f8b763e6c94a53a5"),
    "physical_updater": (0x7BD4E000, 16384, "cbda9861262b204427d73b61bfe22d08f385c6a52cbc4f15b355679afc53614e"),
    "physical_main_entry": (0x4023B800, 3072, "9863d695d199c752a49df9d1b50403a2157ab51b8f7440170a4af2a7be7254f4"),
}
REGIONS = (
    ("preflight_dispatch", "main", 0x4023BA1C, 0x4023BB23),
    ("installation_dispatch", "main", 0x4023BB23, 0x4023BB9C),
    ("preflight_model_version", "main", 0x4023C0AC, 0x4023C141),
    ("installation_bridge", "main", 0x4023C141, 0x4023C1B3),
    ("outer_header_reader", "secondary", 0x7BD4ED0A, 0x7BD4EE4A),
    ("full_decoder_dispatch", "secondary", 0x7BD4EE4A, 0x7BD4EE8F),
    ("unsigned_or_signature", "secondary", 0x7BD4F147, 0x7BD4F1C5),
    ("job_header_policy", "secondary", 0x7BD4FA18, 0x7BD4FAD3),
    ("preflight_header_probe", "secondary", 0x7BD4FAD3, 0x7BD4FB8F),
    ("job_unsigned_flag_key_profile", "secondary", 0x7BD4FB8F, 0x7BD4FCA5),
    ("job_full_decode_before_programming", "secondary", 0x7BD4FCA5, 0x7BD4FCE7),
)
CALLS = (
    ("main", 0x4023BA58, 0x4023C0AC),
    ("main", 0x4023BB50, 0x4023C141),
    ("main", 0x4023C0DA, 0x7BD4FAD3),
    ("main", 0x4023C19A, 0x7BD4FB8F),
    ("secondary", 0x7BD4FB30, 0x7BD4ED0A),
    ("secondary", 0x7BD4FC62, 0x7BD4ED0A),
    ("secondary", 0x7BD4FC7B, 0x7BD4FA18),
    ("secondary", 0x7BD4FC93, 0x7BD4ECD9),
    ("secondary", 0x7BD4FCA0, 0x7BD4EE8F),
    ("secondary", 0x7BD4FCCD, 0x7BD4EE4A),
    ("secondary", 0x7BD4EE80, 0x7BD4EE9B),
    ("secondary", 0x7BD4F192, 0x40274266),
    ("secondary", 0x7BD4F1B7, 0x40273419),
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_report(main: Path, secondary: Path, capture: Path, decoder: Path,
                main_capture: Path | None = None) -> dict:
    packet_check = verify_capture(capture)
    if not packet_check["complete"] or packet_check["mode"] != "updater-window":
        raise ValueError("Expected the complete physical GM5 updater-window capture")
    paths = {"main": main, "secondary": secondary,
             "physical_updater": Path(packet_check["program_file"])}
    main_packet_check = verify_capture(main_capture) if main_capture is not None else None
    if main_packet_check is not None:
        if not main_packet_check["complete"] or main_packet_check["mode"] != "update-entry":
            raise ValueError("Expected a complete physical GM5 update-entry capture")
        paths["physical_main_entry"] = Path(main_packet_check["program_file"])
    data = {name: path.read_bytes() for name, path in paths.items()}
    sources = {}
    for name in paths:
        base, size, digest = INPUTS[name]
        if len(data[name]) != size or sha(data[name]) != digest:
            raise ValueError(f"Pinned {name} differs")
        sources[name] = {"path": str(paths[name]), "bytes": size, "sha256": digest,
                         "file_zero_base": hex(base)}
    regions = []
    for name, component, start, end in REGIONS:
        variants = [(component, start, end)]
        if component == "secondary":
            variants.append(("physical_updater", start+4, end+4))
        elif main_packet_check is not None:
            variants.append(("physical_main_entry", start, end))
        for source, first, last in variants:
            base = INPUTS[source][0]
            disassembly, count = checked_disassembly(paths[source], data[source], decoder,
                                                     base, first, last)
            regions.append({"name": name, "source": source, "start": hex(first),
                            "end_exclusive": hex(last), "native_sha256": sha(data[source][first-base:last-base]),
                            "instruction_count": count, "raw_annotations_match_source": True,
                            "disassembly": disassembly})
    calls = []
    for component, address, target in CALLS:
        variants = [(component, address, target)]
        if component == "secondary":
            variants.append(("physical_updater", address+4,
                             target+4 if 0x7BD4E000 <= target < 0x7BD52000 else target))
        elif main_packet_check is not None:
            variants.append(("physical_main_entry", address,
                             target+4 if 0x7BD4E000 <= target < 0x7BD52000 else target))
        for source, at, expected in variants:
            offset = at-INPUTS[source][0]
            opcode = data[source][offset]
            if opcode not in (0xCD, 0xDD):
                raise ValueError(f"Missing relative call at {at:#x}")
            actual = (at+struct.unpack_from("<h" if opcode == 0xCD else "<i",
                                           data[source], offset+1)[0]) & 0xFFFFFFFF
            if actual != expected:
                raise ValueError(f"Call target differs at {at:#x}")
            calls.append({"source": source, "address": hex(at), "target": hex(actual)})
    physical = data["physical_updater"]
    base = INPUTS["physical_updater"][0]
    if physical[0x7BD4FB97-base:0x7BD4FB9D-base] != bytes.fromhex("fca89084a670"):
        raise ValueError("Physical unsigned flag load differs")
    return {
        "schema": 1, "scope": "GM5 native preflight/installation split and installed unsigned branch; offline only",
        "sources": sources, "physical_packet_check": packet_check,
        "physical_main_packet_check": main_packet_check,
        "verifier": {"path": "tools/gm5_updater_verify.py", "sha256": sha(Path(__file__).read_bytes())},
        "decoder": {"path": str(decoder), "sha256": sha(decoder.read_bytes()), "machine_argument": 332},
        "regions": regions, "relative_calls": calls,
        "manual_review": {
            "preflight": "Official main 0x4023c0ac calls the outer-header-only probe at 0x7bd4fad3, then checks version/build fields. The probe calls 0x7bd4ed0a, which reads and checks the 512-byte UPD header; it does not call the full decoder or ECDSA verifier.",
            "separate_installation": "Main installation handler 0x4023bb23 calls bridge 0x4023c141, which calls the full update job 0x7bd4fb8f. That job sets the key/profile/unsigned allowance and invokes full decoding via 0x7bd4ee4a before later programming operations.",
            "unsigned": "The installed job at 0x7bd4fb93 loads RAM 0x70a68490 at 0x7bd4fb97; zero enables context+112. Installed inner-marker branch 0x7bd4f14b admits marker byte zero only with that allowance, bypassing ECDSA on that branch.",
            "prompt_interpretation": "Reaching a confirmation prompt alone does not demonstrate ECDSA bypass or successful full payload validation. The preflight and installation request handlers are separate; complete UI-state ordering is not yet traced.",
        },
        "limits": {"camera_contacted_by_verifier": False, "firmware_executed": False,
                   "flash_written": False, "physical_main_ui_path_captured": main_packet_check is not None,
                   "complete_ui_state_machine_traced": False,
                   "unsigned_update_accepted_on_camera": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main", type=Path)
    parser.add_argument("secondary", type=Path)
    parser.add_argument("--physical-updater-capture", required=True, type=Path)
    parser.add_argument("--physical-main-capture", type=Path)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = make_report(args.main, args.secondary, args.physical_updater_capture, args.decoder,
                         args.physical_main_capture)
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Verified {len(result['regions'])} native regions and {len(result['relative_calls'])} call edges; preflight alone does not prove unsigned acceptance.")


if __name__ == "__main__":
    main()
