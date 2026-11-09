#!/usr/bin/env python3
"""Windows-local GX9 capture of previously validated RAM ranges.

Uses the existing pinned libusb DLL and WinUSB driver. No network connection,
USB reset, driver installation, arbitrary opcode, write command or automatic
retry. Output includes partial data, a flushed transfer log and a final ZIP.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

LIBUSB_SHA = '7cbf37e76dae9c840c7e8dbf7348ee8897dcc86c8ba45e46ada60b89411569f7'

U8, U16 = C.c_uint8, C.c_uint16

class Device(C.Structure):
    _fields_ = [(name, typ) for name, typ in [
        ('length', U8), ('type', U8), ('usb', U16), ('cls', U8), ('sub', U8), ('protocol', U8),
        ('packet0', U8), ('vid', U16), ('pid', U16), ('release', U16), ('manufacturer', U8),
        ('product', U8), ('serial', U8), ('configurations', U8)]]

class Endpoint(C.Structure):
    _fields_ = [('length', U8), ('type', U8), ('address', U8), ('attributes', U8),
                ('packet', U16), ('interval', U8), ('refresh', U8), ('synch', U8),
                ('extra', C.c_void_p), ('extra_length', C.c_int)]

class Alternate(C.Structure):
    _fields_ = [('length', U8), ('type', U8), ('number', U8), ('alternate', U8),
                ('count', U8), ('cls', U8), ('sub', U8), ('protocol', U8), ('string', U8),
                ('endpoint', C.POINTER(Endpoint)), ('extra', C.c_void_p), ('extra_length', C.c_int)]

class Interface(C.Structure):
    _fields_ = [('alternate', C.POINTER(Alternate)), ('count', C.c_int)]

class Configuration(C.Structure):
    _fields_ = [('length', U8), ('type', U8), ('total', U16), ('count', U8), ('value', U8),
                ('string', U8), ('attributes', U8), ('power', U8), ('interface', C.POINTER(Interface)),
                ('extra', C.c_void_p), ('extra_length', C.c_int)]

def descriptor_selftest():
    assert C.sizeof(Device) == 18
    if C.sizeof(C.c_void_p) == 8:
        assert (C.sizeof(Endpoint), C.sizeof(Alternate), C.sizeof(Interface), C.sizeof(Configuration)) == (32, 40, 16, 40)
    data = bytes.fromhex('1201000200000040da047023000101020001')
    descriptor = Device.from_buffer_copy(data)
    assert descriptor.vid == 0x04DA and descriptor.pid == 0x2370 and descriptor.configurations == 1

class Reader:
    def __init__(self, dll, event, model):
        if hashlib.sha256(Path(dll).read_bytes()).hexdigest() != LIBUSB_SHA:
            raise ValueError('Official DLL hash differs')
        self.lib = C.CDLL(str(Path(dll).resolve()))
        if model not in ("DC-GX9", "DC-GX7MK3"):
            raise ValueError("Unrecognized PnP camera model")
        self.model = model
        self.event = event
        self.ctx, self.handle = C.c_void_p(), C.c_void_p()
        self.device_list = C.POINTER(C.c_void_p)()
        self.claimed = False
        self.requests = self.validated = 0

    def function(self, name, result, args):
        value = getattr(self.lib, name)
        value.restype, value.argtypes = result, args
        return value

    def check(self, label, code):
        self.event('api', step=label, status=code)
        if code < 0:
            raise RuntimeError(label+' failed: '+str(code))

    def open(self):
        self.check('init', self.function('libusb_init', C.c_int, [C.POINTER(C.c_void_p)])(C.byref(self.ctx)))
        count = self.function('libusb_get_device_list', C.c_ssize_t,
            [C.c_void_p, C.POINTER(C.POINTER(C.c_void_p))])(self.ctx, C.byref(self.device_list))
        self.check('enumerate', count)
        if count > 4096:
            raise ValueError('Enumeration bounds exceeded')
        candidates = []
        get = self.function('libusb_get_device_descriptor', C.c_int, [C.c_void_p, C.POINTER(Device)])
        for index in range(count):
            descriptor = Device()
            if get(self.device_list[index], C.byref(descriptor)) == 0 and (descriptor.vid, descriptor.pid) == (0x04DA, 0x2370):
                candidates.append((self.device_list[index], descriptor))
        if len(candidates) != 1:
            raise ValueError('Expected exactly one service VID/PID')
        device, descriptor = candidates[0]
        cfg = C.POINTER(Configuration)()
        self.check('get_configuration_descriptor', self.function('libusb_get_config_descriptor', C.c_int,
            [C.c_void_p, C.c_uint8, C.POINTER(C.POINTER(Configuration))])(device, 0, C.byref(cfg)))
        try:
            value = cfg.contents
            if descriptor.configurations != 1 or value.value != 1 or value.count != 1:
                raise ValueError('Configuration geometry differs')
            interface = value.interface[0]
            if interface.count != 1:
                raise ValueError('Alternate geometry differs')
            alt = interface.alternate[0]
            if (alt.number, alt.alternate, alt.cls, alt.sub, alt.protocol, alt.count) != (0, 0, 255, 160, 176, 3):
                raise ValueError('GX9 service interface differs')
            endpoints = sorted((alt.endpoint[i].address, alt.endpoint[i].attributes & 3,
                                alt.endpoint[i].packet) for i in range(3))
            if ([(a, t) for a, t, _ in endpoints] != [(1, 2), (0x82, 2), (0x83, 3)]
                    or any(size not in (64, 512) for _, _, size in endpoints)):
                raise ValueError('Service endpoints differ')
            self.event('descriptor_profile', configuration=value.value, endpoints=endpoints)
        finally:
            self.function('libusb_free_config_descriptor', None, [C.POINTER(Configuration)])(cfg)
        self.check('open', self.function('libusb_open', C.c_int,
            [C.c_void_p, C.POINTER(C.c_void_p)])(device, C.byref(self.handle)))
        current = C.c_int()
        self.check('get_active_configuration', self.function('libusb_get_configuration', C.c_int,
            [C.c_void_p, C.POINTER(C.c_int)])(self.handle, C.byref(current)))
        if current.value != 1:
            raise ValueError('Active configuration differs; no configuration change attempted')
        self.check('claim_interface', self.function('libusb_claim_interface', C.c_int,
            [C.c_void_p, C.c_int])(self.handle, 0))
        self.claimed = True

    def prepare(self, index):
        if index not in (0, 1):
            raise ValueError('Unreviewed direction preparation')
        self.event('prepare', setup_hex='40000000'+index.to_bytes(2, 'little').hex()+'0000')
        status = self.function('libusb_control_transfer', C.c_int,
            [C.c_void_p, C.c_uint8, C.c_uint8, C.c_uint16, C.c_uint16, C.c_void_p, C.c_uint16, C.c_uint])(
                self.handle, 0x40, 0, 0, index, None, 0, 1500)
        self.check('prepare', status)
        if status:
            raise ValueError('Unexpected control length')

    def bulk(self, endpoint, data, size):
        buffer = (C.c_ubyte * size)()
        if data is not None:
            buffer[:] = data
        count = C.c_int()
        status = self.function('libusb_bulk_transfer', C.c_int,
            [C.c_void_p, C.c_ubyte, C.c_void_p, C.c_int, C.POINTER(C.c_int), C.c_uint])(
                self.handle, endpoint, buffer, size, C.byref(count), 1500)
        self.event('bulk', endpoint=endpoint, status=status, bytes=count.value,
                   hex=bytes(buffer[:max(0, min(count.value, size))]).hex())
        self.check('bulk', status)
        if count.value != size:
            raise ValueError('Unexpected transfer length')
        return bytes(buffer)

    def word(self, operation, index):
        request = packet(operation, index)
        self.prepare(0)
        self.requests += 1
        self.bulk(1, request, 16)
        time.sleep(0.1)
        self.prepare(1)
        if self.bulk(0x82, None, 1) != b'\x08':
            raise ValueError('Unexpected response type')
        self.prepare(1)
        value = response(self.bulk(0x82, None, 16))
        self.validated += 1
        return value

    def close(self):
        if self.handle:
            if self.claimed:
                self.function('libusb_release_interface', C.c_int, [C.c_void_p, C.c_int])(self.handle, 0)
            self.function('libusb_close', None, [C.c_void_p])(self.handle)
        if self.device_list:
            self.function('libusb_free_device_list', None, [C.POINTER(C.c_void_p), C.c_int])(self.device_list, 1)
        if self.ctx:
            self.function('libusb_exit', None, [C.c_void_p])(self.ctx)


PROFILES = {
    'linux-prefix': (0x80200000, 0x80400000),
    'pre-linux': (0x80000000, 0x80200000),
    'early-tables': (0x83E70000, 0x83E84000),
}
CODE_CONTROL_SHA = 'd982dd856084fcd5dfbfc9cc40f02922e2b610287ede1ddd1f347d90bfe1ddbe'


def packet(operation, index):
    if (operation, index) != (0x35, 0x2000):
        raise ValueError('Only the established buffer control exists in this tool')
    return bytes.fromhex('0800ff35002010000000000000006400')


def response(data):
    if (len(data) != 16 or data[:4] != b'\x08\0\xff\x36'
            or any(data[6:14]) or data[15] or data[14] != sum(data[1:14]) & 255):
        raise ValueError('Invalid buffer control response')
    return data[4:6]


def block_packet(address, profile):
    start, end = PROFILES[profile]
    if (address % 1024 or not (start <= address <= end-1024 or address == 0x80208000)):
        raise ValueError('Address outside the selected established interval')
    request = bytearray(1030)
    request[:4] = bytes((1, 0, 255, 0x5C))
    request[4:8] = address.to_bytes(4, 'little')
    request[8:12] = (address+1024).to_bytes(4, 'little')
    request[-2] = sum(request[1:-2]) & 255
    return bytes(request)


def block_response(reply, request):
    if (len(reply) != 1030 or reply[:4] != bytes((1, 0, 255, 5))
            or reply[-1] or reply[-2] != sum(reply[1:-2]) & 255):
        raise ValueError('Invalid block response; stopped without retry')
    if reply[4:-2] == request[4:-2]:
        raise ValueError('Source payload unchanged from request; no read claimed')
    return reply[4:-2]


def block(reader, address, profile):
    request = block_packet(address, profile)
    reader.prepare(0)
    reader.requests += 1
    reader.bulk(1, request, len(request))
    time.sleep(0.01)
    reader.prepare(1)
    kind = reader.bulk(0x82, None, 1)[0]
    if kind not in (1, 8):
        raise ValueError('Unexpected response class')
    reader.prepare(1)
    reply = reader.bulk(0x82, None, 1030 if kind == 1 else 16)
    return block_response(reply, request)


def pnp_model():
    script = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$rows=@(Get-PnpDevice -PresentOnly | Where-Object {$_.InstanceId -like 'USB\VID_04DA&PID_2370*'} | ForEach-Object {
$d=$_
function P($key) { (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName $key -ErrorAction Stop).Data }
[pscustomobject]@{id=$d.InstanceId;status=$d.Status;model=(P 'DEVPKEY_Device_BusReportedDeviceDesc');service=(P 'DEVPKEY_Device_Service');problem=(P 'DEVPKEY_Device_ProblemCode')}
})
ConvertTo-Json -InputObject $rows -Depth 4 -Compress
"""
    process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                             capture_output=True, timeout=30)
    if process.returncode:
        raise RuntimeError(process.stderr.decode('utf-8', 'replace')[:1000])
    rows = json.loads(process.stdout.decode('utf-8-sig'))
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError('Exactly one GX9 service-mode camera is required')
    row = rows[0]
    if (row['model'] not in ('DC-GX9', 'DC-GX7MK3')
            or (row['status'], row['service'], row['problem']) != ('OK', 'WinUSB', 0)):
        raise ValueError('Camera PnP model, service or status differs')
    return {'model': row['model'], 'status': row['status'], 'service': row['service'],
            'instance_sha256': hashlib.sha256(row['id'].encode()).hexdigest()}


