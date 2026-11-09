#!/usr/bin/env python3
"""Inspect, enable, or restore the GX9 1.4 live updater-policy word on Windows.

--enable leaves verified RAM policy one set for a separate, manual updater
attempt. --restore sets the same RAM word to zero. Inspection is the default.
No update, flash command, SD-card write, reset, SSH or network access is included.
Keep the unchanged policy-probe and USB-transport modules beside this file.
"""
from __future__ import annotations

import argparse
import ctypes as C
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import zipfile

import gx9_update_policy_probe_windows as probe


transport = probe.transport
sha = probe.sha
PROBE_SHA = '0db4a92956f5fff28e5597139394d76d0ce9d8ebed810ee69eb18966927d4b6a'
CANDIDATE_SHA = '719fc4e4daeb17f09172e7ac59675fdc0a637376a73284e814f9a9b266aa6883'
CANDIDATE_BYTES = 102538240
POLICY_OFFSET = 0x1a


def shadow_packet():
    request = bytearray(bytes.fromhex('0800ff350dc022000000000000000000'))
    request[-2] = sum(request[1:-2]) & 255
    return bytes(request)


class Access(probe.Access):
    def shadow_word(self):
        request = shadow_packet()
        self.reader.prepare(0)
        self.reader.requests += 1
        self.report['policy_shadow_read_requests'] += 1
        self.reader.bulk(1, request, 16)
        time.sleep(0.1)
        self.reader.prepare(1)
        if self.reader.bulk(0x82, None, 1) != b'\x08':
            raise ValueError('Unexpected fixed-bank response type')
        self.reader.prepare(1)
        return probe.checked_reply(self.reader.bulk(0x82, None, 16))


def canonical_metadata(data):
    if len(data) != 1024 or data[POLICY_OFFSET:POLICY_OFFSET + 2] not in (b'\0\0', b'\x01\0'):
        raise ValueError('Policy metadata or current policy is not a supported 0/1 value')
    return data[:POLICY_OFFSET] + bytes(2) + data[POLICY_OFFSET + 2:]


def change_policy(access, report, save, mode, guards=probe.GUARDS):
    if mode not in ('inspect', 'enable', 'restore'):
        raise ValueError('Unrecognized fixed policy operation')
    if access.buffer() != bytes.fromhex('f2b0'):
        raise ValueError('Known settings-buffer control differs; no write')
    linux, updater, before = (access.block(kind) for kind in ('linux', 'updater', 'metadata'))
    normalized = canonical_metadata(before)
    if any(sha(data) != guards[kind] for kind, data in (
            ('linux', linux), ('updater', updater), ('metadata', normalized))):
        raise ValueError('Pinned 1.4 code or complete normalized policy block differs; no write')
    original = int.from_bytes(before[POLICY_OFFSET:POLICY_OFFSET + 2], 'little')
    if access.word() != original or access.shadow_word() != original:
        raise ValueError('Absolute and fixed-bank policy readings disagree; no write')
    report.update({'initial_policy': original, 'installed_updater_matches_verified_1_4': True,
                   'complete_metadata_guard_verified': True,
                   'absolute_and_shadow_before_agree': True})
    target = {'inspect': original, 'enable': 1, 'restore': 0}[mode]
    expected = before[:POLICY_OFFSET] + target.to_bytes(2, 'little') + before[POLICY_OFFSET + 2:]
    attempted = False
    save()
    try:
        if target != original:
            attempted = True
            report.update({'write_value_requested': target, 'state_uncertain': True})
            save()  # Persist intent before submitting the single halfword write.
            access.write(target)
        if access.word() != target or access.shadow_word() != target:
            raise ValueError('Policy did not read back through both access paths')
        if access.block('metadata') != expected:
            raise ValueError('Complete policy block does not match the one-word change')
        if access.block('updater') != updater or access.block('linux') != linux:
            raise ValueError('Code repeat control differs')
        if access.buffer() != bytes.fromhex('f2b0'):
            raise ValueError('Settings-buffer repeat differs')
    except (Exception, KeyboardInterrupt):
        if attempted:
            report['rollback_attempted'] = True
            save()
            try:
                access.write(original)
                if (access.word() != original or access.shadow_word() != original
                        or access.block('metadata') != before):
                    raise ValueError('Original complete block was not restored')
                report.update({'rollback_verified': True, 'state_uncertain': False,
                               'verified_policy': original, 'policy_left_enabled': original == 1})
            except (Exception, KeyboardInterrupt) as error:
                report['rollback_error'] = type(error).__name__ + ': ' + str(error)
                report['state_uncertain'] = True
            save()
        raise
    report.update({'ok': True, 'verified_policy': target, 'state_uncertain': False,
                   'policy_left_enabled': target == 1,
                   'absolute_and_shadow_after_agree': True,
                   'complete_expected_policy_block_verified': True,
                   'code_repeat_controls_verified': True})
    save()


