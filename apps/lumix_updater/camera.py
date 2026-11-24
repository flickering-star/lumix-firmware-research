"""Reviewed GM1/GM5 profiles and their sole model-specific RAM change."""
from __future__ import annotations

from dataclasses import dataclass,field
import hashlib
import struct

from .protocol import Service
from .usb import Transport
from .models import MODELS,model_spec
from .layout import check_layout,layout_pages

MODEL='DMC-GM5'
POLICY_ROM,POLICY_RAM,MODE=0x406B1800,0x70A68400,0x702FF800
KEY_PAGE,KEY_OFFSET=0x4064B400,0xCC
KEY_SHA='8c5c9a63324a7b65ec589672f479961f11523f393d846fab05d8fc66b61b94e5'
GUARDS={
    0x40000400:'49d5fb0f3e4a832b0989c0fd8c619a00fd71bc6d498e024690fe8db210d2d0b0',
    KEY_PAGE:'5d96a700c6dd48cfbd341567df5a1e9e1de8a52ae507fe19cba191e5dd1a31e1',
    0x4061E400:'789c1dd614af1b74b8e68c4eb9262bdc44f193556804f5af6164eb2f6af5a6de',
    0x4036CC00:'7c580db12c5c5fc37afcacb9a0c75929d4164b49c6a03f54f307135e882348d9',
    0x4036E000:'247bdd53e25eb02ccaea710e1b1129b08f3cc71ae388ac08910345bf8ea7a698',
    POLICY_ROM:'6d76a45b6286ec0bb42bef6f24d41fc771d5b463511a327b98846ad1c33d49fc'}
OFFICIAL_GUARDS={
    0x40000400:'ce95bd16a7a64aed41cfce2e297769b6a25e2a8856e4a379ce56b6be73a203df',
    KEY_PAGE:'a254a319ca5095f9eeddee30a0d01ad0e4d5ed21ca4f030bd2ca9981c2a0a863',
    0x4061E400:GUARDS[0x4061E400],
    0x4036CC00:'e4ccd5a94d6a60dd94e9705cb44d7d2524494567ea75cb09f46eb7646c742e07',
    0x4036E000:'a7f326f94f95da08cc7f96f15579bffd07f0587f827c941793ad81e4d594ba55',
    POLICY_ROM:GUARDS[POLICY_ROM]}
PROFILE_GUARDS={0x0110:OFFICIAL_GUARDS,0x0111:GUARDS}
PROFILE_NAMES={0x0110:'gm5-official-0110',0x0111:'gm5-factory-0111'}
PAGES=frozenset(GUARDS)|{POLICY_RAM,MODE}
GM1_GUARDS={
    0x40000400:'a03443c440d607fa2f36fe706688f0a896273ee449c6f6bd197615f96e065423',
    0x405AB400:'ff1483b11bb21194465236afbc19308b7fc6cef72c6019ca1ec9b8c056a1e366',
    0x4057B800:'3ee288991ff95d27dc29566abf25ff65664e716047d4d28b8168c2212870837c',
    0x4036A000:'e8951cfe66681a18fc749a71826237539e264e5972523b42aca12313f322b1e8',
    0x4036B000:'6fd3d81781b08a0ce039e871a4b84287575510f1cc63e95ab68799ea923de86c',
    0x405C5800:'01c5765071c40cb898dca585b99c172520cda42a253a37b404ac545270996b37'}


def profile_guards(model):
    model_spec(model)
    return PROFILE_GUARDS if model=='DMC-GM5' else {0x0110:GM1_GUARDS}


def profile_pages(model,*,layout_only=False):
    spec=model_spec(model)
    rom_pages=(layout_pages(model)|{0x40000400,spec['key_page'],spec['policy_rom']}
        if layout_only else frozenset(next(iter(profile_guards(model).values()))))
    return rom_pages|{spec['policy_ram'],spec['mode']}


def selected_service(transport,*,layout_only=False):
    model=transport.identity.get('model')
    if model not in MODELS:raise CameraError('Only the reviewed DMC-GM1 and DMC-GM5 profiles are supported')
    return Service(transport,profile_pages(model,layout_only=layout_only),model=model)


def updater_transport():
    # USB product identity chooses one of two exact allowlisted profiles.
    # The raw Transport default stays GM5 for existing model-specific tools.
    return Transport(expected_model=None)


class CameraError(ValueError):
    pass


