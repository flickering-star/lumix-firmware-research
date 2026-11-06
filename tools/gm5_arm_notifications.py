#!/usr/bin/env python3
"""Record exact ARM notification stores while native tasks keep executing.

The recorded request does not deliver an interrupt or acknowledge a peer.
Other device operations remain CPU faults. No application instruction is patched.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

from gm5_arm_emulator import ARM_IMAGE,ARM_SHA,restored_scenario,run_scenario
from gm5_emulator import number,sha
from gm5_reflash_control import save_json


STORES={0x23F68:(0x9C013006,1),0x23BD0:(0x9C013006,1)}


def request(result:dict,image:bytes)->dict:
    pc=number(result["pc"]);registers=result["registers"]
    if sha(image)!=ARM_SHA or pc not in STORES or image[pc:pc+2]!=bytes.fromhex("0180"):
        raise ValueError("ARM notification is outside the pinned native STRH profile")
    at,value=STORES[pc]
    if not(number(registers["cpsr"])&0x20)or number(registers["r0"])!=at or number(registers["r1"])!=value:
        raise ValueError("Native ARM notification instruction operands/state differ")
    return {"instruction_pc":hex(pc),"register":hex(at),"bytes":2,"value":value,
            "continuation_pc":hex(pc+2),"interrupt_delivered":False,"peer_acknowledgement_supplied":False}


def probe(output:Path,state:Path)->dict:
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    image=ARM_IMAGE.read_bytes();original=restored_scenario("native_arm_tasks_record_notifications",state)
    stops={"application_worker_entry":0xBC24,"unexpected_zero_pc":0}
    for at in STORES:stops[f"pending_notification_{at:x}"]=at
    remaining=2000000;stages=[];events=[];current=original
    for index in range(64):
        current["stops"],current["budget"],current["trace_every"]=stops,remaining,1000
        directory=output/f"native_{index:02d}"
        record=run_scenario(current,directory);result=record["result"]
        stages.append({"directory":str(directory),"execution":record});remaining-=result["instructions_started"]
        if not result["stop"].startswith("pending_notification_"):
            report={"schema":1,"time_utc":datetime.now(timezone.utc).isoformat(),
                    "scope":"Continuous native ARM task execution with exact notification writes recorded without delivery",
                    "native_stages":stages,"pending_notification_requests":events,
                    "native_instructions_started":sum(stage["execution"]["result"]["instructions_started"]for stage in stages),
                    "modeled_strh_stores":len(events),"last_directory":str(directory),"last_execution":record,
                    "application_worker_entry_reached":result["stop"]=="application_worker_entry",
                    "task_selection_or_stack_frame_provided_by_fixture":False,
                    "interrupts_or_peer_acknowledgements_supplied":False,"camera_contacted":False,
                    "driver_sha256":sha((output/"driver-source.py").read_bytes()),
                    "limits":["Only pinned native STRH writes at23f68/23bd0 withr0=9c013006,r1=1,Thumb state are consumed.",
                              "The consumed store records a request without hardware delivery; all live/banked/VFP registers are preserved andPC advances2.",
                              "Other unknown device accesses remain faults; no peer response, timer tick or application message is invented."]}
            save_json(output/"summary.json",report)
            print(json.dumps({"stop":result["stop"],"pc":result["pc"],"instructions":report["native_instructions_started"],
                              "notifications":len(events),"fault":result["fault"]}),flush=True)
            return report
        event=request(result,image)
        if remaining<1:raise ValueError("ARM notification sequence exhausted its instruction budget")
        remaining-=1;events.append(dict(event,after_native_stage=index))
        current=restored_scenario(original["name"],directory)
        current["registers"]["pc"]=number(event["continuation_pc"])
        current["assumptions"].append("The exact native STRH request is recorded without delivery/ACK; memory-visible register hardware state is not fabricated, CPU registers/flags/banks/VFP are preserved andPC advances2.")
    raise ValueError("Native ARM notification probe exceeded its64-request bound")


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--state",type=Path,default=Path("work/gm5-arm-native-first-service-registration-1"))
    args=parser.parse_args();probe(args.out,args.state)


if __name__=="__main__":main()