def selftest():
    descriptor_selftest()
    assert packet(0x35, 0x2000).hex() == '0800ff35002010000000000000006400'
    assert response(bytes.fromhex('0800ff36f2b00000000000000000d700')) == bytes.fromhex('f2b0')
    actual = block_packet(0x80208000, 'linux-prefix')
    assert actual[:12].hex() == '0100ff5c0080208000842080'
    assert actual[-2:] == bytes.fromhex('9f00')
    assert hashlib.sha256(actual).hexdigest() == '0826cc0ef0b0f96ebce4d2b0dc7a9f2f553ed09c547ba68c49eb8943b889d7c9'
    # Real successful reply's header and independently captured checksum rules.
    for operation, index in ((0x70, 0), (0x9B, 0x2000), (0x35, 0x2001)):
        try:
            packet(operation, index)
        except ValueError:
            pass
        else:
            raise AssertionError('Unreviewed operation accepted')
    for address in (0x7FFFFC00, 0x80400000, 0x80200001, 0x83E70000):
        try:
            block_packet(address, 'linux-prefix')
        except ValueError:
            pass
        else:
            raise AssertionError('Out-of-profile address accepted')
    fake = bytearray(actual)
    fake[3] = 5
    fake[-2] = sum(fake[1:-2]) & 255
    for reply in (actual, bytes(fake), actual[:-1]):
        try:
            block_response(reply, actual)
        except ValueError:
            pass
        else:
            raise AssertionError('Echo, unchanged payload or truncation accepted')


