"""Guided preparation state, with camera writes available only after a build."""
from __future__ import annotations

from datetime import datetime,timezone
import json
import os
from pathlib import Path
import tempfile

from .camera import inspect_camera,enable_update
from .codec import Codec
from .download import download,load_local,sha
from .firmware import build,catalog
from .usb import Transport


class Workflow:
    def __init__(self,*,assets=None,transport_factory=Transport,codec_factory=Codec):
        self.assets=assets;self.transport_factory=transport_factory;self.codec_factory=codec_factory
        self.inspection=None;self.output=None;self.manifest=None;self.enabled=False

    def inspect(self,progress=lambda *_:None):
        self.inspection=None;self.output=None;self.manifest=None;self.enabled=False
        inspection=inspect_camera(self.transport_factory,progress)
        self.inspection=inspection;self.output=None;self.manifest=None;self.enabled=False
        return inspection.report()

    def prepare(self,choice,destination,*,local_firmware=None,progress=lambda *_:None):
        if self.inspection is None:raise ValueError('Read the connected camera first')
        # Invalidate old readiness before any attempted replacement build.
        self.output=None;self.manifest=None;self.enabled=False
        raw=load_local(local_firmware) if local_firmware else download(
            lambda done,total:progress('Downloading official firmware',done,total))
        codec=self.codec_factory()
        candidate,report=build(raw,self.inspection.key,codec,choice,assets=self.assets,progress=progress,
            camera_profile=self.inspection.profile)
        restore,restore_report=(candidate,report) if choice=='restore' else build(
            raw,self.inspection.key,codec,'restore',assets=self.assets,progress=progress,
            camera_profile=self.inspection.profile)
        root=Path(destination).expanduser().absolute()
        if root.exists():raise FileExistsError('Choose a new folder for the prepared firmware')
        root.parent.mkdir(parents=True,exist_ok=True)
        # Publish the complete folder only after both firmware files and all
        # instructions are saved. A failed save must not leave a plausible
        # update file in the user-selected destination.
        with tempfile.TemporaryDirectory(prefix='.'+root.name+'-',dir=root.parent) as staging:
            pending=Path(staging)
            for name,data in (('GM5__V11.bin',candidate),('stock-restore/GM5__V11.bin',restore)):
                path=pending/name;path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('xb') as stream:stream.write(data)
                if sha(path.read_bytes())!=sha(data):raise ValueError('The saved firmware file failed verification')
            manifest=dict(schema=1,time_utc=datetime.now(timezone.utc).isoformat(),
                camera=self.inspection.report(),candidate=report,stock_restore=restore_report,
                temporary_flag_needed=self.inspection.rom_policy==1,
                automatic_camera_flash=False,sd_card_written=False)
            (pending/'preparation.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
            (pending/'SHA256SUMS').write_text(report['sha256']+'  GM5__V11.bin\n'+restore_report['sha256']+
                '  stock-restore/GM5__V11.bin\n',encoding='utf-8')
            (pending/'NEXT-STEPS.txt').write_text(self.instructions(manifest),encoding='utf-8')
            if root.exists():raise FileExistsError('The destination folder appeared during preparation')
            os.rename(pending,root)
        self.output=root;self.manifest=manifest
        return manifest

    @staticmethod
    def instructions(manifest):
        text=('1. Copy GM5__V11.bin to the root of a camera-formatted SD card.\n'
            '2. Select Standard, switch the camera OFF, then insert the card.\n'
            '3. Use a fully charged battery.\n')
        if manifest['temporary_flag_needed']:
            text+=('4. Start the GM5 in service mode and reconnect USB. In the updater, choose Enable this update.\n'
                '5. After verification, unplug USB without switching off or letting the camera sleep.\n'
                '6. Press Playback and confirm the update on the camera. Keep power stable until it finishes.\n')
        else:
            text+=('4. Turn the camera on normally. USB is not required for this update.\n'
                '5. Press Playback and confirm the update on the camera. Keep power stable until it finishes.\n')
        text+='\nAfter restart, check the selected patches.\n\nLimitations:\n'
        return text+''.join('- '+item+'\n' for item in manifest['candidate']['limitations'])

    def verify_output(self):
        if self.inspection is None or self.output is None or self.manifest is None:
            raise ValueError('Prepare and save a verified firmware build first')
        path=self.output/'GM5__V11.bin'
        if not path.is_file() or sha(path.read_bytes())!=self.manifest['candidate']['sha256']:
            raise ValueError('The prepared update file changed or is missing. Build it again.')
        return path

    def enable(self,*,card_inserted_with_power_off,progress=lambda *_:None):
        self.verify_output()
        if not card_inserted_with_power_off:
            raise ValueError('Insert the prepared card with the GM5 switched off, then reconnect service USB')
        result=enable_update(self.inspection,self.transport_factory,progress)
        self.enabled=True
        return result