def verify_dependencies():
    for module, expected in ((probe, PROBE_SHA), (transport, probe.TRANSPORT_SHA)):
        if sha(Path(module.__file__).read_bytes()) != expected:
            raise ValueError('Required unchanged local helper dependency differs: ' + module.__name__)


def firmware_check(path):
    import hashlib
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            size += len(chunk)
            digest.update(chunk)
    if (size, digest.hexdigest()) != (CANDIDATE_BYTES, CANDIDATE_SHA):
        raise ValueError('Supplied firmware is not the exact prepared two-component policy candidate')
    return {'bytes': size, 'sha256': digest.hexdigest(), 'exact_prepared_candidate': True,
            'physical_installation_or_boot_verified': False}


def selftest():
    probe.selftest()
    request = shadow_packet()
    assert request[:7] == bytes.fromhex('0800ff350dc022') and len(request) == 16
    assert request[-2] == sum(request[1:-2]) & 255 and not request[-1]

    class Fake:
        def __init__(self, initial=0, bad=None, fail=None, rollback_fails=False):
            self.metadata = bytearray(1024)
            self.metadata[POLICY_OFFSET:POLICY_OFFSET + 2] = initial.to_bytes(2, 'little')
            self.linux, self.updater = b'L' * 1024, b'U' * 1024
            self.bad, self.fail = bad, fail
            self.failed, self.rollback_fails, self.writes = False, rollback_fails, []

        def inject(self, stage):
            if self.writes and self.fail == stage and not self.failed:
                self.failed = True
                raise RuntimeError('Injected ' + stage + ' failure')

        def buffer(self):
            self.inject('buffer')
            return bytes.fromhex('f2b0')

        def block(self, kind):
            self.inject(kind)
            if kind == 'metadata':
                data = bytes(self.metadata)
                return data[:-1] + b'X' if self.bad == kind else data
            return b'X' * 1024 if self.bad == kind else getattr(self, kind)

        def word(self):
            self.inject('word')
            return int.from_bytes(self.metadata[POLICY_OFFSET:POLICY_OFFSET + 2], 'little')

        def shadow_word(self):
            self.inject('shadow')
            value = int.from_bytes(self.metadata[POLICY_OFFSET:POLICY_OFFSET + 2], 'little')
            return value ^ 1 if self.bad == 'alias' else value

        def write(self, value):
            if self.rollback_fails and self.writes:
                raise RuntimeError('Injected disconnection during restoration')
            self.writes.append(value)
            self.metadata[POLICY_OFFSET:POLICY_OFFSET + 2] = value.to_bytes(2, 'little')
            self.inject('write')

    guards = {'linux': sha(b'L' * 1024), 'updater': sha(b'U' * 1024), 'metadata': sha(bytes(1024))}
    successful = []
    for mode in ('inspect', 'enable', 'restore'):
        for initial in (0, 1):
            access, report = Fake(initial), {}
            change_policy(access, report, lambda: None, mode, guards)
            target = {'inspect': initial, 'enable': 1, 'restore': 0}[mode]
            expected_writes = [] if initial == target else [target]
            assert access.writes == expected_writes and access.word() == target
            assert report['ok'] and report['verified_policy'] == target and not report['state_uncertain']
            successful.append({'mode': mode, 'initial': initial, 'final': target,
                               'writes': expected_writes})
    for bad in ('linux', 'updater', 'metadata', 'alias'):
        access = Fake(bad=bad)
        try:
            change_policy(access, {}, lambda: None, 'enable', guards)
        except ValueError:
            assert not access.writes
        else:
            raise AssertionError('Mismatched precondition allowed a write: ' + bad)
    access = Fake(initial=2)
    try:
        change_policy(access, {}, lambda: None, 'enable', guards)
    except ValueError:
        assert not access.writes
    else:
        raise AssertionError('Unknown initial policy allowed a write')
    for mode, initial in (('enable', 0), ('restore', 1)):
        target = 1 - initial
        for stage in ('write', 'word', 'shadow', 'metadata', 'updater', 'linux', 'buffer'):
            access, report = Fake(initial, fail=stage), {}
            try:
                change_policy(access, report, lambda: None, mode, guards)
            except RuntimeError:
                assert access.writes == [target, initial] and access.word() == initial
                assert report['rollback_verified'] and not report['state_uncertain']
                assert not report.get('ok')
            else:
                raise AssertionError('Post-write failure was not propagated: ' + stage)
    access, report = Fake(fail='word', rollback_fails=True), {}
    try:
        change_policy(access, report, lambda: None, 'enable', guards)
    except RuntimeError:
        assert report['state_uncertain'] and report['rollback_error']
        assert not report.get('ok') and not report.get('rollback_verified')
    else:
        raise AssertionError('Failed restoration was not reported')
    return {'successful_state_controls': successful, 'mismatched_precondition_controls': 5,
            'post_write_failure_restoration_controls': 14,
            'failed_restoration_marks_state_uncertain': True,
            'camera_or_network_access': False}


