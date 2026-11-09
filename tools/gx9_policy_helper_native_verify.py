#!/usr/bin/env python3
"""Run the Windows policy-helper logic through native GX9 USB handlers offline.

USB controller exchanges and policy-alias coherence are modeled. Camera ARM
handlers construct the actual replies consumed by the unchanged helper code.
No device, network, SD card, firmware installation or physical flash access.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import tempfile
from unittest.mock import patch

import unicorn as U

import gx9_policy_helper_windows as helper
from gx9_usb_native_verify import USBMachine, COMPONENTS, POLICY, sha
from gx9_update_policy_capture_verify import verify as verify_capture


def run(components_dir, capture, output_parent):
    program_path = components_dir / 'program.plaintext.bin'
    program = program_path.read_bytes()
    verify_capture(capture, program_path)
    components = {name: (components_dir / (name + '.plaintext.bin')).read_bytes()
                  for name in COMPONENTS}
    memory = (capture / 'memory.bin').read_bytes()
    rows = []
    helper.verify_dependencies()
    for mode, initial, target in (('inspect', 0, 0), ('enable', 0, 1),
                                  ('enable', 1, 1), ('restore', 1, 0)):
        machine = USBMachine(program, components)
        machine.vm.mem_write(0x03ea4000, b'\xf2\xb0')
        for page, destination, block in ((0x80208000, 0x80208000, memory[:1024]),
                                         (0x84027000, 0x84027800, memory[1024:2048]),
                                         (0x83f18000, 0x83f18000, memory[2048:3072])):
            machine.vm.mem_map(page, 4096)
            machine.vm.mem_write(destination, block)
        machine.vm.mem_write(0x83f1801a, struct.pack('<H', initial))
        machine.vm.mem_write(POLICY, struct.pack('<H', initial))
        writes, exchanges = [], []

        def mirror(uc, access, address, size, value, user):
            if address == 0x83f1801a:
                if size != 2 or value not in (0, 1):
                    raise ValueError('Unexpected emulated policy write')
                writes.append(value)
                # Hardware cache/MMU coherence is a declared model assumption.
                machine.vm.mem_write(POLICY, struct.pack('<H', value))

        machine.vm.hook_add(U.UC_HOOK_MEM_WRITE, mirror)

        class Reader(helper.transport.Reader):
            def __init__(self):
                self.requests = self.validated = 0
                self.pending = None
                self.direction = None

            def prepare(self, direction):
                if direction not in (0, 1):
                    raise ValueError('Unexpected modeled USB direction')
                self.direction = direction

            def bulk(self, endpoint, data, size):
                if endpoint == 1 and self.direction == 0 and data is not None:
                    request = bytes(data)
                    if size != len(request) or request[3] not in (0x35, 0x5c, 0x9b, 0x9c):
                        raise ValueError('Unexpected helper operation')
                    if request[3] == 0x9c and (request[4:8] != bytes.fromhex('1a80f183')
                                              or int.from_bytes(request[8:10], 'little') not in (0, 1)):
                        raise ValueError('Helper attempted another destination/value')
                    self.pending = machine.exchange(request)
                    exchanges.append({'opcode': hex(request[3]), 'request_sha256': sha(request),
                                      'native_reply_sha256': sha(self.pending)})
                    return request
                if endpoint != 0x82 or self.direction != 1 or self.pending is None or data is not None:
                    raise ValueError('Unexpected modeled USB read')
                if size == 1:
                    return self.pending[:1]
                if size != len(self.pending):
                    raise ValueError('Native reply length differs from helper expectation')
                reply, self.pending = self.pending, None
                return reply

        reader = Reader()
        report = {'memory_write_requests_attempted': 0, 'policy_shadow_read_requests': 0, 'blocks': []}
        with tempfile.TemporaryDirectory(prefix='gx9-helper-native-', dir=output_parent) as folder:
            access = helper.Access(reader, Path(folder), report, lambda *a, **k: None, lambda: None)
            # Transport delays are irrelevant in the modeled USB exchange.
            with patch('gx9_update_policy_probe_windows.time.sleep', return_value=None):
                helper.change_policy(access, report, lambda: None, mode)
        expected_writes = [] if initial == target else [target]
        if (not report['ok'] or report['verified_policy'] != target or writes != expected_writes
                or machine.read(POLICY, 2) != struct.pack('<H', target)
                or machine.read(0x83f1801a, 2) != struct.pack('<H', target)):
            raise ValueError('Helper/native integration result differs')
        rows.append({'mode': mode, 'initial_policy': initial, 'verified_final_policy': target,
                     'native_RAM_writes': writes, 'service_requests': reader.requests,
                     'both_policy_read_paths_agree': report['absolute_and_shadow_after_agree'],
                     'complete_policy_block_verified': report['complete_expected_policy_block_verified'],
                     'native_instructions': machine.instructions, 'exchanges': exchanges})
    return {'schema': 1, 'scope': 'Native ARM replies consumed by Windows policy-helper logic, offline',
            'verifier_sha256': sha(Path(__file__).read_bytes()),
            'helper_sha256': sha(Path(helper.__file__).read_bytes()),
            'native_handler_verifier_sha256': sha(Path(__file__).with_name('gx9_usb_native_verify.py').read_bytes()),
            'program_sha256': sha(program), 'capture_id': capture.name, 'controls': rows,
            'USB_exchange_and_timing_modeled': True, 'policy_alias_coherence_modeled': True,
            'native_word_block_and_write_handlers_replaced': False,
            'camera_or_network_access': False, 'physical_flash_operations': 0,
            'limits': ['This does not establish physical MMU/cache alias coherence.',
                       'The real helper requires both physical readings to agree before and after a change.',
                       'USB disconnect, updater activation, actual flashing and boot are not tested.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--components', required=True, type=Path)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = run(args.components, args.capture, args.out.parent)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('Four helper/native integration controls passed; no camera or physical flash access.')


if __name__ == '__main__':
    main()