class UnreviewedFirmwareError(CameraError):
    """An exact build was not recognized; a layout-only retry is available."""


class UnsupportedRevisionError(UnreviewedFirmwareError):
    """The revision number is unreviewed; a compatible layout may still work."""


@dataclass(frozen=True)
class Inspection:
    model:str
    serial:str=field(repr=False)
    usb_release:int
    version:int
    rom_policy:int
    ram_policy:int
    key:bytes=field(repr=False)
    reviewed_revision:int|None=None
    version_fields:tuple[int,int]|None=None
    rom_page_sha256:str|None=field(default=None,repr=False)

    @property
    def modified_updates_enabled(self):return self.rom_policy==0

    @property
    def layout_revision(self):
        return self.version if self.reviewed_revision is None else self.reviewed_revision

    @property
    def revision_check_skipped(self):return self.reviewed_revision is not None

    @property
    def revision_words(self):return self.version_fields or (self.version,self.version)

    @property
    def profile(self):return model_spec(self.model)['profiles'][self.layout_revision]

    def report(self):
        return dict(model=self.model,firmware='unreviewed' if self.revision_check_skipped else '1.1',profile=self.profile,
            internal_revision=f'{self.version:04x}',
            reviewed_internal_revision=f'{self.layout_revision:04x}',
            internal_revision_fields=[f'{value:04x}' for value in self.revision_words],
            revision_check_skipped=self.revision_check_skipped,
            rom_policy=self.rom_policy,ram_policy=self.ram_policy,
            modified_updates_enabled=self.modified_updates_enabled,
            encryption_key_recovered=True,profile_guards_verified=not self.revision_check_skipped,
            layout_compatibility_verified=True,
            firmware_verification='layout-compatibility' if self.revision_check_skipped else 'exact-reviewed-build')


def inspect_service(service,identity,progress=lambda *_:None,*,skip_revision_check=False):
    model=identity.get('model')
    if model not in MODELS:raise CameraError('Only the reviewed DMC-GM1 and DMC-GM5 profiles are supported')
    if skip_revision_check:
        return inspect_compatible_service(service,identity,progress)
    spec=model_spec(model)
    versions=profile_guards(model);allowed=profile_pages(model)
    pages={};guards=None;version=None
    for i,address in enumerate(sorted(allowed)):
        progress('Checking camera firmware',i,len(allowed))
        raw=service.read(address)
        if len(raw)!=1024:raise CameraError('Camera memory reply is incomplete')
        pages[address]=raw
        if address==0x40000400:
            version=struct.unpack_from('<2H',raw,0x2A0)
            if version[0]!=version[1] or version[0] not in versions:
                detected=f'0x{version[0]:04x}'
                if version[0]!=version[1]:
                    detected+=f' / 0x{version[1]:04x} (header fields differ)'
                supported=', '.join(f'0x{value:04x}' for value in sorted(versions))
                raise UnsupportedRevisionError('Unsupported '+spec['token']+' firmware revision '+detected+
                    '. Supported internal revisions: '+supported+'. No camera change was made.')
            guards=versions[version[0]]
        if guards is not None and address in guards:
            checked=bytearray(raw)
            if address==spec['policy_rom']:
                offset=spec['policy_rom_offset']
                value=struct.unpack_from('<H',checked,offset)[0]
                if value not in (0,1):raise CameraError('The update policy is not in a reviewed state')
                checked[offset:offset+2]=b'\x01\0'
            if hashlib.sha256(checked).hexdigest()!=guards[address]:
                raise UnreviewedFirmwareError('The firmware build differs from the reviewed '+spec['token']+
                    f' profile (detected internal revision 0x{version[0]:04x}). No camera change was made.')
    return finish_inspection(pages,identity,version)


def inspect_compatible_service(service,identity,progress=lambda *_:None):
    model=identity['model'];pages={};allowed=profile_pages(model,layout_only=True)
    for i,address in enumerate(sorted(allowed)):
        progress('Checking camera layout compatibility',i,len(allowed))
        pages[address]=service.read(address)
        if len(pages[address])!=1024:raise CameraError('Camera memory reply is incomplete')
    try:check_layout(model,pages)
    except ValueError as error:raise CameraError(str(error)) from error
    version=struct.unpack_from('<2H',pages[0x40000400],0x2A0)
    # This chooses the reviewed firmware used to PREPARE an update/restore.
    # It does not identify the installed build from arbitrary header metadata.
    versions=profile_guards(model)
    reference=version[0] if version[0] in versions else min(versions)
    return finish_inspection(pages,identity,version,reference)


