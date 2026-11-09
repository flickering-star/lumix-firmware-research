#!/usr/bin/env python3
"""Extract GX9 HTTP modes and execute the recovered native PSM query decoder.

Only query parsing and mode selection run. C string/copy/log/time operations are
modeled. No camera, HTTP request, Wi-Fi, socket, command action or shell access.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from gx9_linux_command_verify import Elf, PSM_SHA
from gx9_linux_event_path_verify import Machine, HEAP, sha


def mode_definitions(elf):
    modes = []
    for index in range(26):
        at = 0x5dea8 + index * 8
        ident, name = elf.word(at), elf.string(elf.word(at + 4))
        if not re.fullmatch('[a-z_]+', name):
            raise ValueError('Native mode table name differs')
        modes.append({'mode': name, 'internal_id': ident})
    if [row['internal_id'] for row in modes] != [i for i in range(27) if i != 8]:
        raise ValueError('Native mode-table ID geometry differs')
    return modes


def select_mode(elf, query, expected):
    machine = Machine(elf)
    machine.memory_imports()
    machine.hooks[0x2ba88] = lambda *args: machine.ret(0)

    def strcmp(a, b, *unused):
        left, right = machine.string(a), machine.string(b)
        machine.ret((left > right) - (left < right))

    def strstr(a, b, *unused):
        at = machine.string(a).find(machine.string(b))
        machine.ret(a + at if at >= 0 else 0)

    def strchr(a, b, *unused):
        value = machine.string(a)
        at = len(value) if b == 0 else value.find(bytes([b & 255]))
        machine.ret(a + at if at >= 0 else 0)

    def memset(a, b, size, unused):
        if size > 4096:
            raise ValueError('Mode fixture memory fill exceeds bound')
        machine.write(a, bytes([b & 255]) * size)
        machine.ret(a)

    machine.imports.update(strcmp=strcmp, strstr=strstr, strchr=strchr, memset=memset)
    address = 0
    if query is not None:
        machine.write(HEAP, query.encode('ascii') + b'\0')
        address = HEAP
    actual = machine.run(0x2fdcc, (address,))
    if actual != expected:
        raise ValueError('Native mode decoder differs for fixture ' + repr(query))
    return {'query': query, 'native_mode_result': actual,
            'native_instructions': machine.native_instructions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--psm', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    elf = Elf(args.psm)
    if sha(elf.data) != PSM_SHA:
        raise ValueError('Expected the pinned recovered GX9 PSM application')
    modes = mode_definitions(elf)
    positives = [select_mode(elf, 'mode=' + row['mode'], row['internal_id']) for row in modes]
    extra = [select_mode(elf, query, expected) for query, expected in (
        ('event=60&mode=getinfo', 5), ('mode=getinfo&event=60', 5),
        ('mode=linux_cmd', 8), ('mode=firmware', 8), ('mode=60', 8),
        ('type=version', 8), ('mode=' + 'x' * 24, 8), (None, 8))]
    result = {'schema': 1, 'scope': 'Native HTTP mode decoder, not camera command execution',
              'verifier_sha256': sha(Path(__file__).read_bytes()), 'psm_sha256': PSM_SHA,
              'mode_table': '0x5dea8', 'native_get_mode_entry': '0x2fdcc',
              'native_query_value_extractor': '0x2fc5c',
              'defined_mode_count': len(modes), 'mode_definitions': modes,
              'positive_mode_controls': positives, 'additional_controls': extra,
              'unrecognized_or_missing_mode_sentinel': 8,
              'native_query_decoder_and_mode_lookup_replaced': False,
              'modeled_operations': ['C string/memory operations', 'logging', 'timestamp'],
              'camera_network_or_process_access': False,
              'limits': ['This does not execute the selected camera command or trace every subtype.',
                         'Absence of a standalone firmware mode does not rule out another update route.',
                         'The internal Linux event 60 has not been delivered from an external HTTP request.',
                         'Pairing, current Wi-Fi mode and physical request behavior are not tested.']}
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('All 26 native HTTP modes and eight additional query controls verified offline; no requests sent.')


if __name__ == '__main__':
    main()