def capture(args, firmware):
    root = Path(os.environ['LOCALAPPDATA']) / 'Temp' / 'lumix-gx9-research'
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='gx9-policy-helper-', dir=root))
    report = {'schema': 1, 'ok': False, 'mode': args.mode,
              'helper_sha256': sha(Path(__file__).read_bytes()), 'policy_service_address': hex(probe.TARGET),
              'policy_shadow_selector': {'opcode': '0x35', 'area': '0x22', 'word_index': '0xc00d'},
              'memory_write_requests_attempted': 0, 'policy_shadow_read_requests': 0,
              'flash_programming_commands': 0, 'firmware_update_started': False,
              'state_uncertain': False, 'blocks': [], 'firmware_file_check': firmware,
              'persistence_across_reboot_established': False}
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
            verify_dependencies()
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            owned_lock = True
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            model = transport.pnp_model()
            report['camera'] = model
            power = C.WinDLL('kernel32', use_last_error=True).SetThreadExecutionState
            power.argtypes, power.restype = [C.c_uint32], C.c_uint32
            if not power(0x80000001):
                raise OSError('Temporary system-awake request failed')
            reader = transport.Reader(args.dll or root / 'libusb-1.0.dll', event, model['model'])
            reader.open()
            change_policy(Access(reader, directory, report, event, save), report, save, args.mode)
        except (Exception, KeyboardInterrupt) as error:
            report['error'] = type(error).__name__ + ': ' + str(error)
        finally:
            if reader is not None:
                report['service_requests'] = reader.requests
                try:
                    reader.close()
                except Exception as error:
                    report['close_error'] = type(error).__name__ + ': ' + str(error)
                    report['ok'] = False
            if power is not None:
                power(0x80000000)
            if owned_lock:
                lock.unlink()
            save()
    with zipfile.ZipFile(directory / 'capture.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in ('report.json', 'events.jsonl', 'memory.bin'):
            if (directory / name).exists():
                archive.write(directory / name, name)
    if report['ok']:
        print(f"Verified live RAM policy {report['verified_policy']} through both read paths.")
        if args.mode == 'enable':
            print('Policy 1 was left enabled. No firmware update has been started.')
            print('Keep the camera powered on. Reboot or settings reload may clear this RAM change.')
        elif args.mode == 'restore':
            print('Live RAM policy restored to 0. This does not rewrite the stored fixed bank.')
    else:
        print('FAILED: ' + report.get('error', report.get('close_error', 'verification did not complete')))
        if report.get('rollback_verified'):
            print('Original policy and complete metadata block were restored.')
        elif report.get('state_uncertain'):
            print('Policy state is uncertain; do not rely on this run for an update.')
    print('Saved local report: ' + str(directory / 'report.json'))
    print('Saved USB evidence: ' + str(directory / 'capture.zip'))
    return 0 if report['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--inspect', dest='mode', action='store_const', const='inspect',
                       help='Verify code, full metadata and both policy readers without writing (default)')
    modes.add_argument('--enable', dest='mode', action='store_const', const='enable',
                       help='Leave verified live RAM policy 1 set after success')
    modes.add_argument('--restore', dest='mode', action='store_const', const='restore',
                       help='Set only the live RAM policy back to 0')
    parser.set_defaults(mode='inspect')
    parser.add_argument('--selftest', action='store_true', help='Offline controls only; no camera access')
    parser.add_argument('--firmware', type=Path, help='Optionally verify the exact prepared candidate before USB access')
    parser.add_argument('--dll', type=Path)
    args = parser.parse_args()
    verify_dependencies()
    selftest()
    if args.selftest:
        print('Inspection, enable/restore, idempotency, guards and failure-restoration controls passed offline.')
        return 0
    firmware = firmware_check(args.firmware) if args.firmware else None
    if sys.platform != 'win32':
        parser.error('Run on the Windows PC physically connected to the GX9')
    return capture(args, firmware)


if __name__ == '__main__':
    raise SystemExit(main())
