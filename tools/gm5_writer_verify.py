#!/usr/bin/env python3
"""Pin installed GM5 programming regions, call edges and modeled boundaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from gh2_debug_verify import checked_disassembly
from gm5_emulator import sha
from gm5_virtual_install import installed

REGIONS = (
    ("post_decode_merge", 0x7BD4FD8A, 0x7BD4FE14),
    ("component_selection", 0x7BD4FE23, 0x7BD4FF0D),
    ("component_programming_loop", 0x7BD4FF17, 0x7BD50074),
    ("range_writer", 0x7BD4EB0D, 0x7BD4EC48),
    ("erase_wrapper", 0x7BD1B567, 0x7BD1B60B),
    ("buffer_program_wrapper", 0x7BD1B610, 0x7BD1B6F0),
    ("cache_control", 0x7BD1B383, 0x7BD1B405),
    ("interrupt_save_restore", 0x7BD4EA9E, 0x7BD4EAB7),
    ("hardware_handshake", 0x7BD4DD87, 0x7BD4DDBD),
)
CALLS = ((0x7BD50030, 0x7BD4EB0D), (0x7BD4EBCB, 0x7BD1B567),
         (0x7BD4EBEC, 0x7BD1B610), (0x7BD1B570, 0x7BE0826E),
         (0x7BD1B600, 0x7BE0629D), (0x7BD1B622, 0x7BE0826E),
         (0x7BD1B6E4, 0x7BE0629D))


def report(decoder: Path) -> dict:
    images, main, secondary, flash = installed()
    path = Path(images[1]["path"])
    base = 0x7BC00000
    regions = []
    for name, start, end in REGIONS:
        text, count = checked_disassembly(path, secondary, decoder, base, start, end)
        regions.append({"name": name, "start": hex(start), "end_exclusive": hex(end),
                        "sha256": sha(secondary[start-base:end-base]), "instructions": count,
                        "raw_annotations_match_source": True, "disassembly": text})
    calls = []
    for at, expected in CALLS:
        offset = at-base
        opcode = secondary[offset]
        if opcode not in (0xCD, 0xDD): raise ValueError("Expected relative call")
        target = (at+struct.unpack_from("<h" if opcode == 0xCD else "<i", secondary, offset+1)[0]) & 0xFFFFFFFF
        if target != expected: raise ValueError("Installed writer call edge changed")
        calls.append({"at": hex(at), "target": hex(target)})
    if secondary[0x7BD50035-base:0x7BD50039-base] != bytes.fromhex("fab43801"):
        raise ValueError("Expected D0 overwrite immediately after writer return")
    at = 0x64B5B8+(0x70A92A74-0x70A01E6C)
    return {"schema": 1, "scope": "Installed GM5 native NOR writer and explicit emulator boundaries",
            "images": images, "regions": regions, "calls": calls,
            "geometry": {"descriptor_ram": "0x70a92a74", "original_words": list(struct.unpack_from("<10I", main, at)),
                         "device_bytes": 0x2000000, "erase_sector_bytes": 0x20000,
                         "native_buffer_halfwords": 512, "native_buffer_bytes": 1024,
                         "range_alignment_check_bytes": 2},
            "software_abstractions": [
                {"at": "0x7bd4fe14", "resume_at": "0x7bd4fe23", "kind": "explicit virtual branch",
                 "detail": "Bypasses board-control calls 0x40254702 and 0x7be00713. Their register I/O roles are not fully modeled."},
                {"at": "0x7bd4ff0d", "resume_at": "0x7bd4ff17", "kind": "explicit virtual branch",
                 "detail": "Bypasses a request/handshake polling 0x93f00030 and interrupt-mask setup; assumes a quiescent single-thread machine."},
                {"at": "0x7be0826e", "kind": "virtual return stub with checked mutex model", "return_bytes": "00dff014"},
                {"at": "0x7be0629d", "kind": "virtual return stub with checked mutex model", "return_bytes": "00dfe010"}],
            "findings": ["The native buffer loop always loads 512 halfwords and subtracts1024 from its remaining length; container lengths must satisfy that implicit requirement.",
                         "At0x7bd50035 the caller overwrites the range writer's D0 return immediately. The injected-error native control confirms the outer loop continues.",
                         "The80KiB after the48KiB adjustment payload in the last128KiB sector are allFF in this backup."],
            "last_sector_unused_tail_sha256": sha(flash[0x1FEC000:]),
            "verifier_sha256": sha(Path(__file__).read_bytes()),
            "decoder_sha256": sha(decoder.read_bytes()), "camera_contacted": False,
            "limits": ["The NOR aliases and command model are software-derived, not a physical write-bus measurement.",
                       "No exact memory-part identification, hardware protection/ECC model or full boot validation."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decoder", type=Path, default=Path("work/toolchain/mn10300/mn103-dis"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = report(args.decoder)
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Pinned {len(result['regions'])} installed writer regions and {len(result['calls'])} call edges.")


if __name__ == "__main__":
    main()