def finish_inspection(pages,identity,version,reviewed_revision=None):
    model=identity['model'];spec=model_spec(model)
    key=pages[spec['key_page']][spec['key_offset']:spec['key_offset']+16]
    if hashlib.sha256(key).hexdigest()!=spec['key_sha']:raise CameraError('The firmware encryption-key record differs')
    rom=struct.unpack_from('<H',pages[spec['policy_rom']],spec['policy_rom_offset'])[0]
    if rom not in (0,1):raise CameraError('The update policy is not in a supported state')
    ram=struct.unpack_from('<H',pages[spec['policy_ram']],spec['policy_ram_offset'])[0]
    if ram not in (0,1):raise CameraError('The temporary update policy is not in a reviewed state')
    if rom==0 and ram!=0:
        raise CameraError('The current update state differs from the installed patch. '
            'Switch the camera off normally, reconnect in service mode and read it again.')
    if pages[spec['mode']][spec['mode_offset']]!=0:raise CameraError('Reconnect the camera in the standard service USB state')
    return Inspection(model,identity.get('serial',''),identity.get('usb_release',0),version[0],rom,ram,key,
        reviewed_revision=reviewed_revision,version_fields=version,
        rom_page_sha256=hashlib.sha256(pages[spec['policy_rom']]).hexdigest())


def inspect_camera(transport_factory=None,progress=lambda *_:None,*,skip_revision_check=False):
    with (transport_factory or updater_transport)() as transport:
        return inspect_service(selected_service(transport,layout_only=skip_revision_check),transport.identity,progress,
                               skip_revision_check=skip_revision_check)


def enable_update(previous,transport_factory=None,progress=lambda *_:None):
    """Repeat the selected build/layout check before the one fixed RAM write."""
    with (transport_factory or updater_transport)() as transport:
        if transport.identity.get('model')!=previous.model:
            raise CameraError('The connected camera model changed after preparation. Read it again.')
        service=selected_service(transport,layout_only=previous.revision_check_skipped);spec=model_spec(previous.model)
        current=inspect_service(service,transport.identity,progress,
                                skip_revision_check=previous.revision_check_skipped)
        if (previous.serial and current.serial!=previous.serial or current.key!=previous.key
                or current.revision_words!=previous.revision_words or current.usb_release!=previous.usb_release
                or current.rom_policy!=previous.rom_policy or current.reviewed_revision!=previous.reviewed_revision):
            raise CameraError('The camera changed after preparation. Read it again before continuing.')
        if current.rom_policy==0 or current.ram_policy==0:
            return dict(wrote_ram=False,already_enabled=True,rom_policy=current.rom_policy)
        # Recheck the addressing mode immediately before the single store.
        if service.read(spec['mode'])[spec['mode_offset']]!=0:raise CameraError('Camera service state changed; no write sent')
        page=service.read(spec['policy_ram']);offset=spec['policy_ram_offset']
        if struct.unpack_from('<H',page,offset)[0]!=1:raise CameraError('Camera policy changed; read the camera again')
        service.set_policy(0)
        wanted=bytearray(page);wanted[offset:offset+2]=bytes(2)
        if service.read(spec['policy_ram'])!=wanted:
            raise CameraError('The temporary flag write could not be verified. Reconnect and read the camera before proceeding.')
        page_for_rom(current,service)
        return dict(wrote_ram=True,already_enabled=False,rom_policy=1,ram_policy=0,
            complete_ram_page_readback_verified=True)


def page_for_rom(current,service):
    # Independent post-write ROM validation; the host never sends NOR writes.
    spec=model_spec(current.model);offset=spec['policy_rom_offset']
    raw=service.read(spec['policy_rom']);checked=bytearray(raw)
    if struct.unpack_from('<H',raw,offset)[0]!=current.rom_policy:
        raise CameraError('The ROM update policy changed unexpectedly')
    if current.revision_check_skipped:
        if current.rom_page_sha256 is None or hashlib.sha256(raw).hexdigest()!=current.rom_page_sha256:
            raise CameraError('The ROM policy page changed during the RAM operation')
        return raw
    checked[offset:offset+2]=b'\x01\0'
    if hashlib.sha256(checked).hexdigest()!=profile_guards(current.model)[current.layout_revision][spec['policy_rom']]:
        raise CameraError('The ROM policy initializer differs')
    return raw
