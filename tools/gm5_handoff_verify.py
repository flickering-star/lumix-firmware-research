#!/usr/bin/env python3
"""Record installed GM5 update dispatch, validation boundary and cleanup calls.

This is offline native-code evidence, not a complete hardware/boot proof or an
authorization to install a package on the camera.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from gh2_debug_verify import checked_disassembly
from gm5_emulator import sha
from gm5_virtual_install import installed

REGIONS = (
    ("confirmation_dispatch", 0, 0x4023BB23, 0x4023BB9C),
    ("installation_bridge", 0, 0x4023C141, 0x4023C1B3),
    ("job_samples_policy", 1, 0x7BD4FB93, 0x7BD4FBA2),
    ("full_decode_and_error_branch", 1, 0x7BD4FCA9, 0x7BD4FCEB),
    ("post_program_and_common_cleanup", 1, 0x7BD50074, 0x7BD500E9),
    ("cleanup_context_release", 1, 0x7BD4EC77, 0x7BD4EC7B),
    ("board_control_forwarder", 0, 0x40254702, 0x40254719),
    ("hardware_handshake_enter", 1, 0x7BD4DD87, 0x7BD4DDBD),
    ("hardware_handshake_exit_prefix", 1, 0x7BD4DDBD, 0x7BD4DE07),
)
CALLS = ((0, 0x4023BB50, 0x4023C141), (0, 0x4023C19A, 0x7BD4FB93),
         (1, 0x7BD4FCD1, 0x7BD4EE4E), (1, 0x7BD5009E, 0x7BD4EC77),
         (1, 0x7BD500AB, 0x40275566), (1, 0x7BD500C5, 0x402784BB),
         (0, 0x4025470F, 0x7BE005EB))


def report(decoder: Path) -> dict:
    images, main, secondary, _ = installed()
    data, bases = (main, secondary), (0x40000000, 0x7BC00000)
    regions = []
    for name, component, start, end in REGIONS:
        text, count = checked_disassembly(Path(images[component]["path"]), data[component], decoder,
                                         bases[component], start, end)
        raw = data[component][start-bases[component]:end-bases[component]]
        regions.append({"name": name, "start": hex(start), "end_exclusive": hex(end),
                        "sha256": sha(raw), "instructions": count,
                        "raw_annotations_match_source": True, "disassembly": text})
    calls = []
    for component, at, expected in CALLS:
        offset = at-bases[component]
        opcode = data[component][offset]
        if opcode not in (0xCD, 0xDD): raise ValueError("Expected relative call")
        actual = (at+struct.unpack_from("<h" if opcode == 0xCD else "<i", data[component], offset+1)[0]) & 0xFFFFFFFF
        if actual != expected: raise ValueError("Installed handoff call differs")
        calls.append({"at": hex(at), "target": hex(actual)})
    if secondary[0x1500E0:0x1500E2] != bytes.fromhex("5818"):
        raise ValueError("Expected return of the job's saved status at SP+24")
    return {"schema": 1, "scope": "Installed GM5 confirmation bridge, validation boundary and cleanup; offline only",
            "images": images, "regions": regions, "calls": calls,
            "supported_findings": [
                "The reviewed confirmation dispatch calls the installation bridge, which calls the updater directly in the current CPU context.",
                "The job samples the RAM policy before the full decoder. Decoder failure branches to common cleanup before the post-decode programming stage.",
                "The job returns the saved status from SP+24. The bridge maps a negative job return to failure; the dispatcher emits its error notification.",
                "Board-control/handshake calls used by the virtual installation occur after full decoding; their physical effects are not fully established."],
            "limits": ["This is local control-flow evidence, not complete UI, asynchronous callback or hardware execution.",
                       "No separate boot-time authentication mechanism is proved absent, including code outside the NOR dump.",
                       "No camera access, RAM writes, SD copying or physical update was performed."],
            "next_control": {"purpose": "Prepare a byte-identical installed-firmware reflash control before a permanent patch",
                             "package_prepared": False, "physical_update_authorized": False,
                             "prerequisites": ["Validate a container encoding the installed bytes with the recovered cipher, all hashes and native checks.",
                                               "Check real settings/calibration handling and the physical entry conditions.",
                                               "Specify the exact payload scope and post-update readback before a camera attempt."]},
            "verifier_sha256": sha(Path(__file__).read_bytes()), "decoder_sha256": sha(decoder.read_bytes()),
            "camera_contacted": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    value = report(args.decoder)
    with args.out.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    print(f"Verified {len(value['regions'])} handoff/cleanup regions and {len(value['calls'])} calls.")


if __name__ == "__main__":
    main()
