#!/usr/bin/env python3
"""Trace captured MN103 messages through bounded native ARM receiver stages.

Each stage is a direct function/prefix probe with a fresh caller frame. Actual
interrupt delivery, ARM kernel mailboxes and replies remain unmodeled.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct

import gm5_arm_emulator as arm_cpu
from gm5_emulator import number, sha
from gm5_reflash_control import save_json
from gm5_region_emulator import candidate, inputs


STATE = Path("work/gm5-native-language-ready-tasks-2/native_parent_menu_entry/native_05")
CONTEXT = 0x363480
CONTEXT_PAGE = 0x363000
SNAPSHOTS = (("arm-state.data",0,arm_cpu.ARM_SIZE),
             ("caller.data",0x70000000,0x10000),
             ("arm-context.data",CONTEXT_PAGE,0x1000),
             ("shared-ring.data",0x93F01000,0x1000),
             ("shared-camera-ram.data",0x20000000,0x1000000))


def word(raw: bytes, at: int) -> int:
    return struct.unpack_from("<I",raw,at)[0]


def probe(output: Path, state: Path) -> dict:
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    (output/"driver-source.py").write_bytes(Path(__file__).read_bytes())
    main,_,_ = inputs()
    if (state/"virtual-nor.bin").read_bytes()[:len(main)] != candidate(main):
        raise ValueError("ARM IPC probe requires the exact virtually installed region candidate")
    source_ram=(state/"ram.data").read_bytes()
    source_rings=(state/"service-notification.data").read_bytes()
    if len(source_ram)!=0x1000000 or struct.unpack_from("<IHH",source_rings,0x110)!=(768,0,24):
        raise ValueError("ARM IPC probe requires the retained two-message native ring snapshot")
    if [struct.unpack_from("<HHII",source_rings,o) for o in (0x118,0x124)] != [
            (0x800F,8,4,0xB027C17C),(0x800F,8,0,0xB027C02C)]:
        raise ValueError("Retained native messages differ from the reviewed application requests")
    cases=[]

    def execute(name: str, entry: int, stop: int, *, prior: Path | None=None, **registers) -> Path:
        spec=arm_cpu.scenario(name,entry)
        spec["maps"] += [[CONTEXT_PAGE,0x1000],[0x93F01000,0x1000],[0x20000000,0x1000000]]
        if prior:
            spec["images"]=[{"path":str(prior/filename),"address":at,
                             "sha256":sha((prior/filename).read_bytes())} for filename,at,_ in SNAPSHOTS]
        else:
            spec["images"] += [{"path":str(state/"service-notification.data"),"address":0x93F01000,"sha256":sha(source_rings)},
                                {"path":str(state/"ram.data"),"address":0x20000000,"sha256":sha(source_ram)}]
        spec["registers"].update(registers)
        spec["stops"]={"reviewed_native_boundary":stop}
        spec["dumps"]=[{"name":filename,"address":at,"size":size} for filename,at,size in SNAPSHOTS]
        spec["assumptions"] += [
            "ROM-selected ARM context storage at0x363480 uses an explicit zero-initialized ordinary page; full ARM BSS/kernel startup has not run.",
            "The exact MN103 ring/RAM snapshot is restored. Native ARM code translates0xb0 pointers to0x20 addresses; this serial probe maps that view to the captured0x70 RAM bytes, without cache timing or simultaneous CPUs.",
            "Each stage enters an unchanged native function/prefix with a fresh caller frame. An earlier peripheral stop is not claimed to have returned or delivered an interrupt.",
            "The shared-ring page's suffix beyond the retained0xe10 bytes starts zero as explicit unused backing; no physical value is inferred."]
        directory=output/name
        record=arm_cpu.run_scenario(spec,directory)
        if record["result"]["stop"]!="reviewed_native_boundary" or number(record["result"]["pc"])!=stop:
            raise ValueError(f"ARM IPC stage stopped unexpectedly: {name}: {record['result']}")
        if (directory/"shared-camera-ram.data").read_bytes()!=source_ram:
            raise ValueError("Bounded ARM IPC stage unexpectedly changed captured camera RAM")
        cases.append({"name":name,"directory":str(directory),"execution":record})
        print(f"Passed {name}",flush=True)
        return directory

    # The real application registration site computes these arguments itself.
    args=execute("native_800f_registration_arguments",0xBC82,0x19DFE)
    registers=cases[-1]["execution"]["result"]["registers"]
    identifier,callback=number(registers["r0"]),number(registers["r1"])
    if (identifier,callback)!=(0x800F,0xBB8D):
        raise ValueError("Native service-registration site selected another callback")
    context=execute("native_arm_service_context_prefix",0x6038,0x604C)
    image=(context/"arm-state.data").read_bytes()
    page=(context/"arm-context.data").read_bytes()
    base=CONTEXT-CONTEXT_PAGE
    expected=bytearray(arm_cpu.ARM_IMAGE.read_bytes());struct.pack_into("<I",expected,0x2F1D08,CONTEXT)
    if (image!=expected or word(page,base)!=CONTEXT or word(page,base+4)!=CONTEXT
            or word(page,base+0x474)!=CONTEXT+0x478):
        raise ValueError("Native ARM service prefix did not establish its context/list/callback table")
    registered=execute("native_arm_callback_registration_before_notification",0x23E82,0x23F68,
                       prior=context,r0=identifier,r1=callback)
    page=(registered/"arm-context.data").read_bytes()
    ring=(registered/"shared-ring.data").read_bytes()
    registers=cases[-1]["execution"]["result"]["registers"]
    if (word(page,base+0x478+15*4),word(ring,12),number(registers["r0"]),number(registers["r1"])) != (
            callback,0x8000,0x9C013006,1):
        raise ValueError("Native ARM registration did not set the reviewed callback/mask/notification operands")
    # Poll the actual receiver twice. Each call stops before its first local
    # interrupt-controller operation; the native ring head/object list updates
    # have already happened. These are direct polling fixtures, not IRQ claims.
    first=execute("native_arm_first_ring_message_before_local_irq",0x23C20,0x23964,prior=registered)
    second=execute("native_arm_second_ring_message_before_local_irq",0x23C20,0x23964,prior=first)
    objects=[]
    for directory,head,command,pointer in ((first,12,4,0xB027C17C),(second,24,0,0xB027C02C)):
        ring=(directory/"shared-ring.data").read_bytes()
        page=(directory/"arm-context.data").read_bytes()
        if struct.unpack_from("<IHH",ring,0x110)!=(768,head,24):
            raise ValueError("Native ARM receiver did not advance the actual ring head")
        # Native list tail identifies the newly inserted fixed-pool object.
        object_address=word(page,base+4)
        fields=struct.unpack_from("<HHII",page,object_address-CONTEXT_PAGE+8)
        if fields!=(0x800F,8,command,pointer):
            raise ValueError("Native ARM receiver did not preserve service/length/payload in its queued object")
        objects.append({"address":hex(object_address),"service_id":"0x800f","payload_bytes":8,
                        "command":command,"mn103_pointer":hex(pointer),"arm_pointer":hex((pointer&0x0FFFFFFF)|0x20000000)})
    selected=execute("native_arm_dispatch_selected_real_callback",0x23F6E,0xBB8C,
                     prior=second,r0=number(objects[0]["address"]))
    registers=cases[-1]["execution"]["result"]["registers"]
    if (number(registers["r0"]),number(registers["r1"]))!=(number(objects[0]["address"])+12,8):
        raise ValueError("Native ARM dispatcher supplied incorrect callback payload/length")
    for index,obj in enumerate(objects):
        execute(f"native_arm_message{index}_before_kernel_mailbox",0x23F6E,0x1D3C04,
                prior=second,r0=number(obj["address"]))
        registers=cases[-1]["execution"]["result"]["registers"]
        if (number(registers["r0"]),number(registers["r1"]),bool(number(registers["cpsr"])&0x20)) != (
                11,number(obj["arm_pointer"]),False):
            raise ValueError("Native ARM callback did not select mailbox11 and translate the actual message pointer")
    report={"schema":1,"time_utc":datetime.now(timezone.utc).isoformat(),
            "scope":"Captured MN103 requests read into native ARM objects and dispatched to their real callback; stops before ARM kernel mailbox posting",
            "passed":len(cases),"cases":cases,"source_mn103_state":str(state),
            "source_ram_sha256":sha(source_ram),"source_ring_sha256":sha(source_rings),
            "arm_service_id":hex(identifier),"native_callback":hex(callback),"native_objects":objects,
            "native_message_headers_or_payloads_written_by_fixture":False,
            "native_ring_head_or_tail_written_by_fixture":False,
            "interrupt_delivery_or_peer_acknowledgements_supplied":False,
            "kernel_mailbox_post_executed":False,"complete_cross_processor_ui_flow":False,
            "camera_contacted":False,"driver_sha256":sha((output/"driver-source.py").read_bytes()),
            "limits":["Direct bounded prefix/function entries use fresh caller frames and explicit ordinary storage.",
                      "ARM registration is tested through the native low-level API; its outer kernel synchronization wrapper has not run.",
                      "Registration and receiver stages stop before unmodeled notification/local interrupt-controller instructions.",
                      "Native callback reaches ARM-mode0x1d3c04 with mailbox11 and the translated pointer, but the ARM kernel/worker/reply path is not initialized."]}
    save_json(output/"summary.json",report)
    print(json.dumps({"passed":len(cases),"kernel_mailbox_post_executed":False}),flush=True)
    return report


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True);parser.add_argument("--state",type=Path,default=STATE)
    args=parser.parse_args();probe(args.out,args.state)


if __name__=="__main__":main()
