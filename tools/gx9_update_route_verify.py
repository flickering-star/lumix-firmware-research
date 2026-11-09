#!/usr/bin/env python3
"""Check GX9 updater stages with native ARM code and disposable local fixtures.

Runs model/version checks, the complete parser on a synthetic clear component,
and the sector-write wrapper with a simulated controller. Does not create an
installation file or access a camera, USB, network, SD card or real flash.
Requires Unicorn 2.1.4 and hash-pinned local firmware inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

import unicorn as U
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
)

from gx9_update_auth_verify import PROGRAM_SHA, PACKAGE_SHAS, BASE, POLICY, REFERENCE
from tz30_control_verify import records


CONTEXT, SCRATCH = 0x30000000, 0x30010000
STACK, RETURN, FIRMWARE = 0x10000000, 0x20000000, 0x50000000
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Machine:
    def __init__(self, program, data):
        if sha(program) != PROGRAM_SHA:
            raise ValueError('Expected the verified 1.4 program component')
        self.vm = U.Uc(U.UC_ARCH_ARM, U.UC_MODE_THUMB)
        self.vm.mem_map(BASE, len(program), U.UC_PROT_READ | U.UC_PROT_EXEC)
        self.vm.mem_write(BASE, program)
        self.vm.mem_map(0x05eb0000, 0x800000)
        self.vm.mem_write(0x05eb0000, program[0x8ae65c:0x8d73d8])
        for address, size in [(CONTEXT, 0x300000), (STACK, 0x20000), (RETURN, 0x1000)]:
            self.vm.mem_map(address, size)
        self.vm.mem_map(FIRMWARE, (len(data) + 4095) & ~4095, U.UC_PROT_READ)
        self.vm.mem_write(FIRMWARE, data)
        self.instructions, self.calls = 0, []
        self.hooks = {0x41b4cb4: self.zero, 0x41b1cb0: self.copy, 0x41b4d08: self.copy}
        self.vm.hook_add(U.UC_HOOK_CODE, self.code)

    def read(self, address, size):
        return bytes(self.vm.mem_read(address, size))

    def word(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def put_word(self, address, value):
        self.vm.mem_write(address, struct.pack('<I', value))

    def ret(self, value=0):
        self.vm.reg_write(UC_ARM_REG_R0, value & 0xffffffff)
        self.vm.reg_write(UC_ARM_REG_PC, self.vm.reg_read(UC_ARM_REG_LR))

    def zero(self, a, b, c, d):
        if not 0 <= b <= 0x200000:
            raise ValueError('Emulated zero-fill exceeds bound')
        self.vm.mem_write(a, bytes(b))
        self.ret(a)

    def copy(self, a, b, c, d):
        if not 0 <= c <= 0x200000:
            raise ValueError('Emulated copy exceeds bound')
        self.vm.mem_write(a, self.read(b, c))
        self.ret(a)

    def code(self, vm, address, size, user):
        self.instructions += 1
        if address == RETURN:
            vm.emu_stop()
        elif address in self.hooks:
            self.hooks[address](*(vm.reg_read(register) for register in REGS))

    def call(self, function, *args, count=300000):
        self.vm.reg_write(UC_ARM_REG_SP, STACK + 0x1ff00)
        self.vm.reg_write(UC_ARM_REG_LR, RETURN | 1)
        for register, value in zip(REGS, (*args, 0, 0, 0, 0)):
            self.vm.reg_write(register, value)
        before = self.instructions
        try:
            self.vm.emu_start(function | 1, RETURN, count=count)
        except U.UcError as error:
            raise RuntimeError(f'{error}: native PC={self.vm.reg_read(UC_ARM_REG_PC):#x}') from error
        if self.vm.reg_read(UC_ARM_REG_PC) != RETURN:
            raise RuntimeError('Native instruction bound reached')
        result = self.vm.reg_read(UC_ARM_REG_R0)
        self.calls.append({'function': hex(function), 'result': hex(result),
                           'native_instructions': self.instructions - before})
        return result


def fixture(original):
    data = bytearray(b'\xff' * 8192)
    data[:0x200] = original[:0x200]
    data[0x200:0x2ec] = original[0x200:0x2ec]
    struct.pack_into('<I', data, 0x3c, len(data) - 512)
    data[0x2a0:0x2e0] = data[:0x40]
    struct.pack_into('<I', data, 0x2e8, 1)
    payload = (b'GX9 OFFLINE PARSER CONTROL\0' * 180)[:4096].ljust(4096, b'\0')
    data[0x1000:0x2000] = payload
    struct.pack_into('<12s4I32s16s16s', data, 0x2ec, b'program', 0xe00, 4096,
                     0x80000, 2, hashlib.sha256(payload).digest(), bytes(16), bytes(16))
    struct.pack_into('<I', data, 0x40, zlib.crc32(data[512:]))
    return bytes(data)


def parse(program, data, policy):
    machine = Machine(program, data)
    machine.vm.mem_write(POLICY, struct.pack('<H', policy))
    for function, args in (
        (0x4027170, (CONTEXT,)),
        (0x40271aa, (CONTEXT, FIRMWARE, len(data))),
        (0x40271c6, (CONTEXT, SCRATCH, 0x200000)),
        (0x402720e, (CONTEXT,)),
        (0x40271e4, (CONTEXT, 0x05ed1c28, 16)),
        (0x4027a9e, (CONTEXT, REFERENCE)),
    ):
        if machine.call(function, *args) != 0:
            raise ValueError('Native parser setup failed')
    status = machine.call(0x4027a6a, CONTEXT, 0, count=30000000)
    count = machine.call(0x4027ab6, CONTEXT) if status == 0 else None
    return {'policy_halfword': policy, 'native_parser_status': hex(status),
            'directory_records': count, 'native_instructions': machine.instructions,
            'calls': machine.calls, 'crc_sha_and_signature_code_replaced': False}


def version_checks(program, v14, v15):
    current = struct.unpack_from('<H', v14, 0x1c)[0]
    type_zero = bytearray(v14[:512])
    type_zero[0x20] &= 0xf0
    wrong_model = bytearray(v15[:512])
    wrong_model[12:28] = b'OTHER_MODEL\0\0\0\0\0'
    result = []
    for name, header, expected in (
        ('same-version-original', v14[:512], 0x80000064),
        ('newer-version-original', v15[:512], 0),
        ('same-version-header-type-zero', bytes(type_zero), 0),
        ('different-model', bytes(wrong_model), 0x80000064),
    ):
        machine = Machine(program, header)
        params = CONTEXT + 0x1000
        machine.put_word(params + 0x18, current)
        status = machine.call(0x4015762, FIRMWARE, params, 0)
        if status != expected:
            raise ValueError('Native model/version control differs: ' + name)
        result.append({'control': name, 'emulated_current_version_parameter': hex(current),
                       'incoming_version': hex(struct.unpack_from('<H', header, 0x1c)[0]),
                       'header_type_low_nibble': header[0x20] & 15,
                       'native_status': hex(status), 'calls': machine.calls})
    return result


def sector_wrapper(program, data, fail=False):
    machine = Machine(program, data)
    control = 0x0614ee0c
    machine.vm.mem_write(0x05ecc118, b'\x01')  # Already initialized, simulated device.
    requests, locks = [], []
    output = bytearray(b'\xff' * 4096)

    def lock(a, *rest):
        locks.append(a)
        machine.ret(0)

    def controller(*args):
        if machine.read(control + 12, 1) != b'\x30':
            raise ValueError('Unexpected controller operation')
        remaining, sector, source = (machine.word(control + i) for i in (0, 4, 8))
        if not 1 <= remaining <= 8 or sector != 0x400 + len(requests):
            raise ValueError('Sector-wrapper transfer geometry differs')
        if source != FIRMWARE + 0x1000 + len(requests) * 512:
            raise ValueError('Sector-wrapper source advancement differs')
        payload = machine.read(source, 512)
        requests.append({'sector': sector, 'source_offset': hex(source - FIRMWARE),
                         'bytes': 512, 'sha256': sha(payload), 'completion_injected_error': fail})
        if fail:
            machine.ret(1)
            return
        at = (sector - 0x400) * 512
        output[at:at + 512] = payload
        machine.put_word(control, remaining - 1)
        machine.put_word(control + 4, sector + 1)
        machine.ret(0)

    machine.hooks.update({0x41b1da8: lock, 0x41b4c70: lock,
                          0x41ff868: lambda *args: machine.ret(0),
                          0x3fb4154: controller,
                          0x3fb428a: lambda *args: machine.ret(0),
                          0x3fb43b0: lambda *args: machine.ret(0),
                          0x41f2ce4: lambda *args: machine.ret(0)})
    status = machine.call(0x41ffd96, 0x400, 8, FIRMWARE + 0x1000)
    if locks != [0xcc, 0xcc] or status != (0xffffffff if fail else 0):
        raise ValueError('Native write-wrapper status or locking differs')
    if fail:
        if len(requests) != 1 or output != b'\xff' * 4096:
            raise ValueError('Injected failure did not stop the wrapper')
    elif len(requests) != 8 or bytes(output) != data[0x1000:0x2000]:
        raise ValueError('Native sector-wrapper source/count mapping differs')
    return {'native_entry': '0x041ffd96', 'native_status': hex(status),
            'sector_bytes': 512, 'first_sector': '0x400', 'byte_offset': '0x80000',
            'controller_completion_model': 'One simulated sector completed per controller invocation',
            'controller_and_lock_operations_mocked': True, 'requests': requests,
            'simulated_output_sha256': sha(output), 'calls': machine.calls}


def startup_scatter(program, postboots, initial_policy):
    machine = Machine(program, b'local fixture')
    joined = b''.join(postboots)
    machine.vm.mem_map(0x047f0000, len(joined), U.UC_PROT_READ | U.UC_PROT_EXEC)
    machine.vm.mem_write(0x047f0000, joined)
    machine.vm.mem_map(0x07df0000, 0xcc0000)
    machine.vm.mem_map(0x20000, 0x1000)
    table = [struct.unpack_from('<4I', program, at) for at in range(0x100, 0x160, 16)]
    for source, destination, length, helper in table:
        if helper not in (0x03e800c8, 0x03e800e4):
            raise ValueError('Native scatter helper differs')
        # Nonzero sentinels make a missing clear/copy visible.
        machine.vm.mem_write(destination, b'\xa5' * length)
    machine.vm.mem_write(POLICY, struct.pack('<H', initial_policy))
    writes, checkpoint = [], []

    def observe(uc, access, address, size, value, user):
        if address < POLICY + 2 and address + size > POLICY:
            writes.append({'address': hex(address), 'bytes': size})

    def stop(*args):
        checkpoint.append(True)
        machine.vm.emu_stop()

    machine.vm.hook_add(U.UC_HOOK_MEM_WRITE, observe, begin=0x03f18000, end=0x03f183ff)
    machine.hooks[0x04319790] = stop
    machine.vm.reg_write(UC_ARM_REG_SP, STACK + 0x1ff00)
    machine.vm.reg_write(UC_ARM_REG_LR, RETURN | 1)
    machine.vm.emu_start(0x03e80095, RETURN, count=10000000)
    if not checkpoint or machine.vm.reg_read(UC_ARM_REG_PC) != 0x04319790:
        raise ValueError('Native startup did not reach its ThreadX continuation checkpoint')
    result = []
    for source, destination, length, helper in table:
        expected = machine.read(source, length) if helper == 0x03e800c8 else bytes(length)
        actual = machine.read(destination, length)
        if actual != expected:
            raise ValueError('Native initialized-data copy or zero-fill differs')
        result.append({'source': hex(source), 'destination': hex(destination), 'bytes': length,
                       'helper': hex(helper), 'entire_destination_verified': True,
                       'destination_sha256': sha(actual)})
    after = int.from_bytes(machine.read(POLICY, 2), 'little')
    if after != initial_policy or writes:
        raise ValueError('Native scatter initialization overwrote the policy field')
    return {'native_entry': '0x03e80094', 'stop_before_threadx': '0x04319790',
            'checkpoint_not_function_return': True, 'native_instructions': machine.instructions,
            'initial_policy': initial_policy, 'policy_after_initialization': after,
            'policy_writes_observed': writes, 'scatter_records': result,
            'scope': 'Main C runtime scatter initialization only; not a complete board/loader/RTOS boot'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program', type=Path, required=True)
    parser.add_argument('--v14', type=Path, required=True)
    parser.add_argument('--v15', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    program, v14, v15 = (p.read_bytes() for p in (args.program, args.v14, args.v15))
    if sha(program) != PROGRAM_SHA or PACKAGE_SHAS.get(sha(v14)) != '1.4' or PACKAGE_SHAS.get(sha(v15)) != '1.5':
        raise ValueError('Pinned input identity differs')
    data = fixture(v14)
    wrong_hash = bytearray(data)
    wrong_hash[0x308] ^= 1
    struct.pack_into('<I', wrong_hash, 0x40, zlib.crc32(wrong_hash[512:]))
    wrong_crc = bytearray(data)
    wrong_crc[0x40] ^= 1
    report = {
        'schema': 1, 'scope': 'Offline native updater-stage controls with synthetic data and mocked controller',
        'verifier_sha256': sha(Path(__file__).read_bytes()), 'program_sha256': PROGRAM_SHA,
        'v14_sha256': sha(v14), 'v15_sha256': sha(v15), 'unicorn_version': U.__version__,
        'camera_or_network_access': False, 'physical_writes': 0, 'installation_file_created': False,
        'fixture_bytes': len(data), 'fixture_sha256': sha(data), 'fixture_component_flags': 2,
        'fixture_payload': '4096 bytes of ASCII emulator-control data, never executed',
        'version_checks': version_checks(program, v14, v15), 'parser_checks': [],
    }
    for name, raw, policy, expected in (
        ('clear-component-policy-one', data, 1, 0),
        ('wrong-plaintext-hash-policy-one', bytes(wrong_hash), 1, 0),
        ('wrong-body-crc-policy-one', bytes(wrong_crc), 1, 0x80000064),
        ('same-fixture-policy-zero', data, 0, 0x80000066),
    ):
        row = parse(program, raw, policy)
        if row['native_parser_status'] != hex(expected):
            raise ValueError('Full native parser control differs: ' + name)
        row['control'] = name
        report['parser_checks'].append(row)
        args.out.write_text(json.dumps(report, indent=2) + '\n')
        print(name + ': native status ' + hex(expected), flush=True)
    report['sector_wrapper'] = sector_wrapper(program, data)
    report['sector_wrapper_error'] = sector_wrapper(program, data, fail=True)
    expected = {row['name']: row['field32'] for row in records(v14, b'MC282')}
    postboots = []
    for number in range(1, 6):
        name = 'postboot' + str(number)
        image = (args.program.parent / (name + '.plaintext.bin')).read_bytes()
        if sha(image) != expected[name]:
            raise ValueError('Postboot source identity differs: ' + name)
        postboots.append(image)
    report['startup_scatter'] = [startup_scatter(program, postboots, value) for value in (0, 1)]
    report['limits'] = [
        'Synthetic fixture acceptance is not acceptance or installation of a modified camera program.',
        'Model/version parameters are controlled emulator inputs, not a fresh camera query.',
        'CRC32, SHA-256, signature and parser code execute natively; only C copy/zero helpers are modeled there.',
        'The sector transfer wrapper runs natively; controller, completion, locks and logging are mocked.',
        'No NAND/NOR erase/program algorithm, bad-block handling, complete updater or boot sequence is emulated.',
        'Native scatter initialization retains policy one; earlier loader behavior and later startup remain separate work.',
    ]
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('Native updater-stage controls passed; no camera access or installation file.')


if __name__ == '__main__':
    main()
