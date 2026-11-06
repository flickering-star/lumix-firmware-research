#!/usr/bin/env python3
"""Exercise the native updater's settings merge against synthetic buffers only.

No installation job, hardware write or camera transport is involved. This
function-level probe checks every output byte and preservation of its inputs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from gm5_emulator import DEFAULT_BACKEND, base_scenario, put, run_scenario, sha

BULK_RANGES = ((0, 768), (768, 192), (2816, 256), (7168, 24),
               (16384, 384), (9728, 504), (26624, 37888),
               (3584, 1536), (5632, 512), (8192, 512), (0x840, 10), (0x324, 2))


def merge_tests(backend: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    controls = []
    for flags, argument, region in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (2, 0, 0),
                                    (4, 0, 0), (4, 0, 1), (1, 1, 1)):
        name = f"flags_{flags}_argument_{argument}_region_{region}"
        current = bytearray(b"\x5a"*0x20000)
        struct.pack_into("<H", current, 0x330, region)
        extra = b"\x69"*8192
        candidate = b"\xa5"*0x20000
        expected = bytearray(candidate)
        if flags in (2, 4):
            for start, size in BULK_RANGES:
                expected[start:start+size] = current[start:start+size]
            expected[0x4800:0x6800] = extra
        elif flags == 1 and argument:
            for start in (0x330, 0x32C):
                expected[start:start+2] = current[start:start+2]
        if (flags in (2, 4) or flags == 1 and argument) and region:
            expected[0x334:0x336] = b"\0\0"
        expected[0x1E00:0x1FF8] = current[0x1E00:0x1FF8]
        stub, entry = 0x70008000, 0x7BD4F7F7
        spec = base_scenario(name)
        spec["memory"] = [put(stub, b"\xdd"+struct.pack("<i", entry-stub)+bytes([0xB0, 16, 0xFF])),
                          put(0x70040000, candidate), put(0x7BFB0000, current), put(0x702C817C, extra)]
        spec["registers"].update(pc=stub, a0=0x70040000, d0=argument, d1=flags)
        spec["stops"] = {"returned": stub+7}
        spec["budget"] = 1000000
        spec["trace_every"] = 1000
        spec["dumps"] = [{"name": "merged.data", "address": 0x70040000, "size": len(candidate)},
                         {"name": "current.data", "address": 0x7BFB0000, "size": len(current)},
                         {"name": "extra.data", "address": 0x702C817C, "size": len(extra)}]
        spec["assumptions"].append("Synthetic settings/payload buffers; no real calibration values are used.")
        record = run_scenario(spec, backend, output/name)
        actual = (output/name/"merged.data").read_bytes()
        if record["result"]["stop"] != "returned" or actual != expected:
            raise ValueError(f"Native settings merge differs: {name}: {record['result']}")
        if ((output/name/"current.data").read_bytes() != current
                or (output/name/"extra.data").read_bytes() != extra):
            raise ValueError(f"Native merge modified a source buffer: {name}")
        controls.append({"name": name, "container_flags_low_nibble": flags, "argument": argument,
                         "synthetic_region_word": region, "whole_candidate_matches_expected": True,
                         "source_buffers_unchanged": True, "merged_sha256": sha(actual),
                         "bytes_changed_in_candidate": sum(a != b for a, b in zip(candidate, actual)),
                         "native_instructions": record["result"]["steps"],
                         "report": str(output/name/"report.json")})
    report = {"schema": 1, "scope": "Native GM5 settings merge at 0x7bd4f7f7, with synthetic buffers",
              "passed": len(controls), "controls": controls, "source_sha256": sha(Path(__file__).read_bytes()),
              "camera_contacted": False, "programming_job_called": False,
              "limits": ["Tests this native merge function, not complete calibration preservation during installation.",
                         "Does not prove installed Japanese function addresses or all build variants.",
                         "Does not emulate NOR erase/programming or independent storage devices."]}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, default=DEFAULT_BACKEND)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = merge_tests(args.backend, args.out)
    print(f"Passed {report['passed']} native settings-merge controls; evidence {args.out}")


if __name__ == "__main__":
    main()