def capture(dll, workspace, profile, model):
    workspace.mkdir(parents=True, exist_ok=True)
    lock = workspace / 'camera-capture.lock'
    # A previous interrupted job leaves the lock for the owner to inspect.
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(descriptor, json.dumps({'pid': os.getpid(), 'profile': profile}).encode())
    os.close(descriptor)
    reader = None
    power = None
    directory = None
    result = {'ok': False, 'profile': profile, 'model_guard': model,
              'memory_writes': 0, 'flash_writes': 0, 'delay_seconds': 0.01}
    started = time.monotonic()
    try:
        directory = Path(tempfile.mkdtemp(prefix='gx9-local-'+profile+'-', dir=workspace))
        (directory / 'capture-source.py').write_bytes(Path(__file__).read_bytes())
        power = C.WinDLL('kernel32', use_last_error=True).SetThreadExecutionState
        power.argtypes, power.restype = [C.c_uint32], C.c_uint32
        if not power(0x80000001):
            raise OSError('Temporary system-awake request failed')
        start, end = PROFILES[profile]
        result.update(start=hex(start), end_exclusive=hex(end), bytes_saved=0, blocks_saved=0)
        print('Saving locally to '+str(directory), flush=True)
        with (directory / 'events.jsonl').open('x') as events:
            def event(kind, **fields):
                events.write(json.dumps({'event': kind, 'monotonic_ns': time.monotonic_ns(), **fields})+'\n')
                events.flush()

            reader = Reader(dll, event, model['model'])
            try:
                reader.open()
                if reader.word(0x35, 0x2000) != bytes.fromhex('f2b0'):
                    raise ValueError('Established buffer control differs')
                control = block(reader, 0x80208000, profile)
                if hashlib.sha256(control).hexdigest() != CODE_CONTROL_SHA:
                    raise ValueError('Established ARM code block differs')
                digest = hashlib.sha256()
                with (directory / 'memory.bin').open('xb') as stream:
                    for address in range(start, end, 1024):
                        data = block(reader, address, profile)
                        stream.write(data)
                        stream.flush()
                        digest.update(data)
                        result['bytes_saved'] += len(data)
                        result['blocks_saved'] += 1
                        if result['blocks_saved'] % 256 == 0:
                            print(str(result['bytes_saved'])+' bytes saved', flush=True)
                result['sha256'] = digest.hexdigest()
                if block(reader, 0x80208000, profile) != control:
                    raise ValueError('ARM code repeat differs')
                if reader.word(0x35, 0x2000) != bytes.fromhex('f2b0'):
                    raise ValueError('Post-read buffer control differs')
                result.update(ok=True, code_repeat_exact=True)
            finally:
                result.update(service_requests=reader.requests, validated_words=reader.validated)
                reader.close()
                reader = None
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = type(error).__name__+': '+str(error)
    finally:
        result['elapsed_seconds'] = time.monotonic()-started
        if power is not None:
            power(0x80000000)
        if directory is not None:
            (directory / 'report.json').write_text(json.dumps(result, indent=2)+'\n')
            with zipfile.ZipFile(directory / 'capture.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
                for name in ('report.json', 'events.jsonl', 'memory.bin', 'capture-source.py'):
                    path = directory / name
                    if path.is_file():
                        archive.write(path, name)
            result['archive'] = str(directory / 'capture.zip')
        lock.unlink()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--capture', choices=sorted(PROFILES))
    parser.add_argument('--dll', type=Path)
    parser.add_argument('--workspace', type=Path)
    args = parser.parse_args()
    selftest()
    if args.selftest:
        print('Descriptor, captured packet and address guards passed; no device or network accessed.')
        return 0
    if sys.platform != 'win32':
        parser.error('Run locally on the Windows PC connected to the GX9')
    model = pnp_model()
    if not args.capture:
        print(json.dumps({'camera': model, 'service_requests': 0}, indent=2))
        return 0
    existing = Path(os.environ['LOCALAPPDATA'])/'Temp'/'lumix-gx9-research'
    workspace = args.workspace or existing
    dll = args.dll or existing/'libusb-1.0.dll'
    result = capture(dll, workspace, args.capture, model)
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
