#!/usr/bin/env python3
"""Run native ARM copy/BSS initialization, then its bounded kernel prefix."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import gm5_arm_emulator as arm_cpu
from gm5_emulator import number, sha
from gm5_reflash_control import save_json


BSS_START, BSS_END, PRIVATE_END = 0x340000, 0x3FC22C, 0x400000
NOR_ARM = 0x41760000
DUMPS=(("arm-state.data",0,arm_cpu.ARM_SIZE),
       ("private-state.data",BSS_START,PRIVATE_END-BSS_START),
       ("rom-source.data",NOR_ARM,arm_cpu.ARM_SIZE),
       ("caller.data",0x70000000,0x10000))


def probe(output: Path) -> dict:
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    fp=arm_cpu.scenario("native_arm_fp_enable_prefix",0x318,thumb=False)
    fp["registers"]["cpsr"]=0x93
    fp["native_fp_setup_profile"]=True
    fp["stops"]={"native_fp_ready":0x338}
    fp["assumptions"].append("Only the pinned native CPACR/ISB/FPEXC setup at318..338 is permitted; cache/MMU setup outside this profile remains a stop. The fixture's CPACR readback limitation is recorded explicitly.")
    enabled=arm_cpu.run_scenario(fp,output/"native_fp_enable")
    if (enabled["result"]["stop"]!="native_fp_ready" or enabled["result"]["instructions_started"]!=8
            or number(enabled["result"]["floating_point_registers"]["fpexc"])!=0x40000000):
        raise ValueError("Native floating-point enable prefix did not establish the tested FPEXC state")
    spec=arm_cpu.scenario("native_arm_copy_bss_initialization",0x20C,thumb=False,budget=3000000)
    spec["registers"]["cpsr"]=0x93
    spec["floating_point_registers"]=enabled["result"]["floating_point_registers"]
    spec["banked_registers"]=enabled["result"]["banked_registers"]
    spec["maps"] += [[BSS_START,PRIVATE_END-BSS_START],[NOR_ARM,arm_cpu.ARM_SIZE]]
    spec["images"].append({"path":str(arm_cpu.ARM_IMAGE),"address":NOR_ARM,"sha256":arm_cpu.ARM_SHA})
    # Poison establishes that the real initializer performs the clear. The
    # suffix after the exact native BSS end must remain poisoned.
    spec["memory"]=[{"address":BSS_START,"hex":(b"\xa5"*(PRIVATE_END-BSS_START)).hex()}]
    spec["dumps"]=[{"name":name,"address":at,"size":size}for name,at,size in DUMPS]
    spec["trace_every"]=10000
    spec["assumptions"] += [
        "Native0x20c copies ROM-selected text/rodata/data intervals from the exact backup ARM slice atNOR41760000, then clears its declared BSS340000..3fc22c.",
        "The containing private RAM pages340000..400000 start poisonedA5 as a deliberate verification precondition, not a claim about physical reset contents.",
        "The NOR source is ordinary fixture storage in this prototype; its complete post-run bytes must remain identical. No flash programming model is claimed for ARM accesses."]
    directory=output/"native_data_initialization"
    initialized=arm_cpu.run_scenario(spec,directory)
    result=initialized["result"]
    expected_private=bytes(BSS_END-BSS_START)+b"\xa5"*(PRIVATE_END-BSS_END)
    if (result["stop"]!="returned" or number(result["registers"]["sp"])!=0x7000E000
            or (directory/"arm-state.data").read_bytes()!=arm_cpu.ARM_IMAGE.read_bytes()
            or (directory/"rom-source.data").read_bytes()!=arm_cpu.ARM_IMAGE.read_bytes()
            or (directory/"private-state.data").read_bytes()!=expected_private):
        raise ValueError(f"Native ARM startup copy/BSS whole-image oracle differs: {result}")
    print("Passed native copy/BSS initialization and complete storage oracles",flush=True)
    kernel=arm_cpu.scenario("native_arm_kernel_start_prefix",0x1A1AC4,thumb=False,budget=3000000)
    kernel["maps"] = spec["maps"]
    kernel["images"]=[{"path":str(directory/name),"address":at,"sha256":sha((directory/name).read_bytes())}for name,at,_ in DUMPS]
    kernel["dumps"]=spec["dumps"]
    kernel["trace_every"]=1000
    kernel["registers"]["cpsr"]=0x93
    kernel["floating_point_registers"]=initialized["result"]["floating_point_registers"]
    kernel["banked_registers"]=initialized["result"]["banked_registers"]
    kernel["stops"]={"before_application_object_creation":0x1A1AF8,"unexpected_zero_pc":0}
    kernel["assumptions"] += [
        "The preceding complete native copy/BSS result is restored. The unchanged kernel-start wrapper runs until its application-object initializer call or a real unsupported boundary.",
        "This is a direct prefix probe with a new Supervisor-mode caller frame(CPSR93). Native1a16e8 initializes FIQ/IRQ banks then returns in Supervisor mode; a System-mode caller would have a different LR/SP bank.",
        "No physical reset, cache/MMU configuration, timer setup or interrupt delivery has run. Supported banked/VFP registers are restored explicitly; the new Supervisor caller SP/LR replace the prior function's live caller frame."]
    kernel_directory=output/"native_kernel_prefix"
    prefix=arm_cpu.run_scenario(kernel,kernel_directory)
    complete=prefix["result"]["stop"]=="before_application_object_creation"
    report={"schema":1,"time_utc":datetime.now(timezone.utc).isoformat(),
            "scope":"Native ARM copy/BSS storage initialization and bounded kernel-start prefix",
            "native_fp_enable_prefix":enabled,"fp_directory":str(output/"native_fp_enable"),
            "native_data_initialization":initialized,"data_directory":str(directory),
            "bss":{"start":hex(BSS_START),"end_exclusive":hex(BSS_END),"bytes":BSS_END-BSS_START,
                   "initial_poison":165,"exact_native_zero_oracle_passed":True,"page_suffix_still_poisoned":True},
            "whole_input_image_and_rom_source_unchanged":True,
            "native_kernel_prefix":prefix,"kernel_directory":str(kernel_directory),
            "kernel_prefix_completed":complete,"camera_contacted":False,"complete_arm_boot":False,
            "driver_sha256":sha((output/"driver-source.py").read_bytes()),
            "limits":["Native copy/BSS initialization is complete; hardware reset/cache/MMU/timer/interrupt setup is not modeled.",
                      "The containing private RAM page suffix remains explicit poisoned fixture storage outside the native BSS interval.",
                      "The kernel prefix stops before application-object creation or at an unsupported native access; application tasks/replies have not run."]}
    save_json(output/"summary.json",report)
    print(json.dumps({"kernel_prefix_completed":complete,"result":prefix["result"]}),flush=True)
    return report


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args();probe(args.out)


if __name__=="__main__":main()
