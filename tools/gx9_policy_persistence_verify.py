#!/usr/bin/env python3
"""Trace the GX9 fixed-settings policy through native update preparation/reload.

Offline only. Native selectors, preprocessing and sector wrappers execute in
Unicorn; NAND controller completions and locks are simulated. This is not a
complete board boot or physical flash-programming test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import unicorn as U
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R1, UC_ARM_REG_R3, UC_ARM_REG_PC, UC_ARM_REG_R0

from gx9_update_route_verify import Machine, FIRMWARE, STACK, RETURN
from gx9_update_auth_verify import PROGRAM_SHA, POLICY
from gx9_update_decode import MAIN_RAM_SHA


FIX_SHA = 'a28f6659b3264b0f1525872d9571f6e6d6d5f80e7dc907aefc919dbdf525ffe0'
FIX_OFFSET = 0x1801a
FIX_RAM, FIX_FLASH, FIX_SECTOR = 0x03f00000, 0x40e00000, 0x7000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def preprocess(program, payload, current):
    machine = Machine(program, payload)
    machine.vm.mem_protect(FIRMWARE, 0x20000, U.UC_PROT_READ | U.UC_PROT_WRITE)
    machine.vm.mem_write(FIX_RAM, current)
    machine.hooks[0x41b1cac] = machine.copy
    sp = STACK + 0x1fd00
    machine.vm.reg_write(UC_ARM_REG_SP, sp)
    machine.vm.reg_write(UC_ARM_REG_LR, RETURN | 1)
    machine.put_word(sp, 4)
    machine.put_word(sp + 0x80, FIRMWARE)
    reached = []

    def stop(*args):
        reached.append(True)
        machine.vm.emu_stop()

    machine.hooks[0x040153f0] = stop
    machine.vm.emu_start(0x04015371, RETURN, count=100000)
    if not reached:
        raise ValueError('Fixed-settings preprocessing did not reach its next-stage checkpoint')
    actual = machine.read(FIRMWARE, 0x20000)
    expected = bytearray(payload)
    fields = [(0x1c020, 16), (0x1c040, 6), (0x17e00, 512), (0x1fe00, 512)]
    for at, size in fields:
        expected[at:at + size] = current[at:at + size]
    if actual != bytes(expected) or actual[FIX_OFFSET:FIX_OFFSET + 2] != payload[FIX_OFFSET:FIX_OFFSET + 2]:
        raise ValueError('Native identity/sector preservation or candidate policy differs')
    return actual, {'native_entry_subsequence': '0x04015370', 'stop_address': '0x040153f0',
                    'header_type': 4, 'copied_live_fields': [{'offset': hex(a), 'bytes': n} for a, n in fields],
                    'payload_policy_before': int.from_bytes(payload[FIX_OFFSET:FIX_OFFSET + 2], 'little'),
                    'live_policy': int.from_bytes(current[FIX_OFFSET:FIX_OFFSET + 2], 'little'),
                    'payload_policy_after': int.from_bytes(actual[FIX_OFFSET:FIX_OFFSET + 2], 'little'),
                    'full_expected_result_matches': True, 'native_instructions': machine.instructions}


class Controller:
    """One simulated sector completion per actual native controller invocation."""
    def __init__(self, store, fail=False):
        self.store = bytearray(store)
        self.fail = fail
        self.requests = []

    def attach(self, machine):
        machine.vm.mem_write(0x05ecc118, b'\x01')

        def controller(*args):
            state = 0x0614ee0c
            left, sector, address = (machine.word(state + i) for i in (0, 4, 8))
            operation = machine.read(state + 12, 1)[0]
            if not FIX_SECTOR <= sector < FIX_SECTOR + 256 or not 1 <= left <= 256:
                raise ValueError('Simulated I/O escaped the fixed settings bank')
            if operation not in (0x20, 0x30):
                raise ValueError('Unexpected simulated controller operation')
            self.requests.append({'operation': operation, 'sector': sector, 'buffer': address})
            if self.fail:
                machine.ret(1)
                return
            at = (sector - FIX_SECTOR) * 512
            if operation == 0x30:
                self.store[at:at + 512] = machine.read(address, 512)
            else:
                machine.vm.mem_write(address, bytes(self.store[at:at + 512]))
            machine.put_word(state, left - 1)
            machine.put_word(state + 4, sector + 1)
            machine.ret(0)

        machine.hooks.update({
            0x3fb4154: controller, 0x3fb428a: lambda *args: machine.ret(0),
            0x3fb43b0: lambda *args: machine.ret(0), 0x41f2ce4: lambda *args: machine.ret(0),
            0x41b1da8: lambda *args: machine.ret(0), 0x41b4c70: lambda *args: machine.ret(0),
            0x41ff868: lambda *args: machine.ret(0),
        })


def reload_bank(program, stored, initial_policy):
    machine = Machine(program, b'local fixture')
    machine.vm.mem_write(POLICY, struct.pack('<H', initial_policy))
    controller = Controller(stored)
    controller.attach(machine)
    status = machine.call(0x0426ad4e, 3)
    actual = machine.read(FIX_RAM, 0x20000)
    if status or actual != stored or len(controller.requests) != 256:
        raise ValueError('Native fixed-bank read did not reproduce the complete stored bank')
    if [r['sector'] for r in controller.requests] != list(range(FIX_SECTOR, FIX_SECTOR + 256)):
        raise ValueError('Native read-sector advancement differs')
    if [r['buffer'] for r in controller.requests] != [FIX_RAM + 512*i for i in range(256)]:
        raise ValueError('Native read-buffer advancement differs')
    return {'native_entry': '0x0426ad4e', 'bank_id': 3, 'flash_api': '0x041ffeca',
            'virtual_flash_source': hex(FIX_FLASH), 'destination': hex(FIX_RAM),
            'initial_policy': initial_policy,
            'policy_after_reload': int.from_bytes(actual[FIX_OFFSET:FIX_OFFSET + 2], 'little'),
            'entire_stored_bank_reloaded': True, 'sector_completions': 256,
            'native_instructions': machine.instructions}


def write_from_update(program, payload, original_store, fail=False):
    machine = Machine(program, payload)
    controller = Controller(original_store, fail)
    controller.attach(machine)
    sp = STACK + 0x1fd00
    machine.vm.reg_write(UC_ARM_REG_SP, sp)
    machine.vm.reg_write(UC_ARM_REG_LR, RETURN | 1)
    machine.vm.reg_write(UC_ARM_REG_R1, 0x20000)
    machine.vm.reg_write(UC_ARM_REG_R3, 0x1a40000)
    machine.put_word(sp + 0x80, FIRMWARE)
    machine.put_word(sp + 0x150, 0x00c40000)
    reached = []

    def stop(*args):
        reached.append(True)
        machine.vm.emu_stop()

    machine.hooks[0x04015568] = stop
    machine.vm.emu_start(0x0401555b, RETURN, count=300000)
    if not reached:
        raise ValueError('Native update transfer did not reach its result check')
    status = machine.vm.reg_read(UC_ARM_REG_R0)
    expected_status = 0xffffffff if fail else 0
    if status != expected_status:
        raise ValueError('Native transfer error/success result differs')
    if fail:
        if len(controller.requests) != 1 or bytes(controller.store) != original_store:
            raise ValueError('Failed first-sector completion was not propagated')
    else:
        if bytes(controller.store) != payload or len(controller.requests) != 256:
            raise ValueError('Native update transfer did not reproduce the entire bank')
        if [r['sector'] for r in controller.requests] != list(range(FIX_SECTOR, FIX_SECTOR + 256)):
            raise ValueError('Native update destination advancement differs')
        if [r['buffer'] for r in controller.requests] != [FIRMWARE + 512*i for i in range(256)]:
            raise ValueError('Native update source advancement differs')
    return bytes(controller.store), {'native_subsequence': '0x0401555a', 'stop_address': '0x04015568',
                                    'record_destination': '0x1a40000', 'storage_boundary': '0xc40000',
                                    'logical_byte_offset': '0xe00000', 'first_sector': '0x7000',
                                    'sector_bytes': 512, 'sector_completions': len(controller.requests),
                                    'native_result': hex(status), 'simulated_store_sha256': sha(controller.store),
                                    'native_instructions': machine.instructions}


def verify(program, fix, ram):
    if sha(program) != PROGRAM_SHA or sha(fix) != FIX_SHA or sha(ram) != MAIN_RAM_SHA:
        raise ValueError('Pinned official or captured source identity differs')
    if program[0x80000:0xa0000] != fix:
        raise ValueError('Expected the complete program/FIX shadow duplication')
    live = ram[0x80000:0xa0000]
    candidate = fix[:FIX_OFFSET] + b'\x01' + fix[FIX_OFFSET + 1:]
    live_one = live[:FIX_OFFSET] + b'\x01' + live[FIX_OFFSET + 1:]
    stock_prepared, stock = preprocess(program, fix, live_one)
    prepared, patched = preprocess(program, candidate, live_one)
    if stock_prepared[FIX_OFFSET] != 0 or prepared[FIX_OFFSET] != 1:
        raise ValueError('Native preprocessor does not preserve the tested policy source')
    program_only = reload_bank(program, fix, 1)
    if program_only['policy_after_reload'] != 0:
        raise ValueError('Stock fixed bank unexpectedly retained the program-only policy patch')
    stored, writing = write_from_update(program, prepared, live)
    _, failure = write_from_update(program, prepared, live, fail=True)
    reloaded = reload_bank(program, stored, 0)
    if reloaded['policy_after_reload'] != 1:
        raise ValueError('Written candidate policy did not survive a fresh native bank reload')
    return {
        'schema': 1, 'scope': 'Native fixed-settings policy persistence with simulated NAND controller completions',
        'verifier_sha256': sha(Path(__file__).read_bytes()), 'program_sha256': PROGRAM_SHA,
        'fixed_component_sha256': FIX_SHA, 'captured_ram_sha256': MAIN_RAM_SHA,
        'camera_or_network_access': False, 'physical_flash_writes': 0,
        'policy_program_offset': '0x9801a', 'policy_fixed_bank_offset': '0x1801a',
        'whole_program_fixed_shadow_equals_component': True,
        'stock_payload_preprocessing': stock, 'candidate_payload_preprocessing': patched,
        'program_only_patch_after_bank_reload': program_only,
        'native_update_fixed_bank_write': writing, 'injected_controller_failure': failure,
        'fresh_bank_reload_after_simulated_update': reloaded,
        'prepared_fixed_bank_sha256': sha(prepared),
        'all_owner_fixed_bank_differences_preserved_by_native_preprocessing':
            all(prepared[i] == live[i] for i in range(len(fix)) if live[i] != fix[i] and i != FIX_OFFSET),
        'limits': [
            'Controller, DMA completions, locks and logging are modeled; no physical NAND was programmed.',
            'Preprocessing and record-transfer subsequences are not the entire updater.',
            'This verifies fixed-bank reload, not the complete earlier/later boot sequence or all validation rules.',
            'The first program-only candidate is insufficient under the demonstrated fixed-bank reload.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program', type=Path, required=True)
    parser.add_argument('--eep-fix', type=Path, required=True)
    parser.add_argument('--main-ram', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.program.read_bytes(), args.eep_fix.read_bytes(), args.main_ram.read_bytes())
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('Native fixed-bank preparation, 256-sector transfer and fresh policy-one reload verified; controller simulated.')


if __name__ == '__main__':
    main()
