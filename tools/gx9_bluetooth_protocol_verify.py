#!/usr/bin/env python3
"""Extract pinned GX9 GATT definitions and execute factory counter callbacks.

Uses the owner's recovered Linux bt executable. Native ARM callbacks run with
modeled logging, time and memset. No Bluetooth, socket, camera, shell, firmware
installation or filesystem operation is issued by the emulated program.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import uuid

from gx9_linux_command_verify import Elf
from gx9_linux_event_path_verify import Machine, HEAP, sha


BT_SHA = '71936c863d9ad0b6d28f2b7dcae4707128a2175f01fcf69628991600ef117ae4'
FACTORY_UUID = '054ac620-3214-21e6-ac0d-0002a5d5c51b'


def definitions(elf):
    services = []
    for index in range(8):
        at = 0x34590 + index * 16
        name, handle, count, chars = (elf.word(at + i) for i in range(0, 16, 4))
        service = str(uuid.UUID(elf.string(name)))
        if handle != 0xffffffff or not 1 <= count <= 16:
            raise ValueError('GATT service geometry differs')
        entries = []
        for i in range(count):
            row = chars + i * 20
            pointer, prop, perm, slot, ident = (elf.word(row + j) for j in range(0, 20, 4))
            if slot != 0xffffffff or not 0 <= ident <= 0x2b:
                raise ValueError('GATT characteristic geometry differs')
            entries.append({'uuid': str(uuid.UUID(elf.string(pointer))),
                            'property_field': hex(prop), 'permission_field': hex(perm),
                            'internal_characteristic_id': hex(ident)})
        services.append({'index': index, 'uuid': service, 'characteristics': entries})
    factory = services[-1]
    if factory['uuid'] != FACTORY_UUID or [c['internal_characteristic_id'] for c in factory['characteristics']] != ['0x27', '0x28', '0x29']:
        raise ValueError('Factory service identifiers differ')
    return services


def factory_controls(elf):
    machine = Machine(elf)
    machine.memory_imports()
    machine.hooks[0x11660] = lambda *args: machine.ret(0)  # Modeled timestamp helper.
    imports = []

    def fill(destination, value, size, unused):
        if destination != HEAP + 0x100 or size != 4:
            raise ValueError('Factory callback tried another output extent')
        imports.append({'operation': 'memset', 'bytes': size, 'byte_value': value & 255})
        machine.write(destination, bytes([value & 255]) * size)
        machine.ret(destination)

    def forbidden(*unused):
        raise ValueError('Factory counter callback unexpectedly reached a process operation')

    machine.imports.update(memset=fill, system=forbidden)
    rows = []
    for initial in (0, 1, 0xfe, 0xff, 0x100):
        machine.put_word(0x34ed8, initial)
        machine.write(HEAP + 0x100, b'\xa5' * 16)
        machine.finished = False
        before = machine.native_instructions
        machine.run(0x13784, (HEAP, HEAP + 0x100))
        actual = machine.read(HEAP + 0x100, 16)
        if (machine.word(HEAP) != 4 or actual != bytes([initial & 255]) * 4 + b'\xa5' * 12
                or machine.word(0x34ed8) != initial + 1):
            raise ValueError('Native factory counter read differs')
        rows.append({'operation': 'factory-read', 'initial_counter': initial,
                     'output_hex': actual[:4].hex(), 'output_bytes': 4,
                     'tail_sentinel_unchanged': True,
                     'native_instructions': machine.native_instructions - before})
    machine.put_word(0x34edc, 0)
    for length in (3, 4, 8, 4):
        initial = machine.word(0x34edc)
        machine.finished = False
        before = machine.native_instructions
        machine.run(0x137f0, (length, HEAP + 0x100))
        final = machine.word(0x34edc)
        if final != initial + (1 if length == 4 else 0):
            raise ValueError('Native factory counter write differs')
        rows.append({'operation': 'factory-write', 'input_bytes': length,
                     'counter_before': initial, 'counter_after': final,
                     'native_instructions': machine.native_instructions - before})
    return {'read_entry': '0x13784', 'write_entry': '0x137f0',
            'read_counter': '0x34ed8', 'write_counter': '0x34edc', 'controls': rows,
            'modeled_operations': ['timestamp', 'printf', 'memset'],
            'process_socket_or_file_imports_executed': False,
            'scope': 'Named factory read/write callbacks; not the full Bluetooth receive path'}


def system_references(elf):
    target = next(address for address, name in elf.plt.items() if name == 'system')
    section = elf.sections['.text']
    calls = []
    for offset in range(section[4], section[4] + section[5] - 3, 4):
        word = struct.unpack_from('<I', elf.data, offset)[0]
        if (word >> 25) & 7 != 5:
            continue
        relative = word & 0xffffff
        if relative & (1 << 23):
            relative -= 1 << 24
        address = section[3] + offset - section[4]
        if address + 8 + relative * 4 == target:
            calls.append(address)
    if calls != [0x12f40, 0x12fe8, 0x13054, 0x131b0]:
        raise ValueError('Direct native system() references differ')
    return {'PLT': hex(target), 'direct_ARM_branch_sites': [hex(at) for at in calls],
            'reviewed_call_context': 'Radio-test helper formats fixed hci_cmd paths with numeric fields; btteststart script',
            'arbitrary_shell_request_or_external_delivery_established': False,
            'scope': 'Static direct-branch references; not a complete process/data-flow proof'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bt', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    elf = Elf(args.bt)
    if sha(elf.data) != BT_SHA:
        raise ValueError('Expected the pinned recovered GX9 Bluetooth application')
    services = definitions(elf)
    result = {'schema': 1, 'scope': 'Recovered GATT definitions and native factory counter controls',
              'verifier_sha256': sha(Path(__file__).read_bytes()), 'bt_sha256': BT_SHA,
              'bt_bytes': len(elf.data), 'service_table': '0x34590', 'service_count': len(services),
              'characteristics_referenced_by_services': sum(len(s['characteristics']) for s in services),
              'services': services, 'factory_counter_controls': factory_controls(elf),
              'process_call_review': system_references(elf), 'camera_or_network_access': False,
              'limits': ['Defined services are not proof that a service is advertised or accessible in the current camera mode.',
                         'Pairing, permissions and external-to-ICC delivery have not been verified.',
                         'The named factory counter callbacks do not establish a memory reader, flash writer or shell.',
                         'Other Bluetooth callbacks and RTOS event consumers remain to be traced.']}
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('Eight GATT definitions and nine native factory counter controls verified offline; no Bluetooth or process access.')


if __name__ == '__main__':
    main()
