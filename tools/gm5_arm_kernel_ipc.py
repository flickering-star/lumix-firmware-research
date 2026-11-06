#!/usr/bin/env python3
"""Pass captured MN103 requests through native ARM dispatch and word queue11.

Direct prefix/function entries use fresh Supervisor caller frames. No timer,
hardware interrupt, application task, reply or acknowledgement is supplied.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import struct

from gm5_arm_application_objects import verify as verify_application,TCB,QUEUE_BUFFER
from gm5_arm_emulator import restored_scenario,run_scenario
from gm5_emulator import number,sha
from gm5_reflash_control import save_json


ARM_STATE=Path("work/gm5-arm-native-application-objects-1/zero_work_storage")
MN103_STATE=Path("work/gm5-native-language-ready-tasks-2/native_parent_menu_entry/native_05")


def read(directory:Path,address:int,size:int)->bytes:
    report=json.loads((directory/"report.json").read_text())
    for dump in report["dumps"]:
        at,extent=number(dump["address"]),number(dump["size"])
        if at<=address and address+size<=at+extent:
            raw=(directory/dump["name"]).read_bytes()
            if sha(raw)!=dump["sha256"]:raise ValueError("ARM IPC snapshot dump changed")
            return raw[address-at:address-at+size]
    raise ValueError("ARM IPC observation is outside retained storage")


def queue(directory:Path)->dict:
    words=struct.unpack("<9I",read(directory,TCB,36))
    if words[:4]!=(0,5,QUEUE_BUFFER,QUEUE_BUFFER):raise ValueError("Queue11 identity/capacity/storage changed")
    return {"read_index":words[5],"write_index":words[4],"count":words[6],
            "storage_words":list(struct.unpack("<5I",read(directory,QUEUE_BUFFER,20)))}


def probe(output:Path,arm_state:Path,mn103_state:Path)->dict:
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    verify_application(arm_state,json.loads((arm_state/"report.json").read_text()))
    source=mn103_state/"service-notification.data";ring=source.read_bytes()
    if (len(ring)!=0xE10 or struct.unpack_from("<IHH",ring,0x110)!=(768,0,24)
            or [struct.unpack_from("<HHII",ring,o)for o in (0x118,0x124)] != [
                (0x800F,8,4,0xB027C17C),(0x800F,8,0,0xB027C02C)]):
        raise ValueError("Requires the exact two-message native MN103 ring snapshot")
    cases=[]

    def execute(name:str,prior:Path,entry:int,*,thumb=True,stop=0x7000FFF0,**arguments)->Path:
        spec=restored_scenario(name,prior)
        if not any(number(at)==0x93F01000 for at,_ in spec["maps"]):
            spec["maps"].append([0x93F01000,0x1000])
            spec["images"].append({"path":str(source),"address":0x93F01000,"sha256":sha(ring)})
            spec["dumps"].append({"name":"shared-ring.data","address":0x93F01000,"size":0x1000})
        spec["registers"].update(pc=entry,sp=0x7000E000,lr=0x7000FFF1,**arguments)
        spec["thumb"]=thumb
        spec["stops"]={"reviewed_boundary":stop}
        spec["trace_every"]=100
        spec["assumptions"] += [
            "Native-created kernel queues and all ordinary maps/banked/VFP state are retained; this direct probe deliberately supplies a fresh Supervisor caller PC/SP/LR and the shown function arguments.",
            "Original MN103 emulation ring bytes are restored without fabricating a header, payload or ring index. The page suffix beyond0xe10 is explicit zero backing.",
            "Unmodeled notification/local-controller operations remain stopped; direct handler/function calls are not hardware interrupt delivery or application-task execution."]
        if spec["memory"]:raise ValueError("Kernel IPC probe must not seed object/message fields directly")
        directory=output/name;record=run_scenario(spec,directory)
        if record["result"]["stop"]!="reviewed_boundary" or number(record["result"]["pc"])!=stop:
            raise ValueError(f"Native ARM kernel IPC stage stopped unexpectedly: {name}: {record['result']}")
        cases.append({"name":name,"directory":str(directory),"execution":record,"queue11":queue(directory)})
        print(f"Passed {name}",flush=True)
        return directory

    args=execute("actual_application_registration_arguments",arm_state,0xBC82,stop=0x19DFE)
    registers=cases[-1]["execution"]["result"]["registers"]
    if (number(registers["r0"]),number(registers["r1"]))!=(0x800F,0xBB8D):
        raise ValueError("Actual application registration arguments differ")
    context=execute("native_service_context_prefix",arm_state,0x6038,stop=0x604C)
    registered=execute("native_callback_registered_before_notification",context,0x23E82,stop=0x23F68,r0=0x800F,r1=0xBB8D)
    if struct.unpack("<I",read(registered,0x363480+0x478+15*4,4))[0]!=0xBB8D:
        raise ValueError("Native service registry did not install the actual callback")
    first=execute("native_receiver_message0_before_local_irq",registered,0x23C20,stop=0x23964)
    second=execute("native_receiver_message1_before_local_irq",first,0x23C20,stop=0x23964)
    objects=[]
    for directory,head,command,pointer in ((first,12,4,0xB027C17C),(second,24,0,0xB027C02C)):
        if struct.unpack("<IHH",read(directory,0x93F01110,8))!=(768,head,24):
            raise ValueError("Native receiver did not consume the actual ring entry")
        obj=struct.unpack("<I",read(directory,0x363484,4))[0]
        if struct.unpack("<HHII",read(directory,obj+8,12))!=(0x800F,8,command,pointer):
            raise ValueError("Native queued object differs from the original message")
        objects.append(obj)
    expected_words=[0x2027C17C,0x2027C02C]
    current=second
    for index,obj in enumerate(objects):
        current=execute(f"native_dispatch_and_kernel_send{index}",current,0x23F6E,r0=obj)
        observed=queue(current)
        if (observed["read_index"],observed["write_index"],observed["count"])!=(0,index+1,index+1) or observed["storage_words"][:index+1]!=expected_words[:index+1]:
            raise ValueError("Actual native callback did not post the translated request through kernel queue11")
    if struct.unpack("<II",read(current,0x363480,8))!=(0x363480,0x363480):
        raise ValueError("Native dispatch did not remove both completed callback objects from its list")
    sent=current
    for index,expected in enumerate(expected_words):
        current=execute(f"native_kernel_poll_receive{index}",current,0x20DE68,thumb=False,r0=11,r1=0x70001000,r2=0)
        result=cases[-1]["execution"]["result"]
        observed=queue(current)
        if (number(result["registers"]["r0"])!=0 or struct.unpack("<I",read(current,0x70001000,4))[0]!=expected
                or (observed["read_index"],observed["write_index"],observed["count"])!=(index+1,2,1-index)):
            raise ValueError("Native kernel polling receive did not return the actual queued request")
    before_empty=queue(current);last_output=read(current,0x70001000,4)
    empty=execute("native_empty_queue_poll_control",current,0x20DE68,thumb=False,r0=11,r1=0x70001000,r2=0)
    status=number(cases[-1]["execution"]["result"]["registers"]["r0"])
    if status!=(-50&0xFFFFFFFF) or queue(empty)!=before_empty or read(empty,0x70001000,4)!=last_output:
        raise ValueError(f"Native empty polling receive did not preserve the queue/output or return-50: {status:#x}")
    report={"schema":1,"time_utc":datetime.now(timezone.utc).isoformat(),"passed":len(cases),"cases":cases,
            "scope":"Actual captured MN103 requests through native ARM ring/registry/dispatch and real kernel word queue11",
            "arm_object_state":str(arm_state),"mn103_ring_source":str(source),"mn103_ring_sha256":sha(ring),
            "source_is_mn103_emulation_not_physical_ram":True,"native_queue_capacity":5,
            "native_sent_words":[hex(value)for value in expected_words],"queue_after_sends":queue(sent),
            "queue_after_receives":queue(empty),"empty_poll_status":-50,
            "message_headers_payloads_ring_offsets_or_queue_fields_written_by_fixture":False,
            "kernel_queue_api_return_stubs_used":False,"interrupts_or_peer_acknowledgements_supplied":False,
            "native_application_worker_or_reply_executed":False,"camera_contacted":False,
            "driver_sha256":sha((output/"driver-source.py").read_bytes()),
            "limits":["Direct prefix/handler/kernel calls use fresh Supervisor caller frames; complete scheduler/interrupt delivery is not modeled.",
                      "Receiver/registration stages stop before local-controller/notification accesses. The real kernel queue send/receive bodies execute without return stubs.",
                      "The native worker that processes queue11 and produces a reply has not run. No complete camera UI flow is claimed."]}
    save_json(output/"summary.json",report);print(json.dumps({"passed":len(cases),"kernel_queue_transport_passed":True}),flush=True)
    return report


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--arm-state",type=Path,default=ARM_STATE);parser.add_argument("--mn103-state",type=Path,default=MN103_STATE)
    args=parser.parse_args();probe(args.out,args.arm_state,args.mn103_state)


if __name__=="__main__":main()
