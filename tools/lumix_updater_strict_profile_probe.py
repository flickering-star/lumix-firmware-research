#!/usr/bin/env python3
"""Check exact profile acceptance and refusal after removal of revision skips."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.lumix_updater import camera
from apps.lumix_updater.models import model_spec
from lumix_updater_layout_probe import Peer


def sha(raw): return hashlib.sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--references',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(mode=0o700,parents=True,exist_ok=False)
    cases=[]
    for entry in json.loads(args.references.read_text()):
        model=entry['model'];a=Path(entry['main_path']).read_bytes();b=Path(entry['secondary_path']).read_bytes()
        if sha(a)!=entry['main_sha256'] or sha(b)!=entry['secondary_sha256']:raise ValueError('Original input changed')
        for case in ('exact','unlisted-revision','mixed-header','changed-code','changed-after-read','skip-parameter'):
            peer=Peer(model,a,b);message=None
            if case=='exact':
                inspected=camera.inspect_camera(peer);camera.enable_update(inspected,peer)
                assert len(peer.writes)==1 and inspected.profile==model_spec(model)['profiles'][inspected.version]
            else:
                previous=camera.inspect_camera(peer) if case=='changed-after-read' else None
                if case in ('unlisted-revision','mixed-header'):
                    revision=0x111 if model=='DMC-GM1' else 0x112
                    peer.put(0x400006a0,struct.pack('<2H',revision,revision if case=='unlisted-revision' else revision+1))
                elif case in ('changed-code','changed-after-read'):peer.flip(sorted(camera.profile_guards(model)[int(entry['revision'],16)])[1]+4)
                try:
                    if case=='skip-parameter':camera.inspect_camera(peer,skip_revision_check=True)
                    elif previous:camera.enable_update(previous,peer)
                    else:camera.inspect_camera(peer)
                except (camera.CameraError,TypeError) as error:message=str(error)
                else:raise AssertionError('Unreviewed input/removed override accepted')
                assert not peer.writes
            cases.append(dict(model=model,reference_revision=entry['revision'],case=case,
                accepted=case=='exact',error=message,camera_writes=len(peer.writes)))
    result=dict(schema=1,time_utc=datetime.now(timezone.utc).isoformat(),passed=True,cases=cases,
        real_firmware_reference_profiles=3,host_cases=len(cases),camera_contacted=False,
        source_sha256={p.name:sha(p.read_bytes()) for p in Path('apps/lumix_updater').glob('*.py')})
    (args.out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(cases),GM5_0111_exact_profile_passes=True)))


if __name__=='__main__':main()
