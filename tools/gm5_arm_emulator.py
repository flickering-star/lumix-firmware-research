#!/usr/bin/env python3
"""Bounded ARM/Thumb execution of private GM5 firmware; no camera transport.

Unicorn supplies the CPU and Capstone supplies diagnostics. The Cortex-A9
model is an explicit Thumb-2-capable fixture, not a hardware identification.
Unknown devices fault. Unreviewed system-control instructions stop; an opt-in
profile permits the pinned boot's FP-access/ISB sequence. Banked and VFP state
are retained explicitly between independent CPU runs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

from gm5_emulator import number, sha
from gm5_reflash_control import save_json


BACKUP = Path("captures/gm5-flash-backup-9z320rtf/result/flash32m.bin")
BACKUP_SHA = "c51dca467a8bd24c0be75915acb54692f9213a7d7b9896c5e50a010d830a35ca"
ARM_OFFSET, ARM_SIZE = 0x1760000, 0x340000
ARM_SHA = "3538e32f5310a89e48a2534f4cb4737fda679b8683a635bea31ab557cf762d3c"
ARM_IMAGE = Path("work/gm5-arm-private-inputs/installed-armcode.bin")
EXPECTED_PACKAGES = {"capstone": "5.0.9", "unicorn": "2.1.4"}
BANK_MODES = {"system": 0x1F, "fiq": 0x11, "irq": 0x12, "supervisor": 0x13,
              "abort": 0x17, "undefined": 0x1B}
FP_SETUP_SYSTEM_PCS = (0x318, 0x324, 0x32C)


def installed_arm() -> bytes:
    raw = BACKUP.read_bytes()
    if len(raw) != 0x2000000 or sha(raw) != BACKUP_SHA:
        raise ValueError("ARM input requires the complete pinned physical NOR backup")
    image = raw[ARM_OFFSET:ARM_OFFSET+ARM_SIZE]
    if sha(image) != ARM_SHA:
        raise ValueError("ARM component differs from the pinned backup slice")
    return image


def extract() -> Path:
    raw = installed_arm()
    if ARM_IMAGE.exists():
        if ARM_IMAGE.read_bytes() != raw:
            raise ValueError("Existing private ARM input differs; refusing to replace it")
        return ARM_IMAGE
    ARM_IMAGE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with ARM_IMAGE.open("xb") as output: output.write(raw)
    ARM_IMAGE.chmod(0o400)
    save_json(ARM_IMAGE.parent/"source.json", {
        "source": str(BACKUP), "source_sha256": BACKUP_SHA, "offset": hex(ARM_OFFSET),
        "bytes": ARM_SIZE, "path": str(ARM_IMAGE), "sha256": ARM_SHA,
        "camera_contacted": False, "derived_from_original_backup_not_a_new_camera_read": True})
    return ARM_IMAGE


def dependencies() -> tuple:
    import capstone
    import unicorn
    from unicorn import arm_const
    artifacts = []
    for name, module in (("capstone", capstone), ("unicorn", unicorn)):
        version = importlib.metadata.version(name)
        if version != EXPECTED_PACKAGES[name]:
            raise ValueError(f"ARM research backend requires {name}=={EXPECTED_PACKAGES[name]}")
        directory = Path(module.__file__).parent
        files = [Path(module.__file__)]+sorted(directory.rglob("*.dylib"))
        artifacts.append({"package": name, "distribution_version": version,
                          "binding_reported_version": module.__version__,
                          "files": [{"path": str(path), "bytes": path.stat().st_size,
                                     "sha256": sha(path.read_bytes())} for path in files]})
    return capstone, unicorn, arm_const, artifacts


def scenario(name: str, entry: int, *, thumb=True, budget=1000) -> dict:
    path = extract()
    return {"name": name, "maps": [[0, ARM_SIZE], [0x70000000, 0x10000]],
            "images": [{"path": str(path), "address": 0, "sha256": ARM_SHA}],
            "memory": [], "registers": {"pc": entry, "sp": 0x7000E000,
                                        "lr": 0x7000FFF1, "cpsr": 0x1F},
            "thumb": thumb, "budget": budget, "trace_every": 1,
            "stops": {"returned": 0x7000FFF0}, "dumps": [],
            "assumptions": [
                "The ARM component is the exact original physical NOR-backup slice, mapped at0 as suggested by its native reset/vector literals; no full relocation or boot has run.",
                "A Cortex-A9 CPU model supplies ARM/Thumb-2 execution, without identifying the camera's actual ARM CPU or asserting its cache/MMU/interrupt behavior.",
                "Image bytes and a separate zero-initialized64KiB caller scratch area are ordinary storage; there are no automatic device mappings.",
                "The caller supplies an explicit SP/LR and instruction-set state for a bounded function probe; no application context, IPC response or camera input is supplied.",
            ]}


def run_scenario(spec: dict, output: Path) -> dict:
    capstone, unicorn, arm, artifacts = dependencies()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    save_json(output/"scenario.json", spec)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    machine = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_ARM)
    machine.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_A9)
    registers = {f"r{i}": getattr(arm, f"UC_ARM_REG_R{i}") for i in range(13)}
    registers.update(sp=arm.UC_ARM_REG_SP, lr=arm.UC_ARM_REG_LR,
                     pc=arm.UC_ARM_REG_PC, cpsr=arm.UC_ARM_REG_CPSR)
    mapped = []
    for start, size in spec["maps"]:
        start, size = number(start), number(size)
        if start & 0xFFF or size <= 0 or size & 0xFFF or start+size > 0x100000000:
            raise ValueError("ARM maps require positive page-aligned bounded intervals")
        if any(start < end and previous < start+size for previous, end in mapped):
            raise ValueError("ARM maps overlap")
        machine.mem_map(start, size)
        mapped.append((start, start+size))

    def ordinary(address: int, size: int) -> None:
        if size < 1 or not any(start <= address and address+size <= end for start, end in mapped):
            raise ValueError("ARM fixture input/output is outside an explicit map")

    images = []
    for image in spec.get("images", []):
        path, at = Path(image["path"]), number(image["address"])
        raw = path.read_bytes()
        if sha(raw) != image["sha256"]:
            raise ValueError("ARM input image hash differs")
        ordinary(at, len(raw)); machine.mem_write(at, raw)
        images.append(dict(image, bytes=len(raw)))
    for item in spec.get("memory", []):
        at, raw = number(item["address"]), bytes.fromhex(item["hex"])
        ordinary(at, len(raw)); machine.mem_write(at, raw)
    # Select the register bank before supplying SP/LR. Changing SVC to System
    # after those writes would select that mode's still-zero bank instead.
    cpsr = number(spec["registers"].get("cpsr", 0x1F))
    cpsr = cpsr | 0x20 if spec.get("thumb", True) else cpsr & ~0x20
    for name, values in spec.get("banked_registers", {}).items():
        if name not in BANK_MODES: raise ValueError("Unsupported ARM register bank")
        machine.reg_write(arm.UC_ARM_REG_CPSR, (cpsr & ~0x1F) | BANK_MODES[name])
        fields = {"sp": arm.UC_ARM_REG_SP, "lr": arm.UC_ARM_REG_LR}
        if name in ("system", "fiq"):
            fields.update({f"r{i}": getattr(arm, f"UC_ARM_REG_R{i}") for i in range(8,13)})
        if name != "system": fields["spsr"] = arm.UC_ARM_REG_SPSR
        for register, value in values.items():
            if register not in fields or not 0 <= number(value) <= 0xFFFFFFFF:
                raise ValueError("Unsupported banked ARM register/value")
            machine.reg_write(fields[register], number(value))
    fp_fields = {"fpexc": arm.UC_ARM_REG_FPEXC, "fpscr": arm.UC_ARM_REG_FPSCR}
    fp_fields.update({f"d{i}": getattr(arm, f"UC_ARM_REG_D{i}") for i in range(32)})
    fp = spec.get("floating_point_registers", {})
    if "cpacr" in fp:
        value = number(fp["cpacr"])
        if not 0 <= value <= 0xFFFFFFFF: raise ValueError("CPACR is outside32bits")
        machine.cpr_write(15, 0, 1, 0, 2, 1, False, value)
        if machine.cpr_read(15, 0, 1, 0, 2, 1, False) != value:
            raise ValueError("Selected CPU fixture does not retain the requested CPACR value")
    for name, value in fp.items():
        if name == "cpacr": continue
        if name not in fp_fields or not 0 <= number(value) < 1 << (64 if name.startswith("d") else 32):
            raise ValueError("Unsupported floating-point register/value")
        machine.reg_write(fp_fields[name], number(value))
    machine.reg_write(arm.UC_ARM_REG_CPSR, cpsr)
    for name, value in spec["registers"].items():
        if name not in registers: raise ValueError("Unknown ARM register")
        if name != "cpsr": machine.reg_write(registers[name], number(value))
    # Restore T after supplying PC, without changing the already selected bank.
    machine.reg_write(arm.UC_ARM_REG_CPSR, cpsr)
    budget, interval = number(spec["budget"]), number(spec.get("trace_every", 1))
    if not 1 <= budget <= 50000000 or not 1 <= interval <= 1000000:
        raise ValueError("ARM instruction/trace budget is outside the bounded profile")
    stops = {number(value): label for label, value in spec["stops"].items()}
    if len(stops) != len(spec["stops"]): raise ValueError("ARM stop addresses overlap")
    mode = spec.get("execution_mode", "run")
    if mode not in ("run", "step"): raise ValueError("Unknown ARM execution mode")
    decoders = {False: capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM),
                True: capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)}
    approved_system = {}
    if spec.get("native_fp_setup_profile", False):
        original = ARM_IMAGE.read_bytes()
        if sha(original) != ARM_SHA:
            raise ValueError("Native floating-point setup requires the pinned original ARM image")
        approved_system = {pc: original[pc:pc+4] for pc in FP_SETUP_SYSTEM_PCS}
    count, stopped, fault = 0, None, None

    def state() -> dict:
        return {name: hex(machine.reg_read(identifier)) for name, identifier in registers.items()}

    with (output/"trace.jsonl").open("w") as trace:
        def code_hook(cpu, address, size, unused):
            nonlocal count, stopped
            if address in stops:
                stopped = stops[address]; cpu.emu_stop(); return
            if count >= budget:
                stopped = "budget_exhausted"; cpu.emu_stop(); return
            thumb = bool(cpu.reg_read(arm.UC_ARM_REG_CPSR) & 0x20)
            raw = bytes(cpu.mem_read(address, size))
            decoded = next(decoders[thumb].disasm(raw, address, count=1), None)
            if count % interval == 0:
                trace.write(json.dumps({"step": count, "pc": hex(address), "thumb": thumb,
                                        "bytes": raw.hex(), "instruction": None if decoded is None else f"{decoded.mnemonic} {decoded.op_str}",
                                        "registers": state()}, sort_keys=True)+"\n")
            privileged = decoded is not None and decoded.mnemonic.startswith((
                "mrc", "mcr", "mrrc", "mcrr", "svc", "swi", "wfi", "wfe", "smc", "hvc", "bkpt", "udf"))
            approved = not thumb and address in approved_system and raw == approved_system[address]
            if decoded is None or privileged and not approved:
                stopped = "unmodeled_system_instruction"; cpu.emu_stop(); return
            count += 1

        def invalid_hook(cpu, access, address, size, value, unused):
            nonlocal fault, stopped
            stopped = "unmapped_or_protected_access"
            fault = {"access": access, "address": hex(address), "bytes": size,
                     "value": hex(value), "instruction_pc": hex(cpu.reg_read(arm.UC_ARM_REG_PC))}
            return False

        machine.hook_add(unicorn.UC_HOOK_CODE, code_hook)
        machine.hook_add(unicorn.UC_HOOK_MEM_INVALID, invalid_hook)
        error = None
        try:
            while stopped is None:
                pc = machine.reg_read(arm.UC_ARM_REG_PC)
                thumb = bool(machine.reg_read(arm.UC_ARM_REG_CPSR) & 0x20)
                machine.emu_start(pc | int(thumb), 0xFFFFFFFF, count=1 if mode == "step" else 0)
                if mode == "run" and stopped is None:
                    stopped = "engine_returned_without_boundary"
        except unicorn.UcError as exception:
            error = str(exception)
            if stopped is None: stopped = "cpu_exception"
    dumps = []
    for dump in spec.get("dumps", []):
        at, size, name = number(dump["address"]), number(dump["size"]), dump["name"]
        if Path(name).name != name: raise ValueError("ARM dump name must be a local filename")
        ordinary(at, size); raw = bytes(machine.mem_read(at, size))
        (output/name).write_bytes(raw)
        dumps.append(dict(dump, sha256=sha(raw)))
    live = state()
    banked = {}
    saved_cpsr = machine.reg_read(arm.UC_ARM_REG_CPSR)
    if saved_cpsr & 0x1F not in tuple(BANK_MODES.values())+(0x10,):
        raise ValueError("Cannot serialize an unsupported ARM CPU mode")
    for name, mode_value in BANK_MODES.items():
        machine.reg_write(arm.UC_ARM_REG_CPSR, (saved_cpsr & ~0x1F) | mode_value)
        banked[name] = {"sp": hex(machine.reg_read(arm.UC_ARM_REG_SP)),
                        "lr": hex(machine.reg_read(arm.UC_ARM_REG_LR))}
        if name in ("system", "fiq"):
            banked[name].update({f"r{i}": hex(machine.reg_read(getattr(arm, f"UC_ARM_REG_R{i}"))) for i in range(8,13)})
        if name != "system": banked[name]["spsr"] = hex(machine.reg_read(arm.UC_ARM_REG_SPSR))
    machine.reg_write(arm.UC_ARM_REG_CPSR, saved_cpsr)
    if state() != live: raise ValueError("Banked-register observation changed the stopped CPU state")
    floating_point = {name: hex(machine.reg_read(identifier)) for name, identifier in fp_fields.items()}
    floating_point["cpacr"] = hex(machine.cpr_read(15, 0, 1, 0, 2, 1, False))
    result = {"stop": stopped, "instructions_started": count,
              "pc": hex(machine.reg_read(arm.UC_ARM_REG_PC)), "registers": state(),
              "banked_registers": banked, "floating_point_registers": floating_point,
              "fault": fault, "engine_error": error}
    report = {"schema": 1, "time_utc": datetime.now(timezone.utc).isoformat(), "name": spec["name"],
              "result": result, "images": images, "dependencies": artifacts, "dumps": dumps,
              "scenario_sha256": sha((output/"scenario.json").read_bytes()),
              "trace_sha256": sha((output/"trace.jsonl").read_bytes()),
              "driver_sha256": sha((output/"driver-source.py").read_bytes()),
              "cpu_model_fixture": "Cortex-A9", "assumptions": spec.get("assumptions", []),
              "native_fp_setup_profile": bool(approved_system),
              "fp_system_profile_limit": "In this Cortex-A9 fixture, the native CPACR write/readback control returns0 after writing0x00f00000. FPEXC/NEON operation is tested separately; CPACR privilege behavior is not a hardware prediction." if approved_system else None,
              "camera_contacted": False, "complete_camera_emulation": False,
              "interrupt_delivery_or_ipc_acknowledgements_supplied": False}
    save_json(output/"report.json", report)
    return report


def restored_scenario(name: str, directory: Path) -> dict:
    """Restore all ordinary maps and supported CPU state from a clean stop."""
    report = json.loads((directory/"report.json").read_text())
    previous = json.loads((directory/"scenario.json").read_text())
    if (sha((directory/"scenario.json").read_bytes()) != report["scenario_sha256"]
            or sha((directory/"trace.jsonl").read_bytes()) != report["trace_sha256"]):
        raise ValueError("ARM resume scenario/trace differs from the execution receipt")
    result = report["result"]
    if result["fault"] is not None or result["engine_error"] is not None:
        raise ValueError("An ARM fault/exception snapshot needs a new diagnostic probe, not automatic continuation")
    if "banked_registers" not in result or "floating_point_registers" not in result:
        raise ValueError("ARM snapshot lacks the required banked/floating-point state")
    images = []
    for start, size in previous["maps"]:
        matches = [dump for dump in report["dumps"]
                   if (number(dump["address"]), number(dump["size"])) == (number(start), number(size))]
        if len(matches) != 1:
            raise ValueError("ARM resume requires exactly one complete retained dump for every explicit map")
        dump = matches[0]
        path = directory/dump["name"]
        raw = path.read_bytes()
        if len(raw) != number(size) or sha(raw) != dump["sha256"]:
            raise ValueError("ARM snapshot dump changed or is truncated")
        images.append({"path": str(path), "address": number(start), "sha256": dump["sha256"]})
    return {"name": name, "maps": previous["maps"], "images": images, "memory": [],
            "registers": {key: number(value) for key, value in result["registers"].items()},
            "banked_registers": result["banked_registers"],
            "floating_point_registers": result["floating_point_registers"],
            "thumb": bool(number(result["registers"]["cpsr"]) & 0x20),
            "budget": 1000000, "trace_every": previous.get("trace_every", 1),
            "stops": {}, "dumps": previous["dumps"],
            "assumptions": report["assumptions"]+[
                f"Every explicit ordinary-memory map and the supported live/banked/VFP registers are restored from{directory}; PC/SP/LR are not replaced by a new caller.",
                "Cache/MMU/device/interrupt state remains outside this bounded ARM snapshot model. The selected fixture's CPACR readback limitation remains applicable."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--entry", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--thumb", action="store_true")
    parser.add_argument("--budget", type=int, default=1000)
    args = parser.parse_args()
    spec = scenario("native_arm_bounded_probe", args.entry, thumb=args.thumb, budget=args.budget)
    report = run_scenario(spec, args.out)
    print(json.dumps(report["result"]), flush=True)


if __name__ == "__main__": main()
