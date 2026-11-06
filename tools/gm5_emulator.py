#!/usr/bin/env python3
"""Execute pinned GM5 native routines in the GNU AM33-2 CPU simulator.

This is an offline function harness, not a full camera hardware model. Unknown
memory/device accesses and host syscalls stop execution. No USB code is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import time
import zlib

MAIN = ("work/gm5-v11-decoded-verified/00_program.decoded.bin", 0x40000000,
        "e6ce3a0764fd56e0f255d4412d30b1f9f73b5282b333c0fe80f16dc11833078c")
SECONDARY = ("work/gm5-v11-decoded-verified/02_program2.decoded.bin", 0x7BC00000,
             "90dd3e4a19c6008571f1623e4d849f245b279473f43e3b13f8b763e6c94a53a5")
REGISTERS = {**{f"d{i}": i for i in range(4)}, **{f"a{i}": 4+i for i in range(4)},
             "sp": 8, "pc": 9, "mdr": 10, "psw": 11, "lir": 12, "lar": 13}
DEFAULT_BACKEND = Path("work/toolchain/gdb-mn10300-build/gm5-mn103-sim")


def number(value) -> int:
    return int(value, 0) if isinstance(value, str) else int(value)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def put(address: int, raw: bytes) -> dict:
    return {"address": hex(address), "hex": raw.hex()}


def word(address: int, value: int) -> dict:
    return put(address, struct.pack("<I", value & 0xFFFFFFFF))


def base_scenario(name: str) -> dict:
    return {"schema": 1, "name": name,
            "maps": [[0x40000000, 0x800000], [0x7BC00000, 0x360000],
                     [0x70000000, 0x1000000], [0x7BFB0000, 0x40000]],
            "images": [{"path": path, "address": address, "sha256": digest}
                       for path, address, digest in (MAIN, SECONDARY)],
            "registers": {"sp": 0x700F0000}, "memory": [], "stops": {}, "budget": 10000,
            "execution_mode": "fast",
            "assumptions": ["Only CPU and explicitly mapped memory are modeled.",
                            "EEPROM string buffers used by the identity getter begin as zero."]}


def run_scenario(spec: dict, backend: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    backend = backend.resolve()
    if not backend.is_file():
        raise ValueError("Build tools/mn103_simulator/build.py first")
    backend_digest = sha(backend.read_bytes())
    driver_digest = sha(Path(__file__).read_bytes())
    commands = []
    aliases = spec.get("ram_aliases", [])
    if not isinstance(aliases, list) or len(aliases) > 16:
        raise ValueError("At most16bounded RAM aliases are supported")
    alias_regions = {}
    for item in aliases:
        at, size, shadow = (number(item[key]) for key in ("address", "size", "alias"))
        if (not 0x70000000 <= at < at+size <= 0x71000000 or shadow != at+0x40000000
                or any(at < other+length and other < at+size for other, length in alias_regions)):
            raise ValueError("RAM aliases require nonoverlapping bounded0x70 RAM intervals and matching0xb0 views")
        alias_regions[at, size] = shadow
    used_aliases = set()
    for address, size in spec["maps"]:
        pair = number(address), number(size)
        if pair in alias_regions:
            if pair in used_aliases:
                raise ValueError("An aliased RAM map must occur exactly once")
            commands.append(f"RAM_ALIAS {pair[0]:#x} {pair[1]:#x} {alias_regions[pair]:#x}")
            used_aliases.add(pair)
        else:
            commands.append(f"MAP {pair[0]:#x} {pair[1]:#x}")
    if used_aliases != set(alias_regions):
        raise ValueError("Each RAM alias must exactly match an explicit RAM map")
    images = []
    for item in spec.get("images", []):
        path = Path(item["path"]).resolve()
        if "\n" in str(path) or "\r" in str(path):
            raise ValueError("Newline in image path")
        raw = path.read_bytes()
        if sha(raw) != item["sha256"]:
            raise ValueError(f"Image SHA-256 differs: {path}")
        images.append({"path": str(path), "address": hex(number(item["address"])),
                       "bytes": len(raw), "sha256": sha(raw)})
        commands.append(f"LOAD {number(item['address']):#x} {path}")
    nor_source = None
    if "nor" in spec:
        device = spec["nor"]
        path = Path(device["path"]).resolve()
        if "\n" in str(path) or "\r" in str(path):
            raise ValueError("Newline in NOR input path")
        raw = path.read_bytes()
        if len(raw) != 32*1024*1024 or sha(raw) != device["sha256"]:
            raise ValueError("Virtual NOR input must match its pinned 32 MiB image")
        nor_source = {"path": str(path), "bytes": len(raw), "sha256": sha(raw)}
        values = [number(device.get(name, default)) for name, default in
                  (("busy_reads", 2), ("fail_erase", 0), ("fail_program", 0), ("cut_after", 0))]
        commands += ["NOR "+" ".join(str(v) for v in values)+f" {path}",
                     f"NOR_LOG {(output/'nor-events.jsonl').resolve()}"]
        if "single_thread_sync" in spec:
            sync = spec["single_thread_sync"]
            commands.append(f"SYNC {number(sync['lock_pc']):#x} {number(sync['unlock_pc']):#x} {number(sync['id'])}")
    for item in spec.get("memory", []):
        raw = bytes.fromhex(item["hex"])
        commands.append(f"BYTES {number(item['address']):#x} {raw.hex()}")
    if "command_controller" in spec:
        controller = spec["command_controller"]
        busy, stuck = number(controller.get("busy_reads", 2)), number(controller.get("stuck_mask", 0))
        if not 0 <= busy <= 1000000 or not 0 <= stuck <= 3:
            raise ValueError("Command-controller fixture requires bounded latency and a two-bit stuck mask")
        commands.append(f"CONTROL {busy} {stuck} {(output/'control-events.jsonl').resolve()}")
    for name, value in spec["registers"].items():
        commands.append(f"REG {REGISTERS[name]} {number(value):#x}")
    for label, address in spec["stops"].items():
        commands.append(f"STOP {number(address):#x} {label}")
    conditional_stops = spec.get("stops_if_registers_differ", [])
    if not isinstance(conditional_stops, list) or len(conditional_stops)+len(spec["stops"]) > 64:
        raise ValueError("At most64unconditional/conditional stops are supported")
    conditional_labels = set(spec["stops"])
    for item in conditional_stops:
        label, left, right = item["label"], item["left"], item["right"]
        if (not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,79}", label)
                or label in conditional_labels or left not in REGISTERS or right not in REGISTERS):
            raise ValueError("Conditional stops require distinct valid labels and supported registers")
        conditional_labels.add(label)
        commands.append(f"STOPDIFF {number(item['address']):#x} {REGISTERS[left]} {REGISTERS[right]} {label}")
    for label, address in spec.get("watchpoints", {}).items():
        commands.append(f"WATCH {number(address):#x} {label}")
    observations = spec.get("memory_observations", [])
    if not isinstance(observations, list) or len(observations) > 64:
        raise ValueError("At most64RAM observations are supported")
    labels = set()
    for observation in observations:
        at, size, label = number(observation["address"]), number(observation["size"]), observation["label"]
        if (not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,79}", label)
                or label in labels or not 1 <= size <= 64
                or not (0x70000000 <= at and at+size <= 0x71000000
                        or 0x7BFB0000 <= at and at+size <= 0x7BFF0000)):
            raise ValueError("Memory observations require distinct valid labels and bounded ordinary RAM intervals")
        labels.add(label)
        commands.append(f"MEMWATCH {at:#x} {size} {label}")
    commands += [f"BUDGET {number(spec.get('budget', 10000))}",
                 f"MODE {spec.get('execution_mode', 'step')}",
                 f"TRACE_EVERY {number(spec.get('trace_every', 1))}",
                 f"TRACE {(output/'trace.jsonl').resolve()}", "RUN"]
    for item in spec.get("dumps", []):
        name = item["name"]
        if Path(name).name != name:
            raise ValueError("Dump name must be a basename")
        commands.append(f"DUMP {number(item['address']):#x} {number(item['size'])} {(output/name).resolve()}")
    if nor_source:
        commands.append(f"NOR_SAVE {(output/'virtual-nor.bin').resolve()}")
    protocol = output / "scenario.protocol"
    protocol.write_text("\n".join(commands)+"\n")
    (output / "scenario.json").write_text(json.dumps(spec, indent=2)+"\n")
    timeout = number(spec.get("timeout_seconds", 120))
    if not 1 <= timeout <= 3600:
        raise ValueError("Execution timeout must be1..3600seconds")
    started = time.monotonic()
    execution = subprocess.run([str(backend), str(protocol.resolve())], capture_output=True, text=True,
                               timeout=timeout)
    elapsed = time.monotonic()-started
    (output / "stdout.txt").write_text(execution.stdout)
    (output / "stderr.txt").write_text(execution.stderr)
    results = [json.loads(line) for line in execution.stdout.splitlines()
               if line.startswith('{"event":"result",')]
    if execution.returncode or len(results) != 1:
        raise ValueError(f"Simulator failed; inspect {output}: {execution.stderr[-1500:]}")
    result = results[0]
    record = {"schema": 1, "name": spec["name"], "images": images, "result": result,
              "backend": {"path": str(backend), "sha256": backend_digest},
              "driver_sha256": driver_digest,
              "scenario_sha256": sha((output / "scenario.json").read_bytes()),
              "trace_sha256": sha((output / "trace.jsonl").read_bytes()),
              "trace_every_instructions": number(spec.get("trace_every", 1)),
              "execution_wall_seconds": round(elapsed, 6),
              "execution_mode": spec.get("execution_mode", "step"),
              "assumptions": spec.get("assumptions", []),
              "camera_contacted": False, "complete_camera_emulation": False}
    if observations:
        record["memory_observations"] = observations
    if aliases:
        record["ram_aliases"] = aliases
    if conditional_stops:
        record["stops_if_registers_differ"] = conditional_stops
    if "command_controller" in spec:
        record["command_controller"] = spec["command_controller"]
        record["control_event_sha256"] = sha((output/"control-events.jsonl").read_bytes())
    if nor_source:
        if sha(Path(nor_source["path"]).read_bytes()) != nor_source["sha256"]:
            raise ValueError("Virtual NOR source changed during execution")
        record["nor_source"] = dict(nor_source, unchanged=True)
        record["nor_output_sha256"] = sha((output/"virtual-nor.bin").read_bytes())
        record["nor_event_sha256"] = sha((output/"nor-events.jsonl").read_bytes())
    (output / "report.json").write_text(json.dumps(record, indent=2)+"\n")
    return record


def header_scenario(name: str, header: bytes, *, flag=1, floor=0, job_type=2) -> dict:
    spec = base_scenario(name)
    stub, entry, stack = 0x70008000, 0x7BD4FA18, 0x700F0000
    # Native call target,[d2,d3,a2,a3],88; stop immediately after the return.
    trampoline = b"\xdd"+struct.pack("<i", entry-stub)+bytes([0xF0, 88, 0xFF])
    spec["memory"] = [put(stub, trampoline), put(0x70010000, header),
                      word(0x70010204, job_type), word(0x7001020C, floor)]
    spec["registers"].update({"pc": stub, "d0": flag, "a0": 0x70010000, "a1": 0x70010200,
                              "d2": 0x22332233, "d3": 0x33443344, "a2": 0x44554455, "a3": 0x55665566})
    spec["stops"] = {"returned": stub+7}
    spec["expected_preserved"] = {name: value for name, value in spec["registers"].items()
                                  if name in ("sp", "d2", "d3", "a2", "a3")}
    return spec


def updater_tests(backend: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    image = Path("firmware/official-gm5-v11/GM5__V11.bin").read_bytes()
    if sha(image) != "d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243":
        raise ValueError("Official container differs")
    header = image[:512]
    controls = []
    for name, changes, flag, floor, expected in (
        ("official_header", {}, 1, 0, 0),
        ("raised_header", {0x1C: 0x01120112}, 1, 0, 0),
        ("version_not_above_floor", {}, 1, 0x0110, 0x80000064),
        ("relaxed_version_floor", {0x20: 0}, 1, 0x0110, 0),
        ("invalid_digest_selector", {0x2C: 1}, 1, 0, 0x80000006),
        ("invalid_cipher_selector", {0x34: 1}, 1, 0, 0x80000006),
        ("cipher_without_digest", {0x2C: 0}, 1, 0, 0x80000006),
        ("old_revision_flag_one", {0x08: 0x100}, 1, 0, 0x80000064),
        ("old_revision_flag_zero", {0x08: 0x100}, 0, 0, 0),
        ("wrong_model", {0x0C: 0x45504F4E}, 1, 0, 0x80000064),
    ):
        candidate = bytearray(header)
        for offset, value in changes.items():
            struct.pack_into("<I", candidate, offset, value)
        spec = header_scenario(name, bytes(candidate), flag=flag, floor=floor)
        record = run_scenario(spec, backend, output/name)
        result = record["result"]
        regs = [int(v, 0) for v in result["registers"]]
        if result["stop"] != "returned" or regs[0] != expected:
            raise ValueError(f"Native header control failed: {name}: {result}")
        for register, value in spec["expected_preserved"].items():
            if regs[REGISTERS[register]] != value:
                raise ValueError(f"Native call/return clobbered {register}: {name}")
        controls.append({"name": name, "expected_return": hex(expected), "actual_return": hex(regs[0]),
                         "steps": result["steps"], "call_frame_preserved": True,
                         "report": str(output/name/"report.json")})
    # Execute the installed-policy-equivalent native job snippet, then feed its
    # actual context+112 result to the native inner-marker branch.
    for flag in (0, 1):
        spec = base_scenario(f"allowance_flag_{flag}")
        spec["registers"]["pc"] = 0x7BD4FC1E
        spec["memory"] = [word(0x700F0010, flag), word(0x700F00FC, 0)]
        spec["stops"] = {"allowance_ready": 0x7BD4FC2C}
        spec["dumps"] = [{"name": "allowance.bin", "address": 0x700F00FC, "size": 4}]
        record = run_scenario(spec, backend, output/spec["name"])
        allowance = struct.unpack("<I", (output/spec["name"]/"allowance.bin").read_bytes())[0]
        if record["result"]["stop"] != "allowance_ready" or allowance != (1 if flag == 0 else 0):
            raise ValueError("Native allowance initialization differs")
        controls.append({"name": spec["name"], "runtime_flag": flag, "actual_allowance": allowance})
        for marker in (0, ord("p")):
            spec = base_scenario(f"marker_{marker:02x}_flag_{flag}")
            spec["registers"]["pc"] = 0x7BD4F147
            spec["memory"] = [word(0x700F0050, 0x70030000), word(0x700F003C, 0x70020000),
                              word(0x70020070, allowance), word(0x70020078, 1), put(0x70030000, bytes([marker]))]
            spec["stops"] = {"unsigned_allowed": 0x7BD4F1C5, "unsigned_rejected": 0x7BD4EF98,
                              "signature_required": 0x7BD4F16E}
            record = run_scenario(spec, backend, output/spec["name"])
            expected = "signature_required" if marker else "unsigned_allowed" if allowance else "unsigned_rejected"
            result = record["result"]
            if result["stop"] != expected or (expected == "unsigned_rejected" and int(result["registers"][0], 0) != 0x80000065):
                raise ValueError(f"Native marker control failed: {spec['name']}: {result}")
            controls.append({"name": spec["name"], "runtime_flag": flag, "allowance_from_native_job": allowance,
                             "expected_stop": expected, "actual_stop": result["stop"],
                             "return_register": result["registers"][0], "steps": result["steps"]})
    report = {"schema": 1, "scope": "GNU AM33-2 execution of GM5 native header/policy/marker routines",
              "controls": controls, "passed": len(controls), "camera_contacted": False,
              "limits": ["Function-level CPU execution; no Lumix ASIC/device or full boot model yet.",
                         "This suite stops before ECDSA; use signature-tests for native P-256 execution.",
                         "The complete updater and NOR programming path have not been emulated."]}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def initializer_tests(backend: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    main = Path(MAIN[0]).read_bytes()
    if sha(main) != MAIN[2]:
        raise ValueError("Official main program differs")
    controls = []
    for name, entry, end, source, source_end, destination, patched in (
        ("key_initializer", 0x4000018F, 0x400001AD, 0x40643B7C, 0x4064B5B8, 0x70000000, False),
        ("policy_initializer_stock", 0x40003000, 0x4000301E, 0x4064B5B8, 0x406DD768, 0x70A01E6C, False),
        ("policy_initializer_patched", 0x40003000, 0x4000301E, 0x4064B5B8, 0x406DD768, 0x70A01E6C, True),
    ):
        spec = base_scenario(name)
        spec["registers"]["pc"] = entry
        spec["stops"] = {"copy_finished": end}
        spec["budget"] = 2000000
        spec["trace_every"] = 1000
        size = source_end-source
        expected = bytearray(main[source-0x40000000:source_end-0x40000000])
        if patched:
            if expected[0x406B1BDC-source] != 1:
                raise ValueError("Expected initialized policy byte one")
            spec["memory"] = [put(0x406B1BDC, b"\0")]
            expected[0x406B1BDC-source] = 0
        spec["dumps"] = [{"name": "initialized.bin", "address": destination, "size": size}]
        record = run_scenario(spec, backend, output/name)
        actual = (output/name/"initialized.bin").read_bytes()
        if record["result"]["stop"] != "copy_finished" or actual != expected:
            raise ValueError(f"Native initializer control failed: {name}: {record['result']}")
        item = {"name": name, "source": hex(source), "end_exclusive": hex(source_end),
                "destination": hex(destination), "copied_bytes": size,
                "native_steps": record["result"]["steps"], "entire_destination_matches_rom": True,
                "destination_sha256": sha(actual), "virtual_rom_patched": patched,
                "trace_every_instructions": spec["trace_every"]}
        if name == "key_initializer":
            key = actual[0x70007950-destination:0x70007950-destination+16]
            if key.hex() != "f630c6cfad87f78031327ba55193fa4c":
                raise ValueError("Native initialized key differs")
            item["key_ram_matches_recovered_key"] = True
        else:
            value = actual[0x70A68490-destination]
            if value != (0 if patched else 1):
                raise ValueError("Native initialized signature policy differs")
            item["policy_ram_byte"] = value
        controls.append(item)
    a = (output/"policy_initializer_stock/initialized.bin").read_bytes()
    b = (output/"policy_initializer_patched/initialized.bin").read_bytes()
    differences = [hex(0x70A01E6C+i) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if differences != ["0x70a68490"]:
        raise ValueError("Virtual policy patch changed other initialized bytes")
    report = {"schema": 1, "scope": "GNU AM33-2 execution of actual GM5 initializer loops and one-byte virtual ROM policy patch",
              "controls": controls, "passed": len(controls), "patched_ram_differences": differences,
              "camera_contacted": False, "physical_firmware_modified": False,
              "limits": ["Starts at data-copy loops, after the first initializer's hardware-control prefix.",
                         "Does not establish safe full boot, installation, persistence of other settings, or recovery."]}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def signature_tests(backend: Path, output: Path) -> dict:
    from panasonic_signature_verify import PUBLIC_PROFILES, openssl_verify, verify
    output.mkdir(parents=True, exist_ok=False)
    image = Path("firmware/official-gm5-v11/GM5__V11.bin").read_bytes()
    if sha(image) != "d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243":
        raise ValueError("Official update differs")
    secondary = Path(SECONDARY[0]).read_bytes()
    if sha(secondary) != SECONDARY[2]:
        raise ValueError("Official secondary program differs")
    key_offset = PUBLIC_PROFILES["GM5"][2]
    public = secondary[key_offset:key_offset+64]
    digest = hashlib.sha256(image[0x2A0:0x2A0+812]).digest()
    signature = image[0x220:0x260]
    controls = []
    for name, changed_digest, changed_signature, expected in (
        ("official_directory_signature", digest, signature, True),
        ("modified_directory_digest", bytes([digest[0]^1])+digest[1:], signature, False),
        ("modified_signature", digest, bytes([signature[0]^1])+signature[1:], False),
    ):
        independent = verify(public, changed_digest, changed_signature)
        host = openssl_verify(public, changed_digest, changed_signature, "openssl")
        if independent != expected or host != expected:
            raise ValueError("Host signature controls disagree")
        spec = base_scenario(name)
        stub, entry = 0x70008000, 0x40273419
        spec["memory"] = [put(stub, b"\xdd"+struct.pack("<i", entry-stub)+bytes([0xF0, 220, 0xFF])),
                          put(0x70010000, public), put(0x70010200, changed_digest),
                          put(0x70010300, changed_signature)]
        spec["registers"].update(pc=stub, a0=0x70010000, a1=0x70010200, d0=0x70010300)
        spec["stops"] = {"returned": stub+7}
        spec["budget"] = 100000000
        spec["trace_every"] = 10000
        record = run_scenario(spec, backend, output/name)
        result = record["result"]
        if result["stop"] != "returned" or int(result["registers"][0], 0) != (0 if expected else 1):
            raise ValueError(f"Native ECDSA control differs: {name}: {result}")
        controls.append({"name": name, "native_return": result["registers"][0],
                         "native_instructions": result["steps"], "independent_ecdsa_valid": independent,
                         "libressl_valid": host, "native_valid": expected,
                         "digest_sha256_bytes": changed_digest.hex(), "report": str(output/name/"report.json")})
    report = {"schema": 1, "scope": "Execute GM5 native ECDSA wrapper and P-256 arithmetic in GNU AM33-2 simulator",
              "passed": len(controls), "controls": controls, "camera_contacted": False,
              "limits": ["Digest is supplied as a function input; this suite does not execute the caller's SHA-256 step.",
                         "Does not emulate the complete update job or NOR programming."]}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def sha_tests(backend: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    controls = []
    vectors = [("empty", b""), ("abc", b"abc")]
    vectors += [(f"length_{size}", bytes((i*29+7)%256 for i in range(size)))
                for size in (55, 56, 63, 64, 65, 812, 4096)]
    for name, data in vectors:
        spec = base_scenario("sha256_"+name)
        stub, entry = 0x70008000, 0x40274266
        spec["memory"] = [put(stub, b"\xdd"+struct.pack("<i", entry-stub)+bytes([0xF0, 132, 0xFF]))]
        if data:
            spec["memory"].append(put(0x70010000, data))
        spec["registers"].update(pc=stub, a0=0x70010000, a1=0x70012000, d0=len(data))
        spec["stops"] = {"returned": stub+7}
        spec["budget"] = 2000000
        spec["trace_every"] = 1000
        spec["dumps"] = [{"name": "digest.data", "address": 0x70012000, "size": 32}]
        record = run_scenario(spec, backend, output/name)
        actual = (output/name/"digest.data").read_bytes()
        if (record["result"]["stop"] != "returned" or int(record["result"]["registers"][0], 0)
                or actual != hashlib.sha256(data).digest()):
            raise ValueError(f"Native SHA-256 control failed: {name}: {record['result']}")
        controls.append({"name": name, "input_bytes": len(data), "native_digest": actual.hex(),
                         "matches_hashlib": True, "native_instructions": record["result"]["steps"],
                         "report": str(output/name/"report.json")})
    report = {"schema": 1, "scope": "Native GM5 SHA-256, including short byte-swap instructions and padding boundaries",
              "passed": len(controls), "controls": controls, "camera_contacted": False}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def decoder_scenario(name: str, image: Path, allowance: int, size: int) -> dict:
    spec = base_scenario(name)
    ctx, buffer, pool, stub = 0x70020000, 0x74000000, 0x70400000, 0x70008000
    spec["maps"].append([buffer, 0x2000000])
    spec["images"].append({"path": str(image), "address": buffer, "sha256": sha(image.read_bytes())})
    code = b"\xdd"+struct.pack("<i", 0x7BD4ED0A-stub)+bytes([0xF0, 36])
    # Header parsing clobbers scratch a0/a1; reload context and a null callback.
    code += b"\xfc\xdc"+struct.pack("<I", ctx)+b"\x95\x00"
    position = stub+len(code)
    code += b"\xdd"+struct.pack("<i", 0x7BD4EE4A-position)+bytes([0x30, 12])+b"\xff"
    spec["memory"] = [put(stub, code), word(ctx+4, buffer), word(ctx+8, size),
                      word(ctx+12, 1), word(ctx+16, 1), word(ctx+28, pool), word(ctx+32, 0x100000),
                      put(ctx+60, bytes.fromhex("f630c6cfad87f78031327ba55193fa4c")), word(ctx+92, 16),
                      word(ctx+108, 0x7BE2A6B8), word(ctx+112, allowance), word(ctx+116, 1), word(ctx+120, 1)]
    spec["registers"].update(pc=stub, a0=ctx, a1=0)
    spec["stops"] = {"returned": stub+len(code)-1}
    spec["budget"] = 10000000000
    spec["timeout_seconds"] = 1800
    spec["trace_every"] = 1000000
    spec["dumps"] = [{"name": "context.bin", "address": ctx, "size": 124},
                     {"name": "decoded-input.data", "address": buffer, "size": size}]
    spec["assumptions"].append("In-memory library input/context; the installation job and NOR programmer are never called.")
    return spec


def decoder_tests(backend: Path, output: Path, *, full=False) -> dict:
    from panasonic_upd import parse
    output.mkdir(parents=True, exist_ok=False)
    original = Path("firmware/official-gm5-v11/GM5__V11.bin").read_bytes()
    if sha(original) != "d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243":
        raise ValueError("Official update differs")
    fixture = bytearray(original[:0xA00])
    struct.pack_into("<I", fixture, 0x3C, len(fixture)-512)
    fixture[0x200] = 0
    fixture[0x2A0:0x2E0] = fixture[:0x40]
    struct.pack_into("<I", fixture, 0x2E8, 1)
    struct.pack_into("<I", fixture, 0x2EC+16, 1024)
    expected = Path(MAIN[0]).read_bytes()[:1024]
    fixture[0x2EC+28:0x2EC+60] = hashlib.sha256(expected).digest()
    struct.pack_into("<I", fixture, 0x40, zlib.crc32(fixture[512:]))
    # This deliberately small library fixture must never be used as an update.
    fixture_path = output/"library-input.data"
    fixture_path.write_bytes(fixture)
    corrupted = bytearray(fixture)
    corrupted[-1] ^= 1
    corrupted_path = output/"bad-crc-library-input.data"
    corrupted_path.write_bytes(corrupted)
    cases = [("unsigned_allowed_fixture", fixture_path, 1, 0),
             ("unsigned_denied_fixture", fixture_path, 0, 0x80000065),
             ("bad_crc_fixture", corrupted_path, 1, 0x80000064)]
    if full:
        candidate = Path("work/gm5-updater-prompt-0112/advertised-0112/GM5__V11.bin")
        if sha(candidate.read_bytes()) != "45a7da844d497f9c52d90a1a7db73e2b54fb18a38d3a639b602320a7df269ce3":
            raise ValueError("Validated full candidate differs")
        cases += [("full_unsigned_candidate", candidate, 1, 0),
                  ("full_unsigned_default_policy", candidate, 0, 0x80000065),
                  ("full_signed_official", Path("firmware/official-gm5-v11/GM5__V11.bin"), 0, 0)]
    controls = []
    for name, path, allowance, expected_status in cases:
        raw = path.read_bytes()
        spec = decoder_scenario(name, path, allowance, len(raw))
        record = run_scenario(spec, backend, output/name)
        result = record["result"]
        if result["stop"] != "returned" or int(result["registers"][0], 0) != expected_status:
            raise ValueError(f"Native full decoder control failed: {name}: {result}")
        after = (output/name/"decoded-input.data").read_bytes()
        components = []
        if expected_status == 0:
            for entry in parse(raw, allow_unsigned=True):
                start, size = entry["file_offset"], entry["size"]
                digest = sha(after[start:start+size])
                if digest != entry["field32_hex"]:
                    raise ValueError(f"Native plaintext differs from declared component digest: {name}/{entry['name']}")
                components.append({"name": entry["name"], "bytes": size, "native_plaintext_sha256": digest,
                                   "declared_sha256_matches": True})
        elif after != raw:
            raise ValueError("Rejected input was modified before expected validation failure")
        controls.append({"name": name, "input_sha256": sha(raw), "bytes": len(raw), "unsigned_allowance": allowance,
                         "native_return": result["registers"][0], "native_instructions": result["steps"],
                         "execution_wall_seconds": record["execution_wall_seconds"], "components": components,
                         "rejected_input_unchanged": after == raw if expected_status else None,
                         "report": str(output/name/"report.json")})
    report = {"schema": 1, "scope": "Execute native GM5 in-memory header/CRC/policy/signature/AES library validation without installation job",
              "passed": len(controls), "controls": controls, "full_candidate_included": full,
              "camera_contacted": False, "programming_job_called": False,
              "fixture_warning": "Small .data fixtures are for emulator tests only; never copy them to a camera card.",
              "limits": ["Does not exercise the UI, file discovery, full installation job or NOR programming.",
                         "Component SHA-256 values in unsigned mode are checked by the host after native decoding; the native branch skips them."]}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("updater-tests", "initializer-tests", "signature-tests", "sha-tests", "decoder-tests", "full-decoder-tests", "run"))
    parser.add_argument("scenario", type=Path, nargs="?")
    parser.add_argument("--backend", type=Path, default=DEFAULT_BACKEND)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.action != "run":
        test = {"updater-tests": updater_tests, "initializer-tests": initializer_tests,
                "signature-tests": signature_tests, "sha-tests": sha_tests, "decoder-tests": decoder_tests,
                "full-decoder-tests": lambda backend, output: decoder_tests(backend, output, full=True)}[args.action]
        report = test(args.backend, args.out)
        print(f"Passed {report['passed']} native CPU controls; evidence {args.out}")
    else:
        if args.scenario is None:
            parser.error("run requires a scenario JSON")
        report = run_scenario(json.loads(args.scenario.read_text()), args.backend, args.out)
        print(json.dumps(report["result"], indent=2))


if __name__ == "__main__":
    main()
