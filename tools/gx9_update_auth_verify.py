#!/usr/bin/env python3
"""Verify GX9 update signatures offline, optionally using the native ARM code.

Requires the decoded, hash-pinned 1.4 program and local official update files.
OpenSSL checks ECDSA independently. --native additionally requires Unicorn
2.1.4; it stops the update parser after directory authentication, before payload
decryption or programming. No device, network, private signing key or shell is
used. All native memory changes occur inside the emulator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

from tz30_control_verify import records


PROGRAM_SHA = '1ea24a84e5bbc1fa24beef59628a8c0fc13d8de042efbe187730031dc4f263d5'
PACKAGE_SHAS = {
    'e26e4b422e9d46dffb7d93eaabd061bb3e49e2d84654dffc1d892f7f25126e7a': '1.4',
    'c08354c91d083d74b274c4884ab4f06d3f72e47ea289ea80c9685f2292f5b801': '1.5',
}
POINT_SHA = '9f1c0f68e2bad2b265fae5b36d625bf9bc0a9e6c49302542fa4a1815730829d1'
BASE, POINT, REFERENCE = 0x03e80000, 0x04622b6a, 0x04622bac
CONTEXT, SCRATCH = 0x30000000, 0x30010000
STACK, RETURN, FIRMWARE = 0x10000000, 0x20000000, 0x50000000
AUTHENTICATED = 0x04027858
POLICY = 0x03f1801a
P = int('ffffffff00000001000000000000000000000000ffffffffffffffffffffffff', 16)
B = int('5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b', 16)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def public_key(program):
    if sha(program) != PROGRAM_SHA:
        raise ValueError('Expected the fully verified 1.4 program component')
    size, pointer = struct.unpack_from('<II', program, REFERENCE - BASE + 0x54)
    if (size, pointer) != (64, POINT):
        raise ValueError('Native public-key descriptor differs')
    point = program[POINT - BASE:POINT - BASE + size]
    if sha(point) != POINT_SHA:
        raise ValueError('Native public point differs')
    # Native big integers use eight little-endian words, with the low word first.
    x, y = (int.from_bytes(point[i:i + 32], 'little') for i in (0, 32))
    if not (0 <= x < P and 0 <= y < P and (y*y - x*x*x + 3*x - B) % P == 0):
        raise ValueError('Public point is not on the P-256 curve')
    prefix = bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d03010703420004')
    return prefix + x.to_bytes(32, 'big') + y.to_bytes(32, 'big')


def signature_der(raw):
    if len(raw) != 64:
        raise ValueError('Signature length differs')

    def integer(little):
        value = little[::-1].lstrip(b'\0') or b'\0'
        if value[0] & 128:
            value = b'\0' + value
        return b'\x02' + bytes([len(value)]) + value

    pair = integer(raw[:32]) + integer(raw[32:])
    return b'\x30' + bytes([len(pair)]) + pair


def openssl_check(executable, folder, public_der, digest, signature):
    key, message, sig = (folder / name for name in ('public.der', 'digest.bin', 'signature.der'))
    key.write_bytes(public_der)
    message.write_bytes(digest)
    sig.write_bytes(signature_der(signature))
    result = subprocess.run(
        [str(executable), 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER',
         '-inkey', str(key), '-in', str(message), '-sigfile', str(sig)],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError('OpenSSL invocation failed: ' + result.stderr[:500])
    return result.returncode == 0


def signed_extent(data):
    entries = records(data, b'MC282')  # Includes complete body-CRC and bounds checks.
    start, end = 0x2a0, 0x2ec + len(entries) * 0x5c
    return start, end, entries


def altered_directory(data):
    changed = bytearray(data)
    changed[0x2ec + 0x1c] ^= 1  # First component's signed plaintext digest.
    struct.pack_into('<I', changed, 0x40, zlib.crc32(changed[0x200:]))
    return bytes(changed)


def native_attempt(program, data, reference=True, policy_halfword=None):
    import unicorn as U
    from unicorn.arm_const import (
        UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
        UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
    )

    registers = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
    vm = U.Uc(U.UC_ARCH_ARM, U.UC_MODE_THUMB)
    vm.mem_map(BASE, len(program), U.UC_PROT_READ | U.UC_PROT_EXEC)
    vm.mem_write(BASE, program)
    if policy_halfword is not None:
        if policy_halfword != 1:
            raise ValueError('Only the fixed emulated policy-one control is supported')
        vm.mem_write(POLICY, struct.pack('<H', policy_halfword))
    vm.mem_map(0x05eb0000, 0x800000)
    vm.mem_write(0x05eb0000, program[0x8ae65c:0x8d73d8])
    for address, size in [(CONTEXT, 0x300000), (STACK, 0x20000), (RETURN, 0x1000)]:
        vm.mem_map(address, size)
    vm.mem_map(FIRMWARE, (len(data) + 4095) & ~4095, U.UC_PROT_READ)
    vm.mem_write(FIRMWARE, data)
    result = {'directory_authentication_passed': False, 'directory_gate_reached': False,
              'policy_halfword': struct.unpack_from('<H', program, POLICY - BASE)[0]
                  if policy_halfword is None else policy_halfword,
              'emulated_policy_changed': policy_halfword is not None, 'signature_calls': 0,
              'crc32_bytes_accelerated': 0, 'calls': [], 'native_instructions': 0,
              'payload_decryption_or_programming_executed': False}
    hooks = {}

    def read(address, size):
        return bytes(vm.mem_read(address, size))

    def word(address):
        return struct.unpack('<I', read(address, 4))[0]

    def ret(value=0):
        vm.reg_write(UC_ARM_REG_R0, value & 0xffffffff)
        vm.reg_write(UC_ARM_REG_PC, vm.reg_read(UC_ARM_REG_LR))

    def copy(a, b, c, d):
        if not 0 <= c <= 0x200000:
            raise ValueError('Emulated copy exceeds its bound')
        vm.mem_write(a, read(b, c))
        ret(a)

    def zero(a, b, c, d):
        if not 0 <= b <= 0x200000:
            raise ValueError('Emulated zero-fill exceeds its bound')
        vm.mem_write(a, bytes(b))
        ret(a)

    def signature(a, b, c, d):
        # Observe the actual native SHA/ECDSA call; neither is replaced.
        count = struct.unpack_from('<I', data, 0x2e8)[0]
        expected = hashlib.sha256(data[0x2a0:0x2ec + 0x5c*count]).digest()
        if read(a, 64) != program[POINT - BASE:POINT - BASE + 64] or read(b, 32) != expected:
            raise ValueError('Native hash or public point differs from the independent check')
        if read(c, 64) != data[0x220:0x260]:
            raise ValueError('Native signature source differs')
        result['signature_calls'] += 1
        result['native_sha256_matches_host'] = True

    def code(uc, address, size, user):
        result['native_instructions'] += 1
        if address == RETURN:
            uc.emu_stop()
        elif address == AUTHENTICATED:
            result['directory_gate_reached'] = True
            result['directory_authentication_passed'] = result['signature_calls'] == 1
            result['payload_hash_checks_selected'] = bool(word(uc.reg_read(UC_ARM_REG_SP) + 0xf4))
            uc.emu_stop()
        elif address in hooks:
            hooks[address](*(uc.reg_read(r) for r in registers))

    hooks.update({0x41b4cb4: zero, 0x41b1cb0: copy, 0x41b4d08: copy,
                  0x402af82: signature})
    vm.hook_add(U.UC_HOOK_CODE, code)

    def call(function, *args, count=200000):
        vm.reg_write(UC_ARM_REG_SP, STACK + 0x1ff00)
        vm.reg_write(UC_ARM_REG_LR, RETURN | 1)
        for register, value in zip(registers, (*args, 0, 0, 0, 0)):
            vm.reg_write(register, value)
        before = result['native_instructions']
        try:
            vm.emu_start(function | 1, RETURN, count=count)
        except U.UcError as error:
            raise RuntimeError(f'{error}: native PC={vm.reg_read(UC_ARM_REG_PC):#x}') from error
        pc = vm.reg_read(UC_ARM_REG_PC)
        if pc not in (RETURN, AUTHENTICATED):
            raise RuntimeError(f'Native instruction bound reached at {pc:#x}')
        status = vm.reg_read(UC_ARM_REG_R0) if pc == RETURN else None
        result['calls'].append({'function': hex(function),
                                'result': hex(status) if status is not None else None,
                                'stop_address': hex(pc),
                                'native_instructions': result['native_instructions'] - before})
        return status

    for function, args in (
        (0x4027170, (CONTEXT,)),
        (0x40271aa, (CONTEXT, FIRMWARE, len(data))),
        (0x40271c6, (CONTEXT, SCRATCH, 0x200000)),
        (0x402720e, (CONTEXT,)),
        (0x40271e4, (CONTEXT, 0x05ed1c28, 16)),
    ):
        if call(function, *args) != 0:
            raise ValueError('Native parser setup/header check failed')
    if reference and call(0x4027a9e, CONTEXT, REFERENCE) != 0:
        raise ValueError('Native validation-reference setup failed')

    # Check the exact native CRC representation before accelerating 102 MB of it.
    obj = CONTEXT + 0x1000
    for function, args in ((0x402ab18, (obj,)),
                           (0x402ab64, (obj, FIRMWARE, 64))):
        if call(function, *args) != 0:
            raise ValueError('Native CRC control failed')
    if word(obj + 12) != zlib.crc32(data[:64]) ^ 0xffffffff:
        raise ValueError('Native CRC update representation differs')
    if call(0x402ab70, obj) != 0 or word(obj + 16) != zlib.crc32(data[:64]):
        raise ValueError('Native CRC finalization differs')
    result['crc32_native_prefix_checked'] = True

    def crc32(state, source, length, unused):
        if not 0 <= length <= len(data):
            raise ValueError('CRC acceleration exceeds its bound')
        crc = zlib.crc32(read(source, length), word(state) ^ 0xffffffff) ^ 0xffffffff
        vm.mem_write(state, struct.pack('<I', crc))
        result['crc32_bytes_accelerated'] += length
        ret(0)

    def progress(*args):
        unit = vm.reg_read(UC_ARM_REG_R2)
        total = word(vm.reg_read(UC_ARM_REG_SP) + 0x44)
        if not (0 < unit <= 64 and total == len(data) - 512):
            raise ValueError('Native progress-loop geometry differs')
        vm.reg_write(UC_ARM_REG_R0, max(1, (total + 99*unit - 1) // (99*unit)))

    hooks.update({0x402bfe8: crc32, 0x402773e: progress})
    status = call(0x4027a6a, CONTEXT, 0, count=30000000)
    result['parser_return_status'] = hex(status) if status is not None else None
    result['stop_address'] = hex(vm.reg_read(UC_ARM_REG_PC))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program', type=Path, required=True)
    parser.add_argument('--firmware', type=Path, action='append', required=True)
    parser.add_argument('--openssl', type=Path, default=Path('/usr/bin/openssl'))
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    program = args.program.read_bytes()
    key = public_key(program)
    version = subprocess.check_output([str(args.openssl), 'version'], text=True, timeout=10).strip()
    report = {
        'schema': 1, 'scope': 'Offline GX9 signed-directory authentication; no flashing',
        'verifier_sha256': sha(Path(__file__).read_bytes()),
        'program_sha256': PROGRAM_SHA, 'public_point_sha256': POINT_SHA,
        'public_point_address': hex(POINT), 'validation_reference_address': hex(REFERENCE),
        'public_point_on_p256': True, 'algorithm': 'ECDSA over NIST P-256',
        'digest': 'SHA-256; native verifier interprets its 32 bytes as a little-endian integer',
        'public_coordinates_and_signature_integers': 'little-endian, 32 bytes each',
        'openssl': version, 'camera_or_network_access': False, 'camera_writes': 0,
        'packages': [], 'native_negative_controls': {},
        'limits': [
            'Directory authentication is not the full updater model/version check or flash writer.',
            'Native execution stops before payload decryption and programming.',
            'C memcpy/zero-fill and long CRC32/progress loops are host modeled; SHA-256 and ECDSA execute natively.',
            'No alternate boot path, service writer or modified camera installation is demonstrated.',
        ],
    }
    originals = []
    with tempfile.TemporaryDirectory(prefix='gx9-signature-check-') as folder:
        folder = Path(folder)
        for path in args.firmware:
            data = path.read_bytes()
            identity = sha(data)
            if identity not in PACKAGE_SHAS:
                raise ValueError('Expected one of the two pinned official update binaries')
            start, end, entries = signed_extent(data)
            digest = hashlib.sha256(data[start:end]).digest()
            signature = data[0x220:0x260]
            if not openssl_check(args.openssl, folder, key, digest[::-1], signature):
                raise ValueError('Original update signature did not verify')
            changed = altered_directory(data)
            signed_extent(changed)  # Changed metadata still has a valid CRC/bounds.
            changed_digest = hashlib.sha256(changed[start:end]).digest()
            changed_signature = bytes([signature[0] ^ 1]) + signature[1:]
            controls = {
                'changed_directory_with_correct_body_crc_rejected': not openssl_check(
                    args.openssl, folder, key, changed_digest[::-1], signature),
                'changed_signature_rejected': not openssl_check(
                    args.openssl, folder, key, digest[::-1], changed_signature),
                'unreversed_digest_rejected': not openssl_check(
                    args.openssl, folder, key, digest, signature),
            }
            if not all(controls.values()):
                raise ValueError('Independent signature negative control failed')
            row = {'version': PACKAGE_SHAS[identity], 'firmware_sha256': identity,
                   'directory_records': len(entries), 'signed_file_start': hex(start),
                   'signed_file_end_exclusive': hex(end), 'signed_bytes': end - start,
                   'signed_sha256': digest.hex(), 'signature_file_start': '0x220',
                   'signature_bytes': 64, 'signature_verified': True,
                   'signed_component_plaintext_hashes': len(entries), 'controls': controls}
            if args.native:
                row['native'] = native_attempt(program, data)
                if not row['native']['directory_authentication_passed'] or row['native']['signature_calls'] != 1:
                    raise ValueError('Native original directory authentication failed')
            report['packages'].append(row)
            originals.append(data)
            args.out.write_text(json.dumps(report, indent=2) + '\n')
            print('GX9 ' + row['version'] + ': signature verified' +
                  (' independently and in native ARM code' if args.native else ''), flush=True)
        if args.native:
            data = originals[0]
            controls = {
                'changed_directory_correct_crc': native_attempt(program, altered_directory(data)),
                'missing_public_reference': native_attempt(program, data, reference=False),
            }
            changed = bytearray(data)
            changed[0x1000] ^= 1  # Body corruption, with original CRC left intact.
            controls['changed_body_incorrect_crc'] = native_attempt(program, bytes(changed))
            for name, control in controls.items():
                if control['directory_gate_reached'] or control['parser_return_status'] in (None, '0x0'):
                    raise ValueError('Native negative control failed: ' + name)
            report['native_negative_controls'] = controls
            policy = native_attempt(program, altered_directory(data), reference=False, policy_halfword=1)
            if (not policy['directory_gate_reached'] or policy['signature_calls'] != 0
                    or policy['payload_hash_checks_selected']):
                raise ValueError('Native emulated policy-one control differs')
            report['emulated_policy_one_control'] = policy
            report['policy_halfword_link_address'] = hex(POLICY)
            report['policy_control_live_camera_writes'] = 0
            report['unicorn_version'] = __import__('unicorn').__version__
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('Signature controls passed; no camera access or firmware installation.')


if __name__ == '__main__':
    main()
