#!/usr/bin/env python3
"""Resume native ARM initialization through queue11 with two RAM preconditions."""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import struct

from gm5_arm_emulator import restored_scenario,run_scenario
from gm5_emulator import number,sha
from gm5_reflash_control import save_json


STATE=Path("work/gm5-arm-native-startup-3/native_kernel_prefix")
TABLE,TCB,QUEUE_BUFFER=0x369160,0x368E6C,0x571FD0
WORK_START,WORK_SIZE=0x400000,0x399000


def verify(directory:Path,record:dict)->dict:
    result=record["result"]
    if (result["stop"]!="queue11_created" or number(result["pc"])!=0x6932
            or number(result["registers"]["r0"])!=0 or result["fault"]is not None):
        raise ValueError(f"Native application initialization did not create queue11: {result}")
    private=(directory/"private-state.data").read_bytes()
    get=lambda at:struct.unpack_from("<I",private,at-0x340000)[0]
    pointers=[get(TABLE+4*i)for i in range(31)]
    if [i+1 for i,value in enumerate(pointers)if value]!=list(range(1,12)):
        raise ValueError("Native queue-table initialization differs from the11 created IDs")
    fields=struct.unpack_from("<9I",private,TCB-0x340000)
    if pointers[10]!=TCB or fields!=(0,5,QUEUE_BUFFER,QUEUE_BUFFER,0,0,0,0,0):
        raise ValueError("Native queue11 control block differs from the reviewed constructor")
    scratch=(directory/"caller.data").read_bytes()
    config=struct.unpack_from("<III",scratch,number(result["registers"]["sp"])-0x70000000+0x18)
    if config!=(0,5,QUEUE_BUFFER):raise ValueError("Native caller did not supply the actual queue11 parameters")
    return {"id":11,"tcb":hex(TCB),"attributes":fields[0],"capacity_words":fields[1],
            "storage":hex(fields[2]),"read_index":0,"write_index":0,"queued_words":0,
            "native_caller_parameters":[hex(value)for value in config],"created_queue_ids":list(range(1,12))}


def controls(output:Path,state:Path)->dict:
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    parent=json.loads((state/"report.json").read_text())
    if parent["result"]["stop"]!="before_application_object_creation":
        raise ValueError("Requires the completed native kernel prefix before its application call")
    cases=[]
    for label,fill in (("zero_work_storage",0),("poison_work_storage",165)):
        spec=restored_scenario("native_arm_application_object_creation",state)
        spec["maps"].append([WORK_START,WORK_SIZE])
        spec["dumps"].append({"name":"application-workarea.data","address":WORK_START,"size":WORK_SIZE})
        if fill:spec["memory"].append({"address":WORK_START,"hex":(bytes([fill])*WORK_SIZE).hex()})
        spec["budget"],spec["trace_every"]=3000000,1000
        spec["stops"]={"queue11_created":0x6932,"unexpected_zero_pc":0}
        spec["assumptions"] += [
            "Ordinary work storage400000..799000 covers ROM-selected fixed-pool buffers(e.g.43e3c8), native FIQ/IRQ stacks796c30/797030 and the797034..798034 4KiB kernel pool. The range is an explicit storage fixture, not a physical reset-state measurement.",
            f"New work storage starts with byte{fill}; unchanged native constructors must create every object header, pool link and queue pointer. No API return or object field is provided by the fixture."]
        directory=output/label
        record=run_scenario(spec,directory)
        queue=verify(directory,record)
        cases.append({"name":label,"directory":str(directory),"initial_work_fill":fill,"queue11":queue,"execution":record})
        print(f"Passed {label}",flush=True)
    first,second=[Path(case["directory"])for case in cases]
    if cases[0]["execution"]["result"]!=cases[1]["execution"]["result"]:
        raise ValueError("Native CPU state depends on the initial unallocated work bytes")
    for filename in ("arm-state.data","private-state.data","rom-source.data","caller.data"):
        if (first/filename).read_bytes()!=(second/filename).read_bytes():
            raise ValueError("Native global/kernel/caller storage differs across work-fill controls")
    report={"schema":1,"time_utc":datetime.now(timezone.utc).isoformat(),"passed":2,"cases":cases,
            "scope":"Continuous native ARM application initialization through the real queue11 constructor",
            "parent_state":str(state),"queue11":cases[0]["queue11"],
            "cpu_and_initialized_global_kernel_caller_states_identical_across_fills":True,
            "native_instructions_each":cases[0]["execution"]["result"]["instructions_started"],
            "pc_sp_lr_or_object_fields_replaced_by_fixture":False,
            "camera_contacted":False,"complete_arm_application_startup":False,
            "driver_sha256":sha((output/"driver-source.py").read_bytes()),
            "limits":["The application initializer stops immediately after successfulqueue11 creation, before its remaining object/task initialization.",
                      "Explicit ordinary work storage is tested with zero/A5 contents; actual physical RAM reset contents are not measured.",
                      "No timer, interrupt delivery, cache/MMU timing or native worker/reply path is claimed."]}
    save_json(output/"summary.json",report);return report


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--state",type=Path,default=STATE)
    args=parser.parse_args();controls(args.out,args.state)


if __name__=="__main__":main()
