#!/usr/bin/env python3
"""Verify native ARM startup, object creation and captured-request transport."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil

from gm5_arm_application_objects import verify as verify_objects
from gm5_arm_emulator import ARM_IMAGE,ARM_SHA
from gm5_arm_startup_probe import BSS_START,BSS_END,PRIVATE_END
from gm5_cooperative_evidence import checked_arm
from gm5_emulator import number,sha
from gm5_prompt_package import artifact
from gm5_reflash_control import save_json


STARTUP=Path("work/gm5-arm-native-startup-3")
OBJECTS=Path("work/gm5-arm-native-application-objects-1")
IPC=Path("work/gm5-arm-native-kernel-ipc-2")
TESTS=Path("work/gm5-arm-state-full-tests.log")


def runtime_ast(path:Path)->str:
    module=ast.parse(path.read_text())
    function=next(node for node in module.body if isinstance(node,ast.FunctionDef)and node.name=="run_scenario")
    return sha(ast.dump(function,include_attributes=False).encode())


def collect(output:Path,release:Path)->dict:
    if output.exists()or release.exists():raise ValueError("Runtime evidence/release output already exists")
    log=TESTS.read_text()
    if "Ran 111 tests"not in log or not log.rstrip().endswith("OK")or "skipped"in log:
        raise ValueError("Requires the complete111-test regression run without skips")
    original=ARM_IMAGE.read_bytes()
    if sha(original)!=ARM_SHA:raise ValueError("Original backup ARM input changed")
    startup=json.loads((STARTUP/"summary.json").read_text())
    objects=json.loads((OBJECTS/"summary.json").read_text())
    ipc=json.loads((IPC/"summary.json").read_text())
    for directory,report in ((STARTUP,startup),(OBJECTS,objects),(IPC,ipc)):
        if sha((directory/"driver-source.py").read_bytes())!=report["driver_sha256"] or report["camera_contacted"]:
            raise ValueError("Runtime wrapper source/scope changed")
    native=[]
    fp=checked_arm(Path(startup["fp_directory"]),startup["native_fp_enable_prefix"])
    data=checked_arm(Path(startup["data_directory"]),startup["native_data_initialization"])
    kernel=checked_arm(Path(startup["kernel_directory"]),startup["native_kernel_prefix"])
    native.extend((fp,data,kernel))
    if (fp["result"]["stop"],fp["result"]["instructions_started"],number(fp["result"]["floating_point_registers"]["fpexc"]))!=("native_fp_ready",8,0x40000000):
        raise ValueError("Native floating-point initialization result differs")
    directory=Path(startup["data_directory"])
    private=bytes(BSS_END-BSS_START)+b"\xa5"*(PRIVATE_END-BSS_END)
    if (data["result"]["stop"]!="returned" or (directory/"arm-state.data").read_bytes()!=original
            or (directory/"rom-source.data").read_bytes()!=original or (directory/"private-state.data").read_bytes()!=private):
        raise ValueError("Native full copy/BSS storage oracle no longer holds")
    if (not startup["kernel_prefix_completed"] or kernel["result"]["stop"]!="before_application_object_creation"
            or number(kernel["result"]["pc"])!=0x1A1AF8
            or number(kernel["result"]["banked_registers"]["fiq"]["sp"])!=0x796C30
            or number(kernel["result"]["banked_registers"]["irq"]["sp"])!=0x797030):
        raise ValueError("Native kernel prefix or stack-bank initialization differs")
    if objects["passed"]!=2:raise ValueError("Application work-fill controls are incomplete")
    object_cases=[]
    for case in objects["cases"]:
        directory=Path(case["directory"])
        verify_objects(directory,case["execution"])
        execution=checked_arm(directory,case["execution"]);native.append(execution)
        object_cases.append(dict(name=case["name"],initial_work_fill=case["initial_work_fill"],execution=execution))
    first,second=[Path(case["directory"])for case in objects["cases"]]
    if objects["cases"][0]["execution"]["result"]!=objects["cases"][1]["execution"]["result"]:
        raise ValueError("Application CPU states differ between zero/A5 work storage")
    for filename in ("arm-state.data","private-state.data","rom-source.data","caller.data"):
        if (first/filename).read_bytes()!=(second/filename).read_bytes():raise ValueError("Initialized application state depends on unused work bytes")
    if (ipc["passed"]!=10 or ipc["kernel_queue_api_return_stubs_used"]
            or ipc["message_headers_payloads_ring_offsets_or_queue_fields_written_by_fixture"]
            or ipc["interrupts_or_peer_acknowledgements_supplied"]or ipc["native_application_worker_or_reply_executed"]):
        raise ValueError("Kernel IPC experiment is incomplete or claims an unexecuted worker/reply")
    source=Path(ipc["mn103_ring_source"])
    if sha(source.read_bytes())!=ipc["mn103_ring_sha256"]:raise ValueError("Native MN103 ring source changed")
    ipc_cases=[]
    for case in ipc["cases"]:
        directory=Path(case["directory"])
        execution=checked_arm(directory,case["execution"]);native.append(execution)
        spec=json.loads((directory/"scenario.json").read_text())
        if spec["memory"]:raise ValueError("Kernel IPC scenario directly seeds an object/message/queue field")
        if number(execution["result"]["pc"])==0x7000FFF0 and number(execution["result"]["registers"]["sp"])!=0x7000E000:
            raise ValueError("Native completed handler/kernel call did not restore its caller stack")
        ipc_cases.append(dict(name=case["name"],queue11=case["queue11"],execution=execution))
    by_name={case["name"]:case for case in ipc["cases"]}
    for index in (0,1):
        observed=by_name[f"native_dispatch_and_kernel_send{index}"]["queue11"]
        if (observed["read_index"],observed["write_index"],observed["count"])!=(0,index+1,index+1):raise ValueError("Native queue-send indices/count differ")
        if observed["storage_words"][:index+1]!=[0x2027C17C,0x2027C02C][:index+1]:raise ValueError("Native queue-send values differ")
    if (ipc["queue_after_receives"]["count"]!=0 or ipc["empty_poll_status"]!=-50
            or number(by_name["native_empty_queue_poll_control"]["execution"]["result"]["registers"]["r0"])!=(-50&0xFFFFFFFF)):
        raise ValueError("Native queue consumption/empty control differs")
    # The startup runs preceded the additive restore helper. Verify the actual
    # CPU-execution function is identical, and retain both real source versions.
    current=Path("tools/gm5_arm_emulator.py");wanted_ast=runtime_ast(current)
    core_sources={}
    for execution in native:
        source=Path(execution["directory"])/"driver-source.py"
        if runtime_ast(source)!=wanted_ast:raise ValueError("Runtime experiment used another CPU-execution implementation")
        core_sources[sha(source.read_bytes())]=source
    release.mkdir(mode=0o700)
    retained=[]
    sources=[(source,f"arm-core-{digest[:16]}.py")for digest,source in core_sources.items()]
    sources += [(STARTUP/"driver-source.py","startup-probe.py"),(OBJECTS/"driver-source.py","application-objects.py"),
                (IPC/"driver-source.py","kernel-ipc.py"),(Path(__file__),"runtime-evidence.py"),
                (Path("tools/arm_simulator/requirements-macos.txt"),"requirements-macos.txt"),
                (Path("tests/test_gm5_arm_architecture_state.py"),"test_architecture_state.py")]
    for source,name in sources:
        target=release/name;shutil.copyfile(source,target);retained.append(artifact(target))
    report={"schema":1,"time_utc":datetime.now(timezone.utc).isoformat(),
            "scope":"Native ARM FP/BSS/kernel initialization, real application queues and captured-request kernel transport",
            "camera_contacted":False,"physical_region_patch_installed":False,"arm_source":artifact(ARM_IMAGE),
            "cpu_execution_function_ast_sha256":wanted_ast,"actual_core_source_versions":list(core_sources),
            "retained_release":retained,"repository_tests":{"passed":111,"skipped":0,"log":artifact(TESTS)},
            "native_fp_setup":fp,"native_copy_bss":data,"native_kernel_prefix":kernel,
            "bss_oracle":startup["bss"],"zero_a5_application_controls":object_cases,"native_queue11":objects["queue11"],
            "native_queue_transport":ipc_cases,"native_sent_and_received_words":["0x2027c17c","0x2027c02c"],
            "empty_poll_status":-50,"mn103_ring_source_sha256":ipc["mn103_ring_sha256"],
            "native_instructions_started":sum(case["result"]["instructions_started"]for case in native),
            "complete_ui_or_worker_reply_flow":False,"kernel_queue_api_return_stubs_used":False,
            "interrupt_delivery_or_peer_acknowledgements_supplied":False,
            "source_is_emulated_mn103_state_not_physical_ram_dump":True,
            "limits":ipc["limits"]+[
                "Cortex-A9 is an explicit CPU fixture; physical ARM identity/cache/MMU/timer behavior is not established.",
                "The native FP setup writesCPACR0x00f00000, but this fixture's native/API readback is0. CPACR privilege behavior is not a hardware prediction; FPEXC and native NEON execution have separate controls.",
                "Application initialization currently stops atqueue11 creation. The remaining objects, worker tasks, scheduler and replies have not run.",
                "Ordinary work storage400000..799000 is an explicit ROM-selected buffer/stack/pool fixture; zero/A5 controls do not measure physical reset contents."]}
    save_json(output,report);return report


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--release",type=Path,required=True);args=parser.parse_args()
    report=collect(args.out,args.release)
    print(json.dumps({"repository_tests":111,"native_stages":len(report["native_queue_transport"])+5,
                      "native_instructions_started":report["native_instructions_started"]}),flush=True)


if __name__=="__main__":main()
