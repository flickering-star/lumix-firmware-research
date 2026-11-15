"""The reviewed GM5 1.1 profiles and their sole temporary RAM change."""
from __future__ import annotations

from dataclasses import dataclass,field
import hashlib
import struct

from .protocol import Service
from .usb import Transport

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


class CameraError(ValueError):
    pass


@dataclass(frozen=True)
class Inspection:
    model:str
    serial:str=field(repr=False)
    usb_release:int
    version:int
    rom_policy:int
    ram_policy:int
    key:bytes=field(repr=False)

    @property
    def modified_updates_enabled(self):return self.rom_policy==0

    @property
    def profile(self):return PROFILE_NAMES[self.version]

    def report(self):
        return dict(model=self.model,firmware='1.1',profile=self.profile,
            internal_revision=f'{self.version:04x}',
            rom_policy=self.rom_policy,ram_policy=self.ram_policy,
            modified_updates_enabled=self.modified_updates_enabled,
            encryption_key_recovered=True,profile_guards_verified=True)


def inspect_service(service,identity,progress=lambda *_:None):
    if identity.get('model')!=MODEL:raise CameraError('Only the reviewed DMC-GM5 profile is supported')
    pages={};guards=None;version=None
    for i,address in enumerate(sorted(PAGES)):
        progress('Checking camera firmware',i,len(PAGES))
        raw=service.read(address)
        if len(raw)!=1024:raise CameraError('Camera memory reply is incomplete')
        pages[address]=raw
        if address==0x40000400:
            version=struct.unpack_from('<2H',raw,0x2A0)
            if version[0]!=version[1] or version[0] not in PROFILE_GUARDS:
                raise CameraError('Unsupported GM5 firmware revision. No camera change was made.')
            guards=PROFILE_GUARDS[version[0]]
        if address in GUARDS:
            if guards is None:raise CameraError('Camera header must be checked first')
            checked=bytearray(raw)
            if address==POLICY_ROM:
                value=struct.unpack_from('<H',checked,0x3DC)[0]
                if value not in (0,1):raise CameraError('The update policy is not in a reviewed state')
                checked[0x3DC:0x3DE]=b'\x01\0'
            if hashlib.sha256(checked).hexdigest()!=guards[address]:
                raise CameraError('The firmware build differs from the reviewed GM5 profile. No camera change was made.')
    key=pages[KEY_PAGE][KEY_OFFSET:KEY_OFFSET+16]
    if hashlib.sha256(key).hexdigest()!=KEY_SHA:raise CameraError('The firmware encryption-key record differs')
    rom=struct.unpack_from('<H',pages[POLICY_ROM],0x3DC)[0]
    ram=struct.unpack_from('<H',pages[POLICY_RAM],0x90)[0]
    if ram not in (0,1):raise CameraError('The temporary update policy is not in a reviewed state')
    if rom==0 and ram!=0:
        raise CameraError('The current update state differs from the installed patch. '
            'Switch the camera off normally, reconnect in service mode and read it again.')
    if pages[MODE][0x5D]!=0:raise CameraError('Reconnect the camera in the standard service USB state')
    return Inspection(MODEL,identity.get('serial',''),identity.get('usb_release',0),version[0],rom,ram,key)


def inspect_camera(transport_factory=Transport,progress=lambda *_:None):
    with transport_factory() as transport:
        return inspect_service(Service(transport,PAGES),transport.identity,progress)


def enable_update(previous,transport_factory=Transport,progress=lambda *_:None):
    """Recheck the entire profile in this connection before a fixed write."""
    with transport_factory() as transport:
        service=Service(transport,PAGES)
        current=inspect_service(service,transport.identity,progress)
        if (previous.serial and current.serial!=previous.serial or current.key!=previous.key
                or current.version!=previous.version or current.usb_release!=previous.usb_release
                or current.rom_policy!=previous.rom_policy):
            raise CameraError('The camera changed after preparation. Read it again before continuing.')
        if current.rom_policy==0 or current.ram_policy==0:
            return dict(wrote_ram=False,already_enabled=True,rom_policy=current.rom_policy)
        # Recheck the addressing mode immediately before the single store.
        if service.read(MODE)[0x5D]!=0:raise CameraError('Camera service state changed; no write sent')
        page=service.read(POLICY_RAM)
        if struct.unpack_from('<H',page,0x90)[0]!=1:raise CameraError('Camera policy changed; read the camera again')
        service.set_policy(0)
        wanted=bytearray(page);wanted[0x90:0x92]=bytes(2)
        if service.read(POLICY_RAM)!=wanted:
            raise CameraError('The temporary flag write could not be verified. Reconnect and read the camera before proceeding.')
        page_for_rom(current,service)
        return dict(wrote_ram=True,already_enabled=False,rom_policy=1,ram_policy=0,
            complete_ram_page_readback_verified=True)


def page_for_rom(current,service):
    # Independent post-write ROM validation; the host never sends NOR writes.
    raw=service.read(POLICY_ROM);checked=bytearray(raw)
    if struct.unpack_from('<H',raw,0x3DC)[0]!=current.rom_policy:
        raise CameraError('The ROM update policy changed unexpectedly')
    checked[0x3DC:0x3DE]=b'\x01\0'
    if hashlib.sha256(checked).hexdigest()!=PROFILE_GUARDS[current.version][POLICY_ROM]:
        raise CameraError('The ROM policy initializer differs')
    return raw
