#!/usr/bin/env python3
"""Exercise the real updater with private GM5 pages and an explicit fake USB peer.

No USB context/device is opened. Firmware/codec/catalog/output operations are
real; camera-memory replies and disconnect/fault inputs are supplied fixtures.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from apps.lumix_updater.camera import (GUARDS, MODE, PAGES, POLICY_RAM, POLICY_ROM,
                                      PROFILE_NAMES, CameraError, enable_update, inspect_camera)
from apps.lumix_updater.download import sha
from apps.lumix_updater.codec import Codec
from apps.lumix_updater.protocol import ProtocolError
from apps.lumix_updater.workflow import Workflow

PRIVATE=Path('work/updater-private-inputs')
FACTORY=Path('captures/gm5-program-readback-f61hhqc_/result/program-main.bin')
FACTORY_SHA='c918553771018e171605ecb1f177a4d64bc94b221fe5304b8ff419f4509d208d'
OFFICIAL=Path('firmware/official-gm5-v11/GM5__V11.bin')
OFFICIAL_MAIN=PRIVATE/'lumix-updater-input-review-1/program.bin'
OFFICIAL_MAIN_SHA='e6ce3a0764fd56e0f255d4412d30b1f9f73b5282b333c0fe80f16dc11833078c'
EXPECTED_OUTPUTS={
    'stable':'a36ea2847198ac99e58449e3b64604062e106541f0b38aac9f96987a9655b196',
    'luts':'fa17315ef8527dfad4bd72444caac786fe0a2e96d85e4802e26c68995989597d',
    'restore':'21ec8efba8cc5f25d703d77855da959f59de980d23ff04e4ee3d70053b17059e'}
OFFICIAL_RESTORE_SHA='9edf5b03aa4bb2b02ad25ae4702a65dceba94770d7f8b424783775050d9fd15e'


class FixtureCamera:
    """Memory-framing peer, not an emulator of real USB or camera execution."""
    def __init__(self,main,*,rom=1,ram=1):
        self.main=bytearray(main);struct.pack_into('<H',self.main,0x6B1BDC,rom)
        self.pages={at:bytearray(self.main[at-0x40000000:at-0x40000000+1024])
                    for at in GUARDS}
        self.pages[MODE]=bytearray(1024)
        self.pages[POLICY_RAM]=bytearray((i*17+23)&255 for i in range(1024))
        struct.pack_into('<H',self.pages[POLICY_RAM],0x90,ram)
        self.identity=dict(model='DMC-GM5',serial='offline-framing-fixture',usb_release=0x100)
        self.reads=[];self.writes=[];self.opens=0;self.fault=None;self.after_read=None
        self.post_write=None

    def __call__(self):
        peer=self
        class Connection:
            @property
            def identity(self):return peer.identity
            def __enter__(self):peer.opens+=1;return self
            def __exit__(self,*_):pass
            def exchange(self,request,kind,size):return peer.exchange(request,kind,size)
        return Connection()

    def exchange(self,request,kind,size):
        if request[-1]!=0 or request[-2]!=(sum(request[1:-2])&255):
            raise AssertionError('Application sent invalid wire checksum')
        if kind==1:
            if len(request)!=1030 or size!=1030 or request[:4]!=bytes.fromhex('0100ff5c'):
                raise AssertionError('Unreviewed read packet geometry')
            begin,end=struct.unpack_from('<2I',request,4)
            if begin not in PAGES or end!=begin+1024:raise AssertionError('Read escaped fixed camera profile')
            self.reads.append(begin)
            if self.after_read:self.after_read(self,begin)
            payload=bytes(self.pages[begin])
            reply=bytearray(bytes.fromhex('0100ff05')+payload+bytes(2))
            reply[-2]=sum(reply[1:-2])&255
            if self.fault=='echo':
                reply[4:-2]=request[4:-2];reply[-2]=sum(reply[1:-2])&255
            elif self.fault=='checksum':reply[-2]^=1
            elif self.fault=='short':reply=reply[:-1]
            return bytes(reply)
        if kind!=8 or size!=16 or len(request)!=16 or request[:4]!=bytes.fromhex('0800ff9c'):
            raise AssertionError('Unreviewed write packet geometry')
        address,value=struct.unpack_from('<IH',request,4)
        if (address,value)!=(0x70A68490,0) or any(request[10:14]):
            raise AssertionError('Application attempted a different camera write')
        self.writes.append(request.hex());self.pages[POLICY_RAM][0x90:0x92]=bytes(2)
        if self.post_write:self.post_write(self)
        ack=bytearray(bytes.fromhex('0800ff01')+bytes(12));ack[-2]=sum(ack[1:-2])&255
        return bytes(ack)


def proof(output,assets,*,factory=FACTORY,official=OFFICIAL,codec_library=None,
          official_main=OFFICIAL_MAIN,profile='gm5-factory-0111'):
    if profile not in PROFILE_NAMES.values():raise ValueError('Unknown fixture profile')
    factory_data=factory.read_bytes();official_data=official_main.read_bytes()
    if sha(factory_data)!=FACTORY_SHA or sha(official_data)!=OFFICIAL_MAIN_SHA:
        raise ValueError('Pinned firmware fixture changed')
    main=official_data if profile=='gm5-official-0110' else factory_data
    other=factory_data if profile=='gm5-official-0110' else official_data
    expected_outputs=dict(EXPECTED_OUTPUTS)
    if profile=='gm5-official-0110':
        expected_outputs['restore']=OFFICIAL_RESTORE_SHA
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    (output/'driver-source.py').write_bytes(Path(__file__).read_bytes())
    records=[]
    for rom,ram in ((1,1),(1,0),(0,0)):
        camera=FixtureCamera(main,rom=rom,ram=ram)
        before=bytes(camera.pages[POLICY_RAM]);rom_before=bytes(camera.pages[POLICY_ROM])
        found=inspect_camera(camera)
        if found.profile!=profile:raise ValueError('Camera was assigned the wrong firmware profile')
        if camera.writes:raise ValueError('Read-only inspection sent a write')
        result=enable_update(found,camera)
        expected=bytearray(before)
        if rom==1 and ram==1:expected[0x90:0x92]=bytes(2)
        if (camera.pages[POLICY_RAM]!=expected or bytes(camera.pages[POLICY_ROM])!=rom_before
                or len(camera.writes)!=(1 if rom==ram==1 else 0)):
            raise ValueError('Fixed policy operation touched unintended memory')
        records.append(dict(name=f'policy_rom{rom}_ram{ram}',passed=True,
            wrote_ram=result['wrote_ram'],reads=len(camera.reads),wire_writes=camera.writes))

    def refuse(name,change,*,after_inspection=False,after_store=False):
        camera=FixtureCamera(main);previous=inspect_camera(camera) if after_inspection else None
        change(camera)
        try:
            if after_inspection:enable_update(previous,camera)
            else:inspect_camera(camera)
        except (CameraError,ProtocolError) as error:
            if len(camera.writes)!=(1 if after_store else 0):
                raise ValueError('Refusal sent an unexpected write: '+name)
            records.append(dict(name=name,passed=True,refused=str(error),
                reads=len(camera.reads),wire_writes=camera.writes))
        else:raise ValueError('Application accepted the fault input: '+name)

    refuse('other_model',lambda c:c.identity.update(model='DC-GX7MK3'))
    refuse('changed_camera_identity',lambda c:c.identity.update(serial='different-camera'),after_inspection=True)
    refuse('unknown_rom_policy',lambda c:struct.pack_into('<H',c.pages[POLICY_ROM],0x3DC,2))
    refuse('unknown_ram_policy',lambda c:struct.pack_into('<H',c.pages[POLICY_RAM],0x90,2))
    refuse('modified_rom_with_stock_ram_gate',
        lambda c:struct.pack_into('<H',c.pages[POLICY_ROM],0x3DC,0))
    refuse('indirect_service_mode',lambda c:c.pages[MODE].__setitem__(0x5D,1))
    refuse('unknown_internal_revision',lambda c:struct.pack_into('<2H',c.pages[0x40000400],0x2A0,0x112,0x112))
    refuse('mismatched_revision_words',lambda c:struct.pack_into('<H',c.pages[0x40000400],0x2A0,0x112))
    def switch_profile(camera):
        for address in GUARDS:
            camera.pages[address]=bytearray(other[address-0x40000000:address-0x40000000+1024])
        struct.pack_into('<H',camera.pages[POLICY_ROM],0x3DC,1)
    refuse('different_reviewed_build_after_prepare',switch_profile,after_inspection=True)
    refuse('mixed_reviewed_header_and_program',lambda c:c.pages.__setitem__(0x40000400,
        bytearray(other[0x400:0x800])))
    for address in GUARDS:
        refuse('changed_code_'+hex(address),lambda c,at=address:c.pages[at].__setitem__(16,c.pages[at][16]^1))
    for fault in ('short','checksum','echo'):
        refuse('invalid_reply_'+fault,lambda c,f=fault:setattr(c,'fault',f))
    def change_mode_before_store(camera):
        count=[0]
        def update(peer,address):
            if address==MODE:
                count[0]+=1
                if count[0]==2:peer.pages[MODE][0x5D]=1
        camera.after_read=update
    refuse('mode_changed_just_before_store',change_mode_before_store,after_inspection=True)
    def change_ram_before_store(camera):
        count=[0]
        def update(peer,address):
            if address==POLICY_RAM:
                count[0]+=1
                if count[0]==2:peer.pages[POLICY_RAM][0x90:0x92]=bytes(2)
        camera.after_read=update
    refuse('ram_changed_just_before_store',change_ram_before_store,after_inspection=True)
    refuse('adjacent_ram_byte_changed_after_store',lambda c:setattr(c,'post_write',
        lambda peer:peer.pages[POLICY_RAM].__setitem__(0x92,peer.pages[POLICY_RAM][0x92]^1)),
        after_inspection=True,after_store=True)
    refuse('rom_changed_after_store',lambda c:setattr(c,'post_write',
        lambda peer:peer.pages[POLICY_ROM].__setitem__(10,peer.pages[POLICY_ROM][10]^1)),
        after_inspection=True,after_store=True)

    outputs=[]
    for choice,rom in (('stable',1),('luts',0),('restore',0)):
        camera=FixtureCamera(main,rom=rom,ram=rom)
        workflow=Workflow(assets=assets,transport_factory=camera,codec_factory=lambda:Codec(codec_library))
        workflow.inspect()
        report=workflow.prepare(choice,output/choice,
            local_firmware=official,
            progress=lambda label,*_:print(choice,label,flush=True))
        if camera.writes:raise ValueError('Preparation wrote to the camera fixture')
        if (sha(workflow.verify_output().read_bytes())!=expected_outputs[choice]
                or sha((workflow.output/'stock-restore/GM5__V11.bin').read_bytes())!=expected_outputs['restore']):
            raise ValueError('Application prepared a different reviewed firmware or stock restore')
        try:workflow.enable(card_inserted_with_power_off=False)
        except ValueError:pass
        else:raise ValueError('Workflow accepted missing card preparation')
        if camera.writes:raise ValueError('Missing card confirmation still wrote RAM')
        enabled=workflow.enable(card_inserted_with_power_off=True)
        if enabled['wrote_ram']!=(rom==1):raise ValueError('Workflow selected the wrong USB bootstrap path')
        outputs.append(dict(choice=choice,sha256=report['candidate']['sha256'],
            prepared_restore_sha256=report['stock_restore']['sha256'],
            preparation_read_only=True,explicit_enable=enabled))
        if workflow.inspection.key.hex() in (output/choice/'preparation.json').read_text():
            raise ValueError('Camera-derived key included in preparation report')
    result=dict(time_utc=datetime.now(timezone.utc).isoformat(),passed=True,
        profile=profile,
        framing_and_profile_controls=records,complete_workflows=outputs,
        app_source_sha256={p.name:sha(p.read_bytes()) for p in Path('apps/lumix_updater').glob('*.py')},
        official_input_sha256=sha(official.read_bytes()),
        camera_input_sha256=sha(main),
        native_codec_sha256=sha(Path(Codec(codec_library).library._name).read_bytes()),
        platform=sys.platform,
        camera_replies_are_explicit_fixtures=True,real_codec_and_output_files=True,
        actual_usb_driver_or_camera_execution_verified=False,camera_contacted=False)
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--factory',type=Path,default=FACTORY)
    parser.add_argument('--official',type=Path,default=OFFICIAL)
    parser.add_argument('--codec-library',type=Path)
    parser.add_argument('--official-main',type=Path,default=OFFICIAL_MAIN)
    parser.add_argument('--profile',choices=tuple(PROFILE_NAMES.values()),default='gm5-factory-0111')
    args=parser.parse_args();result=proof(args.out,args.assets,factory=args.factory,
        official=args.official,codec_library=args.codec_library,official_main=args.official_main,
        profile=args.profile)
    print(json.dumps(dict(passed=True,profile_controls=len(result['framing_and_profile_controls']),
        workflows=len(result['complete_workflows']),camera_contacted=False)))
