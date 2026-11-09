#!/usr/bin/env python3
"""Execute GX9 USB service handlers offline against pinned 1.4 ARM components.

Reproduces the measured descriptors and complete saved policy transcript,
enumerates the first command dispatcher, and checks settings-bank selection.
No USB, SSH, network, SD card or physical flash access is implemented.
Requires Unicorn 2.1.4 and private, locally decoded firmware inputs.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct

import unicorn as U
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

from gx9_update_route_verify import Machine, BASE, CONTEXT, STACK, RETURN, sha
from gx9_update_policy_capture_verify import verify as verify_policy_capture


COMPONENTS = {
    'postboot1': (0x047f0000, 4456448,
                  '76e071e60e1c2cec98dd8bdda49fa0a02120e218e38ece36f97da3965b3b64ca'),
    'postboot5': (0x053b0000, 1835008,
                  'ea085c958d0ff4b3bf0bf091f0a885357a65045348513d507acb75c70347f08e'),
}
DISPATCH, SERVICE, STATUS = 0x053fbd16, 0x089b86d0, 0x08aa7b68
POLICY, BUFFER = 0x03f1801a, CONTEXT


class USBMachine(Machine):
    def __init__(self, program, components):
        super().__init__(program, b'offline USB fixture')
        # The EEPROM shadows in this image are writable RAM on the target.
        self.vm.mem_protect(BASE, len(program), U.UC_PROT_ALL)
        for name, (base, size, digest) in COMPONENTS.items():
            data = components[name]
            if len(data) != size or sha(data) != digest:
                raise ValueError('Pinned 1.4 component differs: ' + name)
            self.vm.mem_map(base, size, U.UC_PROT_READ | U.UC_PROT_EXEC)
            self.vm.mem_write(base, data)
        self.vm.mem_map(0x089b4000, 0x100000)
        self.vm.mem_write(0x089b4000, components['postboot5'][0x81c14:0x86550])
        self.vm.mem_map(0x193d6000, 0x22000)  # Service's whole-bank read buffer.
        self.boundary = None
        self.destination = None

    def code(self, vm, address, size, user):
        if self.boundary and not self.boundary[0] <= address < self.boundary[1]:
            self.destination = address
            vm.emu_stop()
            return
        super().code(vm, address, size, user)

    def dispatch_destination(self, opcode):
        self.vm.mem_write(SERVICE + 8, struct.pack('<H', opcode))
        self.vm.mem_write(BUFFER, bytes([8, 0, 255, opcode]) + bytes(12))
        self.vm.reg_write(UC_ARM_REG_SP, STACK + 0x1ff00)
        self.vm.reg_write(UC_ARM_REG_LR, RETURN | 1)
        self.vm.reg_write(UC_ARM_REG_R0, BUFFER)
        self.boundary, self.destination = (DISPATCH, 0x053fbeec), None
        try:
            self.vm.emu_start(DISPATCH | 1, RETURN, count=100)
            if self.destination is None:
                raise ValueError('First-dispatch instruction bound reached')
            return self.destination
        finally:
            self.boundary = None

    def exchange(self, request):
        if (len(request) != {8: 16, 1: 1030}.get(request[0])
                or request[1:3] != b'\x00\xff' or request[-1]
                or request[-2] != sum(request[1:-2]) & 255):
            raise ValueError('Expected a validated small/block service-frame fixture')
        self.vm.mem_write(BUFFER, bytes(0x9000))
        self.vm.mem_write(BUFFER, request)
        self.vm.mem_write(SERVICE + 8, struct.pack('<H', request[3]))
        self.call(DISPATCH, BUFFER, count=100000)
        length = self.word(SERVICE + 0x34)
        if length not in (16, 262, 1030):
            raise ValueError(f'Unexpected native reply length: {length}')
        return self.read(BUFFER, length)


def frame(opcode, fields=b''):
    if len(fields) > 10:
        raise ValueError('Small-frame fields exceed bound')
    data = bytearray(bytes([8, 0, 255, opcode]) + fields.ljust(10, b'\0') + bytes(2))
    data[-2] = sum(data[1:-2]) & 255
    return bytes(data)


def descriptors(program, components, observed):
    measured = observed['usb_descriptor']
    device = bytes.fromhex(measured['device_descriptor_hex'])
    interface = measured['interfaces'][0]
    expected = struct.pack('<BBHBBBBB', 9, 2, measured['total_length'], 1, 1, 0, 0xc0, 1)
    expected += struct.pack('<9B', 9, 4, 0, 0, 3, interface['class'],
                            interface['subclass'], interface['protocol'], 0)
    for endpoint in interface['endpoints']:
        expected += struct.pack('<4BHB', 7, 5, endpoint['address'], endpoint['type'],
                                endpoint['packet_bytes'], endpoint['interval'])
    result = []
    for high_speed in (1, 0):
        machine = USBMachine(program, components)
        length = machine.call(0x054015a0, BUFFER, BUFFER + 0x10000, high_speed, 0)
        if length != machine.word(BUFFER + 0x10000) or length != 210:
            raise ValueError('Descriptor-builder total differs')
        data = machine.read(BUFFER, length)
        actual = data[18:57]
        wanted = bytearray(expected)
        if not high_speed:
            struct.pack_into('<H', wanted, 22, 64)
            struct.pack_into('<H', wanted, 29, 64)
        if data[:18] != device or actual != wanted:
            raise ValueError('Native USB profile differs from measured descriptor/control')
        result.append({'speed': 'high' if high_speed else 'full',
                       'native_entry': '0x054015a0', 'total_descriptor_bytes': length,
                       'device_descriptor_hex': data[:18].hex(),
                       'configuration_descriptor_hex': actual.hex(),
                       'matches_physical_high_speed_profile': bool(high_speed),
                       'native_instructions': machine.instructions})
    return result


def dispatcher(program, components):
    machine = USBMachine(program, components)
    initial = int.from_bytes(machine.read(0x03f1c404, 2), 'little')
    if initial != 1:
        raise ValueError('Default conditional block-read selector differs')
    groups = defaultdict(list)
    for opcode in range(256):
        groups[hex(machine.dispatch_destination(opcode))].append(f'0x{opcode:02x}')
    machine.vm.mem_write(0x03f1c404, bytes(2))
    alternative = machine.dispatch_destination(0x3e)
    if alternative != 0x053fb844:
        raise ValueError('Conditional block-read dispatch differs')
    return {'native_entry': hex(DISPATCH), 'opcodes_executed': 256,
            'execution_stopped_before_each_handler': True,
            'initial_fixed_word_0x03f1c404': initial, 'groups': dict(groups),
            'conditional_0x3e': {'fixed_word': 0, 'handler': hex(alternative)},
            'scope': 'First dispatcher only; queued commands need their downstream consumers traced'}


def captured_pairs(capture):
    request, result = None, []
    for line in (capture / 'events.jsonl').read_text().splitlines():
        event = json.loads(line)
        if event.get('event') != 'bulk' or event.get('status') != 0:
            continue
        data = bytes.fromhex(event['hex'])
        if event['endpoint'] == 1:
            request = data
        elif event['endpoint'] == 0x82 and len(data) > 1:
            if request is None:
                raise ValueError('Captured reply has no request')
            result.append((request, data))
            request = None
    return result


def replay(program, components, capture, program_path):
    proof = verify_policy_capture(capture, program_path)
    memory = (capture / 'memory.bin').read_bytes()
    machine = USBMachine(program, components)
    # The owner-specific A-bank control is not part of the default UPD bank.
    # Seed that acquired RAM word just as the acquired code/data blocks below.
    machine.vm.mem_write(0x03ea4000, b'\xf2\xb0')
    for page, offset in ((0x80208000, 0), (0x84027000, 1024), (0x83f18000, 2048)):
        machine.vm.mem_map(page, 4096)
        destination = page + (0x800 if page == 0x84027000 else 0)
        machine.vm.mem_write(destination, memory[offset:offset + 1024])
    rows = []
    for index, (request, expected) in enumerate(captured_pairs(capture)):
        before = machine.instructions
        actual = machine.exchange(request)
        if actual != expected:
            raise ValueError(f'Native response differs from capture at transaction {index + 1}')
        rows.append({'transaction': index + 1, 'opcode': hex(request[3]),
                     'reply_bytes': len(actual), 'request_sha256': sha(request),
                     'response_sha256': sha(actual), 'complete_reply_matches_capture': True,
                     'native_instructions': machine.instructions - before})
    if (machine.read(0x83f18000, 1024) != memory[2048:3072]
            or proof['memory_write_requests'] != 2):
        raise ValueError('Native replay did not restore its simulated RAM')
    return {'capture_id': capture.name, 'source_capture_verified_independently': True,
            'all_14_complete_responses_match': True,
            'service_word_and_block_read_handlers_replaced': False,
            'initial_RAM_seeded_from_capture': ['A-bank control word at 0x03ea4000',
                                               'Linux, updater-code and initial policy blocks'],
            'complete_original_simulated_policy_block_restored': True,
            'C_copy_and_zero_helpers_modeled': True, 'transactions': rows}


def bank_controls(program, components):
    machine = USBMachine(program, components)
    # Test RAM-shadow access with the native bank-size API, not a substitute.
    index = 0x1801a // 2
    writes = []

    def observe(vm, access, address, size, value, user):
        if POLICY <= address < POLICY + 2:
            writes.append({'address': hex(address), 'bytes': size, 'value': value})

    machine.vm.hook_add(U.UC_HOOK_MEM_WRITE, observe)
    shadow = []
    for value in (0, 1, 0):
        if value or shadow:
            request = frame(0x34, struct.pack('<HHB', index, value, 0x22))
            if machine.exchange(request) != frame(1, b'\0'):
                raise ValueError('Native bank-shadow write did not acknowledge')
        request = frame(0x35, struct.pack('<HB', index, 0x22))
        reply = machine.exchange(request)
        if reply != frame(0x36, struct.pack('<H', value)):
            raise ValueError('Native fixed-bank shadow control differs')
        shadow.append({'value': value, 'reply_hex': reply.hex()})
    if writes != [{'address': hex(POLICY), 'bytes': 2, 'value': 1},
                  {'address': hex(POLICY), 'bytes': 2, 'value': 0}]:
        raise ValueError('Native bank-shadow destination differs')
    flash_reads, zero_reads = [], []
    machine.vm.mem_write(0x05ecc118, b'\x01')  # Already-initialized simulated driver.
    machine.hooks.update({0x041b1da8: lambda *args: machine.ret(0),
                          0x041b4c70: lambda *args: machine.ret(0)})

    def unexpected_sector_read(*args):
        raise ValueError('Zero-length bank request reached a sector operation')

    machine.hooks[0x041ff894] = unexpected_sector_read

    def flash_read(source, destination, length, unused):
        if (source, destination, length) == (0x40de0000, 0x193d6800, 0):
            zero_reads.append({'virtual_flash_address': hex(source), 'bytes': 0})
            # Execute the real zero-length wrapper; only its locks are modeled.
            del machine.hooks[0x041ffeca]
            return
        if (source, destination, length) != (0x40e00000, 0x193d6800, 0x20000):
            raise ValueError('Unexpected service flash-reader geometry')
        flash_reads.append({'virtual_flash_address': hex(source),
                            'buffer': hex(destination), 'bytes': length})
        machine.vm.mem_write(destination, program[0x80000:0xa0000])
        machine.ret(0)

    machine.hooks[0x041ffeca] = flash_read
    failed = machine.exchange(frame(0x38, struct.pack('<HB', 0x3f80, 0x20)))
    if failed != frame(1, b'\x03') or flash_reads:
        raise ValueError('Older area-0x20 request did not reproduce measured failure')
    if zero_reads != [{'virtual_flash_address': '0x40de0000', 'bytes': 0}]:
        raise ValueError('Older area-0x20 zero-length native path differs')
    machine.hooks[0x041ffeca] = flash_read
    succeeded = machine.exchange(frame(0x38, struct.pack('<HB', index, 0x22)))
    if succeeded != frame(0x36, bytes(2)) or len(flash_reads) != 1:
        raise ValueError('Native area-0x22 fixed-bank read selection differs')
    return {'fixed_bank_area': '0x22', 'policy_word_index': hex(index),
            'shadow_read_opcode': '0x35', 'shadow_write_opcode': '0x34',
            'native_bank_size_api_executed': True, 'shadow_values': shadow,
            'shadow_writes': writes, 'flash_word_read_opcode': '0x38',
            'area_0x20_error_matches_previous_physical_capture': failed.hex(),
            'area_0x20_zero_length_native_read': zero_reads,
            'area_0x22_reply_hex': succeeded.hex(), 'flash_read_calls': flash_reads,
            'flash_byte_reader_modeled': True, 'persistent_write_demonstrated': False,
            'limits': ['0x34 changes a RAM shadow; no persistent save has been established.',
                       '0x38 area 0x22 has been checked in emulation only. It has not been sent to the camera.']}


def memory_width_controls(program, components):
    machine = USBMachine(program, components)
    address = CONTEXT + 0x20000
    machine.put_word(address, 0x12345678)
    results = []
    for name, opcode, write, width, value, wanted in (
        ('read-halfword', 0x48, 0, 0, 0, 0x5678),
        ('read-word', 0x48, 0, 1, 0, 0x12345678),
        ('write-word-and-read-back', 0x48, 1, 1, 0x89abcdef, 0x89abcdef),
        ('write-halfword-with-ack', 0x4a, 1, 0, 0xa55a, 0x89aba55a),
    ):
        request = frame(opcode, struct.pack('<BBII', write, width, address, value))
        actual = machine.exchange(request)
        expected = (frame(0x49, bytes([width]) + struct.pack('<I', wanted))
                    if opcode == 0x48 else frame(1, b'\0'))
        if actual != expected or machine.word(address) != (wanted if width or write else 0x12345678):
            raise ValueError('Native halfword/word access differs: ' + name)
        results.append({'control': name, 'opcode': hex(opcode), 'reply_hex': actual.hex()})
    machine.vm.mem_write(SERVICE, b'\x01')
    before = machine.read(address, 4)
    blocked = machine.exchange(frame(0x48, struct.pack('<BBII', 1, 1, address, 0)))
    if blocked != frame(1, b'\x01') or machine.read(address, 4) != before:
        raise ValueError('Native guarded-access control differs')
    return {'scratch_RAM_only': True, 'native_handler_0x48': '0x053faa50',
            'native_handler_0x4a': '0x053fa9e4', 'controls': results,
            'nonzero_service_flag_blocks_0x48_without_changing_RAM': True,
            'limits': ['These word-access variants have not been sent to the camera.',
                       'No usable physical address range or flash operation follows from this scratch-RAM test.']}


def framing_controls(program, components):
    machine = USBMachine(program, components)
    rows = []
    for kind, expected in ((8, 16), (1, 1030), (2, 32774), (3, 8198),
                           (4, 4102), (5, 106), (16, 262)):
        actual = machine.call(0x053fbf22, kind)
        if actual != expected:
            raise ValueError('Native frame-size lookup differs')
        rows.append({'frame_class': hex(kind), 'frame_bytes': actual})
    reply = machine.exchange(frame(0x3a))
    count = reply[4]
    entries = [{'area': hex(reply[5 + 5 * i]),
                'word_count': int.from_bytes(reply[6 + 5 * i:10 + 5 * i], 'little')}
               for i in range(count)]
    useful = [entry for entry in entries if entry['area'] != '0xff']
    if useful != [{'area': a, 'word_count': n} for a, n in (
            ('0x10', 65536), ('0x11', 65536), ('0x21', 65536),
            ('0x22', 65536), ('0x30', 3072))]:
        raise ValueError('Native settings-area metadata differs')
    return {'native_size_lookup': '0x053fbf22', 'frame_classes': rows,
            'area_metadata_opcode': '0x3a', 'reply_opcode': '0x3b',
            'native_metadata_reply_bytes': len(reply), 'useful_area_entries': useful,
            'other_entries': '0xff area placeholders; not evidence for additional readable banks',
            'limits': ['Frame-size lookup does not establish which operations accept each frame class.',
                       'Physical larger-frame tests previously failed; no larger-frame request was sent here.']}


def queued_controls(program, components):
    rows = []
    for opcode, kind in ((0x28, 1), (0x2b, 1), (0x30, 2), (0x31, 1),
                         (0x32, 2), (0x33, 2), (0x37, 1)):
        machine = USBMachine(program, components)
        events, allocations = [], []
        message = CONTEXT + 0x18000

        def allocate(pool, output, *unused):
            if pool != 0x28:
                raise ValueError('Unexpected simulated message pool')
            allocations.append(pool)
            machine.put_word(output, message)
            machine.ret(0)

        def enqueue(a, b, c, d):
            stack = machine.vm.reg_read(UC_ARM_REG_SP)
            extra = [machine.word(stack + i) for i in range(0, 16, 4)]
            if [a, b, c, d, *extra] != [0xc1, 0x76, 0x6b, 0, 0xe8202,
                                                       message, 0, 0xffffffff]:
                raise ValueError('Native USB callback queue routing differs')
            events.append({'destination_task': hex(a), 'source_task': hex(b),
                           'source_module': hex(c), 'event': hex(extra[0])})
            machine.ret(0)

        machine.hooks.update({0x041f9164: allocate, 0x0421acec: enqueue,
                              0x0407e54e: lambda *args: machine.ret(0)})
        machine.call(0x053f77b6)  # Initialize callback slots.
        machine.call(0x042606ae)  # Native registration of main callback.
        if machine.word(0x08aa70dc) != 0x0425ffcd:
            raise ValueError('Native main callback registration differs')
        machine.vm.mem_write(BUFFER, frame(opcode))
        machine.vm.mem_write(CONTEXT + 0x10000, struct.pack('<5I', BUFFER, 0, 16, 0, 0))
        status = machine.call(0x053f8076, CONTEXT + 0x10000)
        if (status != 1 or len(events) != 1 or allocations != [0x28]
                or machine.read(message, 7) != b'USBMNT\0'
                or machine.read(message + 7, 2) != bytes([kind, opcode])):
            raise ValueError('Native queued-command envelope differs')
        rows.append({'opcode': hex(opcode), 'message_tag': 'USBMNT',
                     'message_class': kind, 'queued_event': events[0],
                     'native_instructions': machine.instructions})
    return {'receive_entry': '0x053f8076', 'main_callback': '0x0425ffcc',
            'callback_registration_executed_natively': True, 'controls': rows,
            'modeled_operations': ['message pool allocation', 'registration state query',
                                   'system queue send', 'C copy/zero helpers'],
            'system_queue_send_modeled_without_running_consumer': True,
            'downstream_event_0x000e8202_consumer_executed': False,
            'persistent_write_or_updater_activation_proven': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--components', required=True, type=Path)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--observed-profile', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    program_path = args.components / 'program.plaintext.bin'
    program = program_path.read_bytes()
    components = {name: (args.components / (name + '.plaintext.bin')).read_bytes()
                  for name in COMPONENTS}
    observed = json.loads(args.observed_profile.read_text())
    result = {'schema': 1, 'scope': 'Native offline GX9 1.4 USB dispatcher and saved-wire replay',
              'verifier_sha256': sha(Path(__file__).read_bytes()),
              'program_sha256': sha(program),
              'component_sha256': {name: sha(data) for name, data in components.items()},
              'observed_usb_evidence_sha256': sha(args.observed_profile.read_bytes()),
              'descriptors': descriptors(program, components, observed),
              'dispatcher': dispatcher(program, components),
              'physical_transcript_replay': replay(program, components, args.capture, program_path),
              'settings_bank_controls': bank_controls(program, components),
              'memory_width_controls': memory_width_controls(program, components),
              'framing_and_area_metadata': framing_controls(program, components),
              'queued_command_controls': queued_controls(program, components),
              'camera_or_network_access': False, 'physical_flash_operations': 0,
              'limits': ['Controller, enumeration, cache/MMU and hardware timing are not emulated.',
                         'First-dispatch routing alone does not identify queued-command effects.',
                         'No external updater activation or SD autorun is established by these controls.']}
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('Native USB profile, all 256 first-dispatch routes, 14 captured replies and fixed-bank controls verified offline.')


if __name__ == '__main__':
    main()
