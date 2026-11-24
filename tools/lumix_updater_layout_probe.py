#!/usr/bin/env python3
"""Offline compatibility controls over real, privately retained firmware.

Only a declared wire-page peer is used. No USB handle or firmware execution is
supplied by this probe. Its deliberate mutations test host acceptance/refusal.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.lumix_updater import camera
from apps.lumix_updater.layout import CODE, COPY, POLICY_JOB, TABLE
from apps.lumix_updater.models import model_spec
from apps.lumix_updater.protocol import checksum, policy_packet


class Peer:
    def __init__(self, model, main, secondary):
        self.model = model
        self.spec = model_spec(model)
        self.identity = dict(model=model, serial='explicit-offline-layout-peer', usb_release=0x100)
        self.allowed = camera.profile_pages(model) | camera.profile_pages(model, layout_only=True)
        self.pages = {}
        self.reads = []
        self.writes = []
        self.after_write = None
        for at in self.allowed:
            source, base = (secondary, 0x41400000) if 0x41400000 <= at < 0x41760000 else (main, 0x40000000)
            if at < 0x70000000:
                self.pages[at] = bytearray(source[at-base:at-base+1024])
                if len(self.pages[at]) != 1024:
                    raise ValueError('Missing private firmware input')
        self.pages[self.spec['mode']] = bytearray(1024)
        self.pages[self.spec['policy_ram']] = bytearray((i*17+23)&255 for i in range(1024))
        self.put(self.spec['policy_rom']+self.spec['policy_rom_offset'], b'\x01\0')
        self.put(self.spec['policy_ram']+self.spec['policy_ram_offset'], b'\x01\0')

    def __call__(self): return self
    def __enter__(self): return self
    def __exit__(self, *_): pass

    def put(self, at, raw):
        page = at & ~1023
        self.pages[page][at-page:at-page+len(raw)] = raw

    def flip(self, at):
        self.pages[at & ~1023][at & 1023] ^= 1

    def exchange(self, request, kind, size):
        if request[-1] or request[-2] != checksum(request):
            raise AssertionError('Invalid request frame')
        if kind == 1:
            at, end = struct.unpack_from('<II', request, 4)
            if (size != 1030 or len(request) != 1030 or request[:4] != bytes.fromhex('0100ff5c')
                    or at not in self.allowed or end != at+1024):
                raise AssertionError('Read escaped the declared page fixture')
            self.reads.append(at)
            reply = bytearray(bytes.fromhex('0100ff05')+self.pages[at]+bytes(2))
        else:
            if (kind, size) != (8, 16) or request != policy_packet(0, self.model):
                raise AssertionError('Write escaped the one fixed policy halfword')
            self.writes.append(request)
            self.put(self.spec['policy_ram']+self.spec['policy_ram_offset'], bytes(2))
            if self.after_write:
                self.after_write(self)
            reply = bytearray(bytes.fromhex('0800ff01')+bytes(12))
        reply[-2] = checksum(reply)
        return bytes(reply)


def verify(output, references):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output/'probe-source.py').write_bytes(Path(__file__).read_bytes())
    references = json.loads(references.read_text())
    cases = []
    for entry in references:
        model = entry['model']
        main = Path(entry['main_path']).read_bytes()
        secondary = Path(entry['secondary_path']).read_bytes()
        for raw, key in ((main, 'main_sha256'), (secondary, 'secondary_sha256')):
            if hashlib.sha256(raw).hexdigest() != entry[key]:
                raise ValueError('Private reference bytes changed')
        spec = model_spec(model)

        def peer(): return Peer(model, main, secondary)

        def accepted(name, change=lambda _: None, *, skip=True):
            p = peer()
            change(p)
            result = camera.inspect_camera(p, skip_revision_check=skip)
            if p.writes or result.revision_check_skipped != skip:
                raise AssertionError('Inspection wrote or lost the requested verification mode')
            before = bytes(p.pages[spec['policy_ram']])
            camera.enable_update(result, p)
            wanted = bytearray(before)
            wanted[spec['policy_ram_offset']:spec['policy_ram_offset']+2] = bytes(2)
            if len(p.writes) != 1 or p.pages[spec['policy_ram']] != wanted:
                raise AssertionError('The fixed write changed neighboring data')
            cases.append(dict(model=model, revision=entry['revision'], name=name, accepted=True,
                fixed_write_and_full_page_readback_verified=True, report=result.report()))
            return result

        def refused(name, change, *, skip=True, before_enable=False, after_write=False):
            p = peer()
            previous = camera.inspect_camera(p, skip_revision_check=skip) if before_enable else None
            if after_write:
                p.after_write = change
            else:
                change(p)
            try:
                if before_enable: camera.enable_update(previous, p)
                else: camera.inspect_camera(p, skip_revision_check=skip)
            except camera.CameraError as error:
                message = str(error)
            else:
                raise AssertionError('An incompatible input was accepted: '+name)
            if len(p.writes) != int(after_write):
                raise AssertionError('Unexpected write for refusal: '+name)
            cases.append(dict(model=model, revision=entry['revision'], name=name, accepted=False,
                error=message, fixed_writes=len(p.writes)))

        accepted('unchanged_exact_build', skip=False)
        accepted('unchanged_layout_override')
        changed_version = lambda p: p.put(0x400006A0, struct.pack('<2H', 0x111 if model == 'DMC-GM1' else 0x112, 0x111 if model == 'DMC-GM1' else 0x112))
        accepted('unlisted_revision_and_other_header_metadata', lambda p: (changed_version(p), p.flip(0x400006A4)))
        accepted('different_revision_halfwords', lambda p: p.put(0x400006A0, struct.pack('<2H', 0x111, 0x112)))
        refused('unlisted_revision_without_override', changed_version, skip=False)
        refused('known_revision_metadata_without_override', lambda p: p.flip(0x400006A4), skip=False)
        for page in sorted(camera.profile_pages(model, layout_only=True)):
            if page in (spec['mode'], spec['policy_ram']): continue
            accepted('unrelated_page_byte_'+hex(page), lambda p, at=page+(0x200 if page == COPY else 0): p.flip(at))
        accepted('initializer_extent_changed_without_moving_policy', lambda p: p.put(COPY+8,
            struct.pack('<I', struct.unpack_from('<I', p.pages[COPY], 8)[0]+4)))
        for name, at, size, _ in CODE[model]:
            refused('changed_'+name, lambda p, a=at: p.flip(a))
        for op in (0x5C, 0x9C):
            refused('moved_dispatch_'+hex(op), lambda p, a=TABLE[model]+4*op: p.flip(a))
        refused('moved_policy_RAM_mapping', lambda p: p.flip(COPY+18))
        refused('policy_outside_initializer_copy', lambda p: p.put(COPY+8,
            struct.pack('<I', spec['policy_rom'])))
        refused('changed_initializer_loop', lambda p: p.flip(COPY+0x17))
        start, end, *_ = POLICY_JOB[model]
        def change_consumer(p):
            for at in range(start, end): p.put(at, b'\0')
        refused('missing_policy_consumer', change_consumer)
        refused('key_record_moved_or_changed', lambda p: p.flip(spec['key_page']+spec['key_offset']))
        refused('nonabsolute_write_mode', lambda p: p.put(spec['mode']+spec['mode_offset'], b'\x01'))
        refused('invalid_ROM_policy_neighbor', lambda p: p.put(spec['policy_rom']+spec['policy_rom_offset']+1, b'\x01'))
        refused('invalid_RAM_policy_neighbor', lambda p: p.put(spec['policy_ram']+spec['policy_ram_offset']+1, b'\x01'))
        refused('layout_moved_after_preparation', lambda p: p.flip(CODE[model][4][1]), before_enable=True)
        refused('revision_changed_after_preparation', lambda p: p.flip(0x400006A2), before_enable=True)
        refused('ROM_changed_during_RAM_write', lambda p: p.flip(spec['policy_rom']), before_enable=True, after_write=True)
        if model == 'DMC-GM5' and entry['revision'] == '0x111':
            with patch.object(camera, 'PROFILE_GUARDS', {0x110: camera.OFFICIAL_GUARDS}):
                accepted('factory_0111_without_its_exact_build_profile')
    report = dict(schema=1, time_utc=datetime.now(timezone.utc).isoformat(), passed=True,
        cases=cases, case_count=len(cases), real_private_firmware_profiles=len(references),
        camera_contacted=False, native_firmware_execution=False,
        scope='Host compatibility checks, wire framing, refusal before writes, fixed RAM write and readback over explicit offline page peers')
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(passed=True, cases=len(cases), camera_contacted=False)))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verify(args.out, args.references)
