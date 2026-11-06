#!/usr/bin/env python3
"""Check and publish the bounded native ARM receiver/callback experiment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import struct

from gm5_arm_emulator import ARM_IMAGE, ARM_SHA
from gm5_cooperative_evidence import checked_arm
from gm5_emulator import number, sha
from gm5_prompt_package import artifact
from gm5_reflash_control import save_json


RUN = Path("work/gm5-arm-native-ipc-1")


def collect(output: Path, release: Path) -> dict:
    if output.exists() or release.exists(): raise ValueError("IPC evidence/release already exists")
    report=json.loads((RUN/"summary.json").read_text())
    if (report["passed"]!=8 or len(report["cases"])!=8 or report["camera_contacted"]
            or report["kernel_mailbox_post_executed"] or report["complete_cross_processor_ui_flow"]
            or report["interrupt_delivery_or_peer_acknowledgements_supplied"]):
        raise ValueError("Native IPC experiment is incomplete or claims unexecuted work")
    if sha((RUN/"driver-source.py").read_bytes())!=report["driver_sha256"] or sha(ARM_IMAGE.read_bytes())!=ARM_SHA:
        raise ValueError("Native IPC source changed")
    state=Path(report["source_mn103_state"])
    for filename,key in (("ram.data","source_ram_sha256"),("service-notification.data","source_ring_sha256")):
        if sha((state/filename).read_bytes())!=report[key]:raise ValueError("Native MN103 input snapshot changed")
    cases=[]
    core=Path("work/gm5-cooperative-arm-release-1/arm-adapter.py")
    for case in report["cases"]:
        directory=Path(case["directory"])
        checked=checked_arm(directory,case["execution"])
        if checked["driver_sha256"]!=sha(core.read_bytes()):
            raise ValueError("IPC experiment used a different ARM core adapter from the105-test milestone")
        spec=json.loads((directory/"scenario.json").read_text())
        if spec["memory"] or checked["result"]["stop"]!="reviewed_native_boundary":
            raise ValueError("IPC experiment includes direct memory writes or an unexpected native boundary")
        checked["name"]=case["name"]
        checked["dumps"]=case["execution"]["dumps"]
        cases.append(checked)
    by_name={case["name"]:case for case in cases}
    ring_heads=[]
    for name,expected in (("native_arm_first_ring_message_before_local_irq",12),
                          ("native_arm_second_ring_message_before_local_irq",24)):
        directory=Path(by_name[name]["directory"])
        ring=(directory/"shared-ring.data").read_bytes()
        if struct.unpack_from("<IHH",ring,0x110)!=(768,expected,24):
            raise ValueError("Native ARM ring head/tail differs")
        ring_heads.append(expected)
    for index,obj in enumerate(report["native_objects"]):
        final=by_name[f"native_arm_message{index}_before_kernel_mailbox"]["result"]
        if (number(final["pc"]),number(final["registers"]["r0"]),number(final["registers"]["r1"]),
                bool(number(final["registers"]["cpsr"])&0x20)) != (0x1D3C04,11,number(obj["arm_pointer"]),False):
            raise ValueError("Native ARM callback kernel-call operands differ")
    release.mkdir(mode=0o700)
    retained=[]
    for source,name in ((RUN/"driver-source.py","ipc-probe.py"),(Path(__file__),"evidence-collector.py")):
        target=release/name;shutil.copyfile(source,target);retained.append(artifact(target))
    result={"schema":1,"time_utc":datetime.now(timezone.utc).isoformat(),"scope":report["scope"],
            "native_bounded_controls_passed":8,"native_instructions_started":sum(c["result"]["instructions_started"]for c in cases),
            "camera_contacted":False,"input_is_mn103_emulation_snapshot_not_physical_ram_dump":True,
            "backend_milestone_evidence":artifact(Path("evidence/gm5-cooperative-arm-extension.json")),
            "native_run_summary":artifact(RUN/"summary.json"),"retained_release":retained,
            "native_cases":cases,"native_objects":report["native_objects"],"native_callback":"0xbb8d",
            "native_ring_heads":[0]+ring_heads,"native_ring_tail":24,
            "source_ram_sha256":report["source_ram_sha256"],"source_ring_sha256":report["source_ring_sha256"],
            "message_data_and_ring_offsets_written_by_fixture":False,
            "interrupts_mailbox_posts_or_acknowledgements_supplied":False,
            "unresolved_boundary":{"native_pc":"0x1d3c04","instruction_set":"ARM","kernel_object_id":11,
                                   "interpretation":"Mailbox-send interface, inferred from the paired native receiving/sending call signatures; kernel body not yet executed in this experiment."},
            "complete_cross_processor_ui_flow":False,"physical_region_patch_installed":False,"limits":report["limits"]}
    save_json(output,result);return result


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True);parser.add_argument("--release",type=Path,required=True)
    args=parser.parse_args();report=collect(args.out,args.release)
    print(json.dumps({"passed":report["native_bounded_controls_passed"],"native_instructions_started":report["native_instructions_started"]}),flush=True)


if __name__=="__main__":main()
