#!/usr/bin/env python3
"""Test the installed GM5 writer and post-decode job against private virtual NOR.

No camera transport is imported or used. Raw outputs stay in new private work
directories. ASIC shutdown/scheduler entry and RTOS synchronization assumptions
are explicit in every complete post-decode scenario.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import struct

from gm5_emulator import DEFAULT_BACKEND, base_scenario, decoder_scenario, put, word, run_scenario, sha
from gm5_emulator_merge import BULK_RANGES
from panasonic_upd import parse

BACKUP = Path("captures/gm5-flash-backup-9z320rtf/result/flash32m.bin")
BACKUP_SHA = "c51dca467a8bd24c0be75915acb54692f9213a7d7b9896c5e50a010d830a35ca"
CANDIDATE = Path("work/gm5-updater-prompt-0112/advertised-0112/GM5__V11.bin")
CANDIDATE_SHA = "45a7da844d497f9c52d90a1a7db73e2b54fb18a38d3a639b602320a7df269ce3"
MAIN_SHA = "5316a6ff14152126a88ce02125e85d713e710c8dd1159dee2ab890e4ff345966"
SECONDARY_SHA = "d3953f29553723e7375c537f2cf8e673ade4924e6c0de161243cf106575a74e7"
SECTOR, BUFFER, INPUT = 0x20000, 1024, 0x74000000
LOCK, UNLOCK, MUTEX = 0x7BE0826E, 0x7BE0629D, 0x12


def installed() -> tuple[list[dict], bytes, bytes, bytes]:
    receipt = json.loads(Path("evidence/gm5-flash-backup.json").read_text())
    components = receipt["analysis"]["components"]
    images = [{"path": c["path"], "address": c["linked_address"], "sha256": c["sha256"]} for c in components]
    main, secondary, flash = (Path(images[0]["path"]).read_bytes(), Path(images[1]["path"]).read_bytes(), BACKUP.read_bytes())
    if (sha(main), sha(secondary), sha(flash)) != (MAIN_SHA, SECONDARY_SHA, BACKUP_SHA):
        raise ValueError("Expected the retained, packet-verified installed GM5 images")
    at = 0x64B5B8 + (0x70A92A74-0x70A01E6C)
    if struct.unpack_from("<10I", main, at) != (0, 0x2000000, SECTOR, 1, 256, SECTOR, 2, 1, 1, 0x70A92A74):
        raise ValueError("Installed NOR descriptor differs")
    if struct.unpack_from("<H", secondary, 0x7BE3E4A8-0x7BC00000)[0] != MUTEX:
        raise ValueError("Installed writer synchronization identifier differs")
    return images, main, secondary, flash


def scenario(name: str, images: list[dict], main: bytes, source: Path = BACKUP, *, sync=False) -> dict:
    spec = base_scenario(name)
    spec["images"] = copy.deepcopy(images)
    spec["maps"] += [[INPUT, 0x2000000], [0x8070, 4], [0x9C01202C, 2],
                     [0x28A00000, 2048], [0x28A80000, 2048]]
    spec["memory"] = [put(0x70000000, main[0x643B7C:0x64B5B8]),
                      put(0x70A01E6C, main[0x64B5B8:0x6DD76C])]
    spec["nor"] = {"path": str(source), "sha256": sha(source.read_bytes())}
    spec["budget"] = 10000000
    spec["trace_every"] = 1000
    spec["assumptions"] = ["Installed GM5 instruction bytes and fixed 32 MiB/128 KiB/x16 command geometry.",
                           "NOR timing is deterministic status polling; protection, ECC and analog behavior are not modeled."]
    if sync:
        spec["memory"] += [put(LOCK, bytes.fromhex("00dff014")), put(UNLOCK, bytes.fromhex("00dfe010"))]
        spec["single_thread_sync"] = {"lock_pc": LOCK, "unlock_pc": UNLOCK, "id": MUTEX}
        spec["assumptions"] += ["Two explicit virtual RTOS return stubs use a checked single-thread mutex model.",
                                 "Cache-control registers are latches and cache tags start empty; real cache coherence is not tested."]
    return spec


def range_writer(name: str, images: list[dict], main: bytes, offset: int, payload: bytes, *, length=None) -> dict:
    spec = scenario(name, images, main, sync=True)
    stub, entry = 0x70008000, 0x7BD4EB0D
    spec["memory"] += [put(stub, b"\xdd"+struct.pack("<i", entry-stub)+bytes([0xF0, 64, 0xFF])),
                       put(INPUT, payload), word(0x700F0004, 0)]
    spec["registers"].update(pc=stub, a0=0x70A92A94, a1=INPUT, d0=offset,
                              d1=len(payload) if length is None else length,
                              d2=0x22332233, d3=0x33443344, a2=0x44554455, a3=0x55665566)
    spec["stops"] = {"returned": stub+7}
    return spec


def events(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (directory/"nor-events.jsonl").read_text().splitlines()]


def erased(raw: bytes, start: int, size: int) -> bytearray:
    result = bytearray(raw)
    first, last = start//SECTOR*SECTOR, (start+size+SECTOR-1)//SECTOR*SECTOR
    result[first:last] = b"\xff"*(last-first)
    return result


def control_tests(backend: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    images, main, secondary, flash = installed()
    controls = []

    def execute(spec: dict, expected: bytes | bytearray | None, stop: str, *, status=None) -> tuple[dict, Path]:
        directory = output/spec["name"]
        record = run_scenario(spec, backend, directory)
        result = record["result"]
        if result["stop"] != stop:
            raise ValueError(f"Unexpected native writer stop: {spec['name']}: {result}")
        if status is not None and int(result["registers"][0], 0) != status:
            raise ValueError(f"Unexpected native writer return: {spec['name']}: {result}")
        if expected is not None and (directory/"virtual-nor.bin").read_bytes() != expected:
            raise ValueError(f"Complete virtual NOR readback differs: {spec['name']}")
        if stop == "returned":
            for register, index in (("d2", 2), ("d3", 3), ("a2", 6), ("a3", 7), ("sp", 8)):
                if int(result["registers"][index], 0) != spec["registers"][register]:
                    raise ValueError(f"Native writer clobbered preserved {register}")
            service = result["services"]
            if service and (service["held"] or service["locks"] != service["unlocks"]):
                raise ValueError("Writer did not release its modeled mutex")
        controls.append({"name": spec["name"], "execution": record,
                         "complete_image_matches_expected": expected is not None})
        return record, directory

    spec = scenario("native_erase_busy", images, main)
    spec["registers"].update(pc=0x7BD1B587, d2=0x80020000, d3=100)
    spec["stops"] = {"commands_finished": 0x7BD1B5E7}
    _, erased_dir = execute(spec, erased(flash, SECTOR, SECTOR), "commands_finished", status=0)
    spec = copy.deepcopy(spec); spec["name"] = "native_erase_error"; spec["nor"]["fail_erase"] = 1
    execute(spec, flash, "commands_finished", status=3)
    payload = bytearray(bytes(range(256))*4)
    payload[:4] = bytes.fromhex("f0002500")
    for fail in (False, True):
        spec = scenario("native_buffer_error" if fail else "native_buffer_success", images, main,
                        erased_dir/"virtual-nor.bin")
        spec["registers"].update(pc=0x7BD1B639, d2=0, a2=0x80020000, a3=INPUT)
        spec["memory"] += [put(INPUT, payload), word(0x700F0004, BUFFER), word(0x700F0008, 100), word(0x700F000C, 0)]
        spec["stops"] = {"commands_finished": 0x7BD1B6CC}
        spec["dumps"] = [{"name": "program-status.data", "address": 0x700F000C, "size": 4}]
        spec["nor"]["fail_program"] = int(fail)
        expected = bytearray((erased_dir/"virtual-nor.bin").read_bytes())
        if not fail: expected[SECTOR:SECTOR+BUFFER] = payload
        _, directory = execute(spec, expected, "commands_finished")
        if struct.unpack("<I", (directory/"program-status.data").read_bytes())[0] != int(fail):
            raise ValueError("Native program status does not reflect the injected error")

    # A program operation masks 0->1 requests, even if DQ7 polling appears good.
    wanted = bytearray(flash[SECTOR:SECTOR+BUFFER])
    index = next(i for i, value in enumerate(wanted[:-2]) if not value & 1)
    wanted[index] |= 1
    spec = scenario("program_without_erase_masking", images, main)
    spec["registers"].update(pc=0x7BD1B639, d2=0, a2=0x80020000, a3=INPUT)
    spec["memory"] += [put(INPUT, wanted), word(0x700F0004, BUFFER), word(0x700F0008, 100), word(0x700F000C, 0)]
    spec["stops"] = {"commands_finished": 0x7BD1B6CC}
    spec["dumps"] = [{"name": "program-status.data", "address": 0x700F000C, "size": 4}]
    record, directory = execute(spec, flash, "commands_finished")
    if not record["result"]["nor"]["zero_to_one_words"] or (directory/"program-status.data").read_bytes() != bytes(4):
        raise ValueError("Expected masked bit with an apparently successful native polling result")
    controls[-1]["requested_data_readback_matches"] = False

    for name, code, stop in (("unmodeled_bus_command", "f070ff", "nor_unmodeled_command"),
                             ("unsupported_bus_width", "60ff", "nor_unsupported_bus_width")):
        spec = scenario(name, images, main)
        spec["memory"].append(put(0x70008000, bytes.fromhex(code)))
        spec["registers"].update(pc=0x70008000, a0=0x80000AAA, d0=0x55)
        execute(spec, flash, stop)

    for name, start, size in (("range_complete_sector", SECTOR, SECTOR),
                              ("range_cross_sector", 2*SECTOR-BUFFER, 2*BUFFER)):
        data = bytes((i*29+7)%256 for i in range(size))
        spec = range_writer(name, images, main, start, data)
        spec["dumps"] = [{"name": "cached.data", "address": 0x40000000+start, "size": size},
                         {"name": "bus.data", "address": 0x80000000+start, "size": size}]
        expected = erased(flash, start, size); expected[start:start+size] = data
        _, directory = execute(spec, expected, "returned", status=0)
        if (directory/"cached.data").read_bytes() != data or (directory/"bus.data").read_bytes() != data:
            raise ValueError("Cached/read-bus alias views differ")

    for name, start, data, code in (("range_misaligned", SECTOR+1, bytes(BUFFER), 0x80000001),
                                    ("range_out_of_bounds", len(flash)-BUFFER, bytes(2*BUFFER), 0x80000003)):
        execute(range_writer(name, images, main, start, data), flash, "returned", status=code)

    data = bytes((i*13+11)%256 for i in range(2*BUFFER))
    spec = range_writer("range_program_failure", images, main, SECTOR, data)
    spec["nor"]["fail_program"] = 2
    expected = erased(flash, SECTOR, len(data)); expected[SECTOR:SECTOR+BUFFER] = data[:BUFFER]
    execute(spec, expected, "returned", status=0x8000000C)
    spec = range_writer("range_power_cut", images, main, SECTOR, data)
    spec["nor"]["cut_after"] = 2
    execute(spec, expected, "nor_power_cut")
    spec = range_writer("wrong_mutex_identifier", images, main, SECTOR, data)
    spec["single_thread_sync"]["id"] = MUTEX+1
    execute(spec, flash, "single_thread_sync_error")

    # The native helper assumes 1 KiB units despite its range wrapper's x16
    # alignment check. An undersized request must never be recorded as success.
    data = bytes((i*13+11)%256 for i in range(4*BUFFER))
    spec = range_writer("unsupported_sub_buffer_length", images, main, SECTOR, data, length=16)
    spec["budget"] = 20000
    record, directory = execute(spec, None, "budget_exhausted")
    expected = erased(flash, SECTOR, 16)
    commits = [e for e in events(directory) if e["event"] == "program_commit"]
    for i, item in enumerate(commits):
        start = int(item["offset"], 0)
        expected[start:start+BUFFER] = data[i*BUFFER:(i+1)*BUFFER]
    if not commits or (directory/"virtual-nor.bin").read_bytes() != expected:
        raise ValueError("Unsupported short-length control did not expose the expected partial overwrite")
    controls[-1]["overrun_of_declared_length_detected"] = True
    report = {"schema": 1, "scope": "Installed native NOR writer/device controls", "passed": len(controls),
              "controls": controls, "driver_sha256": sha(Path(__file__).read_bytes()),
              "camera_contacted": False, "physical_flash_written": False}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def expected_payload(entry: dict, original: bytes, flash: bytes, *, patch=False) -> bytes:
    start = entry["file_offset"]
    wanted = bytearray(original[start:start+entry["size"]])
    current = flash[0x1FA0000:0x1FC0000]
    if entry["name"] in ("eep_ow_a", "eep_ow_b"):
        for start, size in BULK_RANGES: wanted[start:start+size] = current[start:start+size]
        wanted[0x4800:0x6800] = current[0x4800:0x6800]
        region = struct.unpack_from("<H", current, 0x330)[0]
        region = 256 if region == 285 else 265 if region == 21 else region
        if region in (1, 256, 279, 281): wanted[0x334:0x336] = b"\0\0"
        wanted[0x1E00:0x1FF8] = current[0x1E00:0x1FF8]
    elif entry["name"] == "eep_adjfix":
        wanted[:0x5000] = flash[0x1FE0000:0x1FE5000]
    elif entry["name"] == "program" and patch:
        if wanted[0x6B1BDC] != 1: raise ValueError("Expected stock policy ROM byte one")
        wanted[0x6B1BDC] = 0
    return bytes(wanted)


def installation_tests(backend: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    images, main, secondary, flash = installed()
    container = CANDIDATE.read_bytes()
    if sha(container) != CANDIDATE_SHA: raise ValueError("Validated candidate changed")
    entries = parse(container, allow_unsigned=True)
    if any(e["size"] % BUFFER or e["destination_offset_candidate"] % BUFFER for e in entries):
        raise ValueError("This native writer requires whole 1 KiB buffers")
    controls = []
    decoded_path = None
    context_path = None
    for allowance in (1, 0):
        name = "installed_decode_allowed" if allowance else "installed_decode_default_policy"
        spec = decoder_scenario(name, CANDIDATE, allowance, len(container))
        spec["images"][:2] = copy.deepcopy(images)
        stub, ctx = 0x70008000, 0x70020000
        code = b"\xdd"+struct.pack("<i", 0x7BD4ED0E-stub)+bytes([0xF0, 36])
        code += b"\xfc\xdc"+struct.pack("<I", ctx)+b"\x95\0"
        position = stub+len(code)
        code += b"\xdd"+struct.pack("<i", 0x7BD4EE4E-position)+bytes([0x30, 12, 0xFF])
        spec["memory"][0] = put(stub, code)
        spec["memory"].append(word(ctx+108, 0x7BE2A770))
        record = run_scenario(spec, backend, output/name)
        expected = 0 if allowance else 0x80000065
        if record["result"]["stop"] != "returned" or int(record["result"]["registers"][0], 0) != expected:
            raise ValueError("Installed native decoding control failed")
        after = (output/name/"decoded-input.data").read_bytes()
        if allowance:
            for entry in entries:
                at, size = entry["file_offset"], entry["size"]
                if sha(after[at:at+size]) != entry["field32_hex"]:
                    raise ValueError("Installed native plaintext digest differs")
            decoded_path, context_path = output/name/"decoded-input.data", output/name/"context.bin"
        elif after != container:
            raise ValueError("Rejected package was changed")
        controls.append({"name": name, "execution": record, "all_component_hashes_match": bool(allowance)})
        print(f"Passed {name}", flush=True)
    assert decoded_path and context_path
    original = decoded_path.read_bytes()
    current_ctx = context_path.read_bytes()
    successful = []
    for name, patch, fail, cut in (("native_install_stock", False, 0, 0),
                                   ("native_install_virtual_policy_patch", True, 0, 0),
                                   ("native_install_injected_program_error", False, 1, 0),
                                   ("native_install_power_cut", False, 0, 2)):
        spec = scenario(name, images, main, sync=True)
        spec["images"].append({"path": str(decoded_path), "address": INPUT, "sha256": sha(original)})
        def jump(at: int, target: int) -> dict:
            return put(at, b"\xdc"+struct.pack("<i", target-at))
        spec["memory"] += [put(0x7BFB0000, flash[0x1FA0000:0x1FC0000]),
                           put(0x702C817C, flash[0x1FA4800:0x1FA6800]),
                           put(0x7BFD4800, flash[0x1FE0000:0x1FEC000]),
                           put(0x70020000, current_ctx), word(0x70030004, 2),
                           word(0x700F0010, 0), word(0x700F001C, 0x70020000), word(0x70A68490, 0),
                           jump(0x7BD4FE14, 0x7BD4FE23), jump(0x7BD4FF0D, 0x7BD4FF17)]
        if patch: spec["memory"].append(put(INPUT+entries[0]["file_offset"]+0x6B1BDC, b"\0"))
        spec["registers"].update(pc=0x7BD4FD8A, a2=INPUT, a3=0x70030000)
        spec["stops"] = {"programming_finished": 0x7BD50074}
        spec["watchpoints"] = {"component_writer_return": 0x7BD50035}
        spec["nor"].update(fail_program=fail, cut_after=cut)
        spec["budget"], spec["trace_every"] = 1000000000, 10000
        spec["dumps"] = [{"name": "merged-input.data", "address": INPUT, "size": len(original)}]
        spec["assumptions"] += ["Post-decode job starts from a successful installed-build native decoding context.",
                                 "Current settings fixture is seeded from NOR slot A and adjustment area; not a complete live-RAM snapshot.",
                                 "ASIC shutdown/scheduler calls at0x7bd4fe14 and0x7bd4ff0d are bypassed explicitly; UI callbacks are disabled.",
                                 "Stops after programming iteration, before final cleanup/reset; no full camera boot is claimed."]
        directory = output/name
        record = run_scenario(spec, backend, directory)
        wanted_stop = "nor_power_cut" if cut else "programming_finished"
        if record["result"]["stop"] != wanted_stop:
            raise ValueError(f"Native post-decode job stopped unexpectedly: {record['result']}")
        merged = (directory/"merged-input.data").read_bytes()
        expected_image = bytearray(flash)
        requested_image = bytearray(flash)
        components = []
        for i, entry in enumerate(entries):
            at, size, destination = entry["file_offset"], entry["size"], entry["destination_offset_candidate"]
            payload = expected_payload(entry, original, flash, patch=patch)
            if merged[at:at+size] != payload: raise ValueError("Native settings merge differs from the independent expected payload")
            first, last = destination//SECTOR*SECTOR, (destination+size+SECTOR-1)//SECTOR*SECTOR
            requested_image[first:last] = b"\xff"*(last-first)
            requested_image[destination:destination+size] = payload
            if cut:
                if not i:
                    expected_image[:SECTOR] = b"\xff"*SECTOR
                    expected_image[:BUFFER] = payload[:BUFFER]
            elif fail and not i:
                expected_image[:SECTOR] = b"\xff"*SECTOR
            else:
                expected_image[first:last] = b"\xff"*(last-first)
                expected_image[destination:destination+size] = payload
            components.append({"name": entry["name"], "destination": hex(destination), "bytes": size,
                               "original_plaintext_sha256": entry["field32_hex"], "post_merge_sha256": sha(payload)})
        actual = (directory/"virtual-nor.bin").read_bytes()
        if actual != expected_image: raise ValueError("Complete virtual NOR differs from independent operation oracle")
        watches = [json.loads(line) for line in (directory/"trace.jsonl").read_text().splitlines() if '"event":"watch"' in line]
        statuses = [int(w["d0"], 0) for w in watches]
        if not cut and statuses != ([0x8000000C]+[0]*7 if fail else [0]*8):
            raise ValueError(f"Native component writer return sequence differs: {statuses}")
        stats = record["result"]["nor"]
        if not fail and not cut:
            if (stats["erases"], stats["programs"], stats["zero_to_one_words"]) != (244, 31152, 0):
                raise ValueError("Native erase/program plan differs")
            successful.append((name, directory/"virtual-nor.bin", patch))
        controls.append({"name": name, "execution": record, "components": components,
                         "complete_image_matches_operation_oracle": True,
                         "matches_requested_complete_installation": actual == requested_image,
                         "component_writer_returns": [hex(value) for value in statuses],
                         "writer_error_ignored_by_outer_loop": bool(fail and record["result"]["stop"] == "programming_finished")})
        print(f"Passed {name}", flush=True)
    for name, source, patched in successful:
        spec = scenario(name+"_reloaded_initializer", images, main, source)
        spec["registers"]["pc"] = 0x40003000
        spec["stops"] = {"copy_finished": 0x4000301E}
        spec["dumps"] = [{"name": "policy.data", "address": 0x70A68490, "size": 1}]
        record = run_scenario(spec, backend, output/spec["name"])
        value = (output/spec["name"]/"policy.data").read_bytes()[0]
        if record["result"]["stop"] != "copy_finished" or value != (0 if patched else 1):
            raise ValueError("Reloaded virtual image initializes the wrong policy")
        controls.append({"name": spec["name"], "execution": record, "initialized_policy": value})
    if sha(BACKUP.read_bytes()) != BACKUP_SHA: raise ValueError("Original backup changed")
    report = {"schema": 1, "scope": "Installed GM5 decode/post-decode job/virtual NOR/reloaded-initializer tests",
              "passed": len(controls), "controls": controls, "driver_sha256": sha(Path(__file__).read_bytes()),
              "original_backup_sha256": BACKUP_SHA, "original_backup_unchanged": True,
              "camera_contacted": False, "physical_flash_written": False,
              "limits": ["Explicit single-thread RTOS, empty-cache and scheduler/ASIC abstractions; no full machine or physical timing model.",
                         "Settings RAM is a documented fixture from slot A, not a complete measured live RAM state.",
                         "Virtual plaintext policy patch has not been repackaged as an encoded camera update.",
                         "Reloaded initializer tests do not establish full boot or absence of a separate boot-time authentication check.",
                         "Does not establish physical flash acceptance or a recovery writer."]}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("controls", "install-tests"))
    parser.add_argument("--backend", type=Path, default=DEFAULT_BACKEND)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    test = control_tests if args.action == "controls" else installation_tests
    result = test(args.backend, args.out)
    print(f"Passed {result['passed']} virtual NOR controls; evidence {args.out}")


if __name__ == "__main__":
    main()
