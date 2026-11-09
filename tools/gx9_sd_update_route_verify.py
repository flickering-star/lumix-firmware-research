#!/usr/bin/env python3
"""Trace GX9 1.4 alternate SD updater filename selection with native ARM code.

Runs model-tag construction, formatting, file selection and a decoded key-mask
predicate. Task/LED/media/file operations are modeled; execution stops before
the updater. No camera, real filesystem mount, SD, network or flash operation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

import unicorn as U
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

from gx9_update_route_verify import Machine, CONTEXT, STACK, RETURN, POLICY, sha


ENTRY, UPDATER = 0x03f7bf94, 0x04014f80
NORMAL, EXTENDED = 'a:\\MC282.upd', 'a:\\MC282e.upd'


def cstring(machine, address):
    data = machine.read(address, 64).split(b'\0', 1)[0]
    return data.decode('ascii')


def filename_selection(program, files, initial_policy):
    machine = Machine(program, b'offline SD route fixture')
    machine.vm.mem_write(POLICY, struct.pack('<H', initial_policy))
    checks, tasks, delays, checkpoint, writes = [], [], [], [], []

    def task_control(task, *unused):
        tasks.append(task)
        machine.ret(0)

    def idle(a, *unused):
        if a != 0x3ffff:
            raise ValueError('Native idle-loop count differs')
        delays.append(a)
        # One iteration preserves the loop's final registers/stack-byte value.
        # Only the count of repeated identical stack stores is accelerated.
        machine.vm.reg_write(UC_ARM_REG_R0, 1)

    def exists(address, *unused):
        name = cstring(machine, address)
        if name not in (NORMAL, EXTENDED):
            raise ValueError('Unexpected native SD filename')
        checks.append(name)
        machine.ret(1 if name in files else 0)

    def updater(params, *unused):
        path = cstring(machine, machine.word(params))
        checkpoint.append({'stage': 'before-updater', 'path': path,
                           'caller_kind_parameter': machine.word(params + 0xc),
                           'caller_words_0x10_0x14': [machine.word(params + offset)
                                                     for offset in (0x10, 0x14)]})
        machine.vm.emu_stop()

    def no_file(*unused):
        checkpoint.append({'stage': 'before-cleanup-no-file'})
        machine.vm.emu_stop()

    def forbidden(*unused):
        raise ValueError('SD selection unexpectedly reached bank reload or flash I/O')

    def observe(vm, access, address, size, value, user):
        if address < POLICY + 2 and address + size > POLICY:
            writes.append({'address': hex(address), 'bytes': size})

    machine.hooks.update({0x040d4e94: task_control,
                          0x0412c6c0: lambda *args: machine.ret(0),
                          0x0412c6da: lambda *args: machine.ret(0),
                          0x03f7bfc6: idle,
                          0x04179d02: lambda *args: machine.ret(0),
                          0x040e5a38: exists,
                          UPDATER: updater, 0x03f7c0e0: no_file,
                          0x041ffff0: forbidden, 0x0426ad4e: forbidden,
                          0x041ffdba: forbidden, 0x041ffd96: forbidden,
                          0x03fb4154: forbidden})
    machine.vm.hook_add(U.UC_HOOK_MEM_WRITE, observe)
    machine.vm.reg_write(UC_ARM_REG_SP, STACK + 0x1ff00)
    machine.vm.reg_write(UC_ARM_REG_LR, RETURN | 1)
    machine.vm.emu_start(ENTRY | 1, RETURN, count=200000)
    if (len(checkpoint) != 1 or tasks != list(range(2, 0xed))
            or len(delays) != 63 or writes):
        raise ValueError('Native SD selection/task/idle/policy controls differ')
    selected = EXTENDED if EXTENDED in files else NORMAL if NORMAL in files else None
    if selected:
        if (machine.vm.reg_read(UC_ARM_REG_PC) != UPDATER
                or checkpoint[0]['path'] != selected
                or checkpoint[0]['caller_kind_parameter'] != (3 if selected == EXTENDED else 2)
                or checkpoint[0]['caller_words_0x10_0x14'] != [1, 1]):
            raise ValueError('Native updater selection parameters differ')
    elif machine.vm.reg_read(UC_ARM_REG_PC) != 0x03f7c0e0:
        raise ValueError('Missing-file route did not reach the expected cleanup checkpoint')
    if machine.read(POLICY, 2) != struct.pack('<H', initial_policy):
        raise ValueError('Native selection changed the live policy')
    return {'present_files': sorted(files), 'filename_checks_in_order': checks,
            'checkpoint': checkpoint[0], 'checkpoint_is_not_function_return': True,
            'initial_and_final_policy': initial_policy, 'policy_writes': writes,
            'task_control_requests': len(tasks), 'task_ID_range': ['0x2', '0xec'],
            'accelerated_idle_loops': len(delays), 'native_instructions': machine.instructions,
            'native_model_tag_and_sprintf_executed': True, 'updater_executed': False}


def key_gate(program, masks, media, expected):
    machine = Machine(program, b'offline key-gate fixture')
    queried = []

    def result(value, name):
        def callback(*args):
            queried.append(name)
            machine.ret(value)
        return callback

    machine.hooks.update({0x041b60f4: result(masks[0], 'converter-0x041b60f4'),
                          0x041b579e: result(masks[1], 'converter-0x041b579e'),
                          0x041b582c: result(masks[2], 'converter-0x041b582c'),
                          0x041e7e3c: result(media, 'media/GPIO-predicate-0x041e7e3c')})
    actual = machine.call(0x041b5de2)
    if actual != expected:
        raise ValueError('Native decoded-key mask predicate differs')
    return {'decoded_masks': [hex(mask) for mask in masks], 'modeled_media_predicate': media,
            'native_result': actual, 'native_instructions': machine.instructions,
            'modeled_inputs_queried': queried}


def raw_adc_gate(program, missing, media, expected):
    machine = Machine(program, b'offline raw ADC gate fixture')
    # Centers read from the original fixed-bank calibration and native fixed range.
    raw = [int.from_bytes(machine.read(0x03f191ae, 2), 'little'), 0x183,
           int.from_bytes(machine.read(0x03f191b0, 2), 'little')]
    if missing is not None:
        raw[missing] = 0xffff
    machine.vm.mem_write(0x0621933c + 0x1e, struct.pack('<3H', *raw))
    machine.hooks[0x041e7e3c] = lambda *args: machine.ret(media)
    actual = machine.call(0x041b5de2)
    if actual != expected:
        raise ValueError('Native raw ADC conversion/gate differs')
    return {'raw_ADC_halfwords_at_0x0621935a': [hex(value) for value in raw],
            'missing_channel': missing, 'modeled_media_predicate': media,
            'native_result': actual, 'key_converters_replaced': False,
            'native_instructions': machine.instructions}


def verify(program):
    machine = Machine(program, b'offline model-tag fixture')
    machine.call(0x041b6128, CONTEXT)
    model = cstring(machine, CONTEXT + 0x20)
    if model != 'MC282':
        raise ValueError('Native update model tag differs')
    return {'schema': 1, 'scope': 'Native alternate SD updater selection, not SD code boot or installation',
            'verifier_sha256': sha(Path(__file__).read_bytes()), 'program_sha256': sha(program),
            'native_model_tag': model, 'entry': hex(ENTRY), 'updater_checkpoint': hex(UPDATER),
            'selection_controls': [filename_selection(program, present, policy)
                                   for present, policy in ((set(), 0), ({NORMAL}, 0),
                                                           ({EXTENDED}, 0),
                                                           ({NORMAL, EXTENDED}, 1))],
            'decoded_key_gate_entry': '0x041b5de2',
            'decoded_key_required_bits': '0x508',
            'key_gate_controls': [key_gate(program, masks, media, expected)
                                  for masks, media, expected in (
                                      ((0x500, 8, 0), 1, 1), ((0x500, 0, 0), 1, 0),
                                      ((0x508, 0, 0), 0, 0), ((0x508, 0x1000, 0), 1, 1))],
            'raw_ADC_gate_controls': [raw_adc_gate(program, missing, media, expected)
                                      for missing, media, expected in (
                                          (None, 1, 1), (0, 1, 0), (1, 1, 0),
                                          (2, 1, 0), (None, 0, 0))],
            'outer_gate': {'caller': '0x03f7901e', 'call_to_selection': '0x03f7905e',
                           'additional_predicate': 'bit 5 clear at MMIO halfword 0x7f093080 and media predicate true',
                           'full_outer_gate_not_executed': True},
            'modeled_operations': ['task-control calls', 'LED I/O', 'media preparation',
                                   'file existence', 'key converters/media predicate in key-gate controls'],
            'idle_loop_count_accelerated': True, 'C_copy_zero_helpers_modeled': True,
            'camera_or_network_access': False, 'physical_SD_or_flash_operations': 0,
            'limits': ['No physical button combination has been established from decoded mask 0x508.',
                       'The actual card, filesystem, boot entry, updater and programming are not executed.',
                       'No bank reload occurs within this selection routine; USB disconnect/normal SD entry are separate.',
                       'This is a firmware-update route; it does not prove arbitrary code launch from SD.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.program.read_bytes())
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('Native MC282.upd/MC282e.upd selection and decoded-key predicate verified; stopped before updater.')


if __name__ == '__main__':
    main()
