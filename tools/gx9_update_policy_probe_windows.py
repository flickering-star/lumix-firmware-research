#!/usr/bin/env python3
"""Inspect GX9 1.4 updater policy over local USB; optionally test 0 -> 1 -> 0.

Run on the Windows PC physically connected to the camera. No SSH or network
access, update initiation, SD-card change, flash programming, reset or driver
installation. --inspect is the default. --roundtrip temporarily changes only
the fixed policy halfword and restores its complete original block.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import zipfile

import gx9_usb_capture_windows as transport


TRANSPORT_SHA = '64965e069477a2bade6054bfe08fae9d0cefc90c8e87eead5cb36924bb7ab0f2'
METADATA_SHA = 'a89c186b1a0d9eabea5d38b06cd9095dc19d75a2d0e935812bf398630491bf62'
UPDATER_SHA = '92ccfc604d7dfa6b31eaff8e6371fac4cd755c1ac6a64c47534da2e4fb3cb8d2'
TARGET = 0x83f1801a
METADATA, UPDATER = 0x83f18000, 0x84027800
GUARDS = {'linux': transport.CODE_CONTROL_SHA, 'updater': UPDATER_SHA, 'metadata': METADATA_SHA}
ACK = bytes.fromhex('0800ff01000000000000000000000000')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def packet(value=None):
    if value not in (None, 0, 1):
        raise ValueError('Only inspection or the fixed policy 0/1 values are supported')
    request = bytearray(16)
    request[:4] = bytes((8, 0, 255, 0x9b if value is None else 0x9c))
    request[4:8] = TARGET.to_bytes(4, 'little')
    if value is not None:
        request[8:10] = value.to_bytes(2, 'little')
    request[-2] = sum(request[1:-2]) & 255
    return bytes(request)


def checked_reply(reply, writing=False):
    if writing:
        if reply != ACK:
            raise ValueError('Policy write did not return the reviewed success ACK')
        return None
    return int.from_bytes(transport.response(reply), 'little')


class Access:
    def __init__(self, reader, directory, report, event, save):
        self.reader, self.directory, self.report = reader, directory, report
        self.event, self.save = event, save
        self.memory = bytearray()
        transport.PROFILES['policy-metadata'] = (METADATA, METADATA + 1024)
        transport.PROFILES['policy-updater'] = (UPDATER, UPDATER + 1024)

    def exchange(self, value=None):
        request = packet(value)
        self.reader.prepare(0)
        self.reader.requests += 1
        if value is not None:
            self.report['memory_write_requests_attempted'] += 1
            self.event('policy_write_intent', address=hex(TARGET), value=value)
            self.save()
        self.reader.bulk(1, request, 16)
        time.sleep(0.1)
        self.reader.prepare(1)
        if self.reader.bulk(0x82, None, 1) != b'\x08':
            raise ValueError('Unexpected response type')
        self.reader.prepare(1)
        return checked_reply(self.reader.bulk(0x82, None, 16), writing=value is not None)

    def word(self):
        return self.exchange()

    def write(self, value):
        self.exchange(value)

    def buffer(self):
        return self.reader.word(0x35, 0x2000)

    def block(self, kind):
        address, profile = {
            'linux': (0x80208000, 'linux-prefix'),
            'updater': (UPDATER, 'policy-updater'),
            'metadata': (METADATA, 'policy-metadata'),
        }[kind]
        data = transport.block(self.reader, address, profile)
        row = {'kind': kind, 'service_address': hex(address), 'file_offset': len(self.memory),
               'bytes': len(data), 'sha256': sha(data)}
        self.report['blocks'].append(row)
        self.memory.extend(data)
        (self.directory / 'memory.bin').write_bytes(self.memory)
        self.save()
        return data


def probe(access, report, save, roundtrip, guards=GUARDS):
    if access.buffer() != bytes.fromhex('f2b0'):
        raise ValueError('Known buffer control differs')
    linux, updater, before = (access.block(kind) for kind in ('linux', 'updater', 'metadata'))
    if any(sha(data) != guards[kind] for kind, data in
           [('linux', linux), ('updater', updater), ('metadata', before)]):
        raise ValueError('Installed 1.4 code or complete policy metadata differs; no write')
    if before[0x1a:0x1c] != b'\0\0' or access.word() != 0:
        raise ValueError('Expected default policy zero differs; no write')
    report['default_policy_verified'] = True
    report['installed_updater_matches_native_analysis'] = True
    save()
    if roundtrip:
        report['needs_restoration'] = True
        save()
        try:
            access.write(1)
            if access.word() != 1:
                raise ValueError('Temporary policy one did not read back')
            changed = access.block('metadata')
            if changed != before[:0x1a] + b'\x01\0' + before[0x1c:]:
                raise ValueError('Block changed outside the fixed policy halfword')
            report['temporary_policy_one_verified'] = True
            save()
        finally:
            # One explicit restoration attempt, including after a failed readback.
            access.write(0)
            if access.word() != 0 or access.block('metadata') != before:
                raise ValueError('Original policy and complete block were not restored')
            report['needs_restoration'] = False
            report['restoration_verified'] = True
            save()
    if access.block('updater') != updater or access.block('linux') != linux:
        raise ValueError('Code repeat control differs')
    if access.buffer() != bytes.fromhex('f2b0'):
        raise ValueError('Known buffer repeat differs')
    report['ok'] = True


def selftest():
    transport.selftest()
    for value in (None, 0, 1):
        frame = packet(value)
        assert len(frame) == 16 and frame[4:8] == bytes.fromhex('1a80f183')
        assert frame[-2] == sum(frame[1:-2]) & 255 and not frame[-1]
        assert not any(frame[10:14])
    assert packet(1)[8:10] == b'\x01\0'
    checked_reply(ACK, writing=True)
    for bad in (ACK[:-1], ACK[:4] + b'\x03' + ACK[5:]):
        try:
            checked_reply(bad, writing=True)
        except ValueError:
            pass
        else:
            raise AssertionError('Truncated/rejected ACK accepted')

    class Fake:
        def __init__(self, fail_tag=False, bad_guard=False):
            self.metadata = bytearray(1024)
            self.linux, self.updater = b'L' * 1024, b'U' * 1024
            self.fail_tag, self.bad_guard, self.writes = fail_tag, bad_guard, []

        def buffer(self):
            return bytes.fromhex('f2b0')

        def block(self, kind):
            if kind == 'metadata':
                return bytes(self.metadata)
            if kind == 'updater' and self.bad_guard:
                return b'X' * 1024
            return getattr(self, kind)

        def word(self):
            value = int.from_bytes(self.metadata[0x1a:0x1c], 'little')
            if self.fail_tag and value == 1:
                raise RuntimeError('Injected post-write read failure')
            return value

        def write(self, value):
            self.writes.append(value)
            self.metadata[0x1a:0x1c] = value.to_bytes(2, 'little')

    guards = {'linux': sha(b'L' * 1024), 'updater': sha(b'U' * 1024), 'metadata': sha(bytes(1024))}
    for roundtrip in (False, True):
        fake, report = Fake(), {}
        probe(fake, report, lambda: None, roundtrip, guards)
        assert fake.writes == ([1, 0] if roundtrip else []) and fake.metadata == bytes(1024)
        assert report['ok']
    fake, report = Fake(fail_tag=True), {}
    try:
        probe(fake, report, lambda: None, True, guards)
    except RuntimeError:
        assert fake.writes == [1, 0] and fake.metadata == bytes(1024)
        assert report['restoration_verified'] and not report['needs_restoration']
    else:
        raise AssertionError('Injected read failure was not propagated')
    fake = Fake(bad_guard=True)
    try:
        probe(fake, {}, lambda: None, True, guards)
    except ValueError:
        assert not fake.writes
    else:
        raise AssertionError('Mismatched updater code did not stop the write')


def capture(args):
    root = Path(os.environ['LOCALAPPDATA']) / 'Temp' / 'lumix-gx9-research'
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='gx9-policy-local-', dir=root))
    report = {'schema': 1, 'ok': False, 'mode': 'roundtrip' if args.roundtrip else 'inspect',
              'verifier_sha256': sha(Path(__file__).read_bytes()), 'policy_service_address': hex(TARGET),
              'memory_write_requests_attempted': 0, 'flash_programming_commands': 0,
              'firmware_update_started': False, 'needs_restoration': False,
              'temporary_policy_one_verified': False, 'restoration_verified': False, 'blocks': []}
    reader = power = None
    owned_lock = False
    lock = root / 'camera-capture.lock'
    with (directory / 'events.jsonl').open('x', encoding='utf-8', newline='\n') as events:
        def save():
            (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

        def event(kind, **fields):
            events.write(json.dumps({'event': kind, 'monotonic_ns': time.monotonic_ns(), **fields}) + '\n')
            events.flush()

        try:
            module = Path(transport.__file__)
            if sha(module.read_bytes()) != TRANSPORT_SHA:
                raise ValueError('Pinned local USB transport source differs')
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            owned_lock = True
            os.write(fd, str(os.getpid()).encode()); os.close(fd)
            model = transport.pnp_model()
            report['camera'] = model
            power = C.WinDLL('kernel32', use_last_error=True).SetThreadExecutionState
            power.argtypes, power.restype = [C.c_uint32], C.c_uint32
            if not power(0x80000001):
                raise OSError('Temporary system-awake request failed')
            dll = args.dll or root / 'libusb-1.0.dll'
            reader = transport.Reader(dll, event, model['model'])
            reader.open()
            probe(Access(reader, directory, report, event, save), report, save, args.roundtrip)
        except (Exception, KeyboardInterrupt) as error:
            report['error'] = type(error).__name__ + ': ' + str(error)
        finally:
            if reader is not None:
                report['service_requests'] = reader.requests
                reader.close()
            if power is not None:
                power(0x80000000)
            if owned_lock:
                lock.unlink()
            save()
    with zipfile.ZipFile(directory / 'capture.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in ('report.json', 'events.jsonl', 'memory.bin'):
            if (directory / name).exists():
                archive.write(directory / name, name)
    print(json.dumps(report, indent=2))
    print('Saved local USB evidence: ' + str(directory / 'capture.zip'))
    return 0 if report['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--inspect', action='store_true', help='Read guards and policy only (default)')
    mode.add_argument('--roundtrip', action='store_true', help='Test the fixed RAM policy 0 -> 1 -> 0')
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--dll', type=Path)
    args = parser.parse_args()
    selftest()
    if args.selftest:
        print('Packet/ACK, inspection, write/restore, failure restoration and mismatched-code controls passed.')
        return 0
    if sys.platform != 'win32':
        parser.error('Run on the Windows PC physically connected to the GX9')
    return capture(args)


if __name__ == '__main__':
    raise SystemExit(main())
