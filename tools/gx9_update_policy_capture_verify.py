#!/usr/bin/env python3
"""Verify an owner-run GX9 policy round trip from saved USB bytes; offline only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from gx9_capture_verify import read_capture
from gx9_update_auth_verify import PROGRAM_SHA


PROBE_SHA = '0db4a92956f5fff28e5597139394d76d0ce9d8ebed810ee69eb18966927d4b6a'
TARGET = 0x83f1801a


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(capture, program):
    source = program.read_bytes()
    if sha(source) != PROGRAM_SHA:
        raise ValueError('Expected the verified 1.4 program component')
    wire = read_capture(capture)
    report = json.loads((capture / 'report.json').read_text(encoding='utf-8-sig'))
    if (report.get('verifier_sha256') != PROBE_SHA or report.get('mode') != 'roundtrip'
            or not report.get('ok') or not report.get('temporary_policy_one_verified')
            or not report.get('restoration_verified') or report.get('needs_restoration')):
        raise ValueError('Producer did not report a completed guarded policy round trip')
    memory = (capture / 'memory.bin').read_bytes()
    if len(memory) != 7 * 1024:
        raise ValueError('Expected seven complete acquired blocks')
    blocks = [memory[i:i + 1024] for i in range(0, len(memory), 1024)]
    linux, code, before, changed, restored, code_repeat, linux_repeat = blocks
    if (sha(linux) != 'd982dd856084fcd5dfbfc9cc40f02922e2b610287ede1ddd1f347d90bfe1ddbe'
            or linux_repeat != linux or code != source[0x1a7800:0x1a7c00]
            or code_repeat != code or before != source[0x98000:0x98400]):
        raise ValueError('Captured code or default metadata does not match pinned inputs')
    if (before[0x1a:0x1c] != b'\0\0' or restored != before
            or changed != before[:0x1a] + b'\x01\0' + before[0x1c:]):
        raise ValueError('Exact policy change or complete restoration is not established')
    events = [json.loads(line) for line in (capture / 'events.jsonl').read_text().splitlines()]
    pairs, request = [], None
    for event in events:
        if event.get('event') == 'prepare' and event['setup_hex'] not in (
                '4000000000000000', '4000000001000000'):
            raise ValueError('Unexpected USB direction-preparation request')
        if event.get('event') != 'bulk' or event['status'] != 0:
            continue
        raw = bytes.fromhex(event['hex'])
        if event['endpoint'] == 1:
            request = raw
        elif event['endpoint'] == 0x82 and len(raw) > 1:
            pairs.append((request, raw))
            request = None
    if [p[0][3] for p in pairs] != [0x35, 0x5c, 0x5c, 0x5c, 0x9b, 0x9c, 0x9b,
                                    0x5c, 0x9c, 0x9b, 0x5c, 0x5c, 0x5c, 0x35]:
        raise ValueError('Unexpected policy experiment sequence')
    if wire['service_requests'] != 14:
        raise ValueError('Unexpected extra or incomplete transactions')
    saved, words, writes = [], [], []
    addresses = []
    for (req, reply), row in zip(pairs, wire['transactions']):
        if req[3] == 0x35:
            if (row.get('area'), row.get('word_index'), row.get('word_hex')) != ('0x10', 0x2000, 'f2b0'):
                raise ValueError('Buffer control differs')
        elif req[3] == 0x5c:
            start, end = int.from_bytes(req[4:8], 'little'), int.from_bytes(req[8:12], 'little')
            if not row['successful_read'] or end != start + 1024:
                raise ValueError('Block exchange differs')
            addresses.append(start)
            saved.append(reply[4:-2])
        elif req[3] == 0x9b:
            if row.get('source_address') != hex(TARGET) or not row['successful_read']:
                raise ValueError('Independent policy word read differs')
            words.append(reply[4:6])
        elif req[3] == 0x9c:
            if row.get('destination_address') != hex(TARGET) or row['result'] != 'write_ack':
                raise ValueError('Fixed policy write not acknowledged')
            writes.append(req[8:10])
    if (saved != blocks or addresses != [0x80208000, 0x84027800, 0x83f18000,
                                         0x83f18000, 0x83f18000, 0x84027800, 0x80208000]
            or words != [b'\0\0', b'\x01\0', b'\0\0'] or writes != [b'\x01\0', b'\0\0']):
        raise ValueError('Saved bytes, addresses or independent word/write sequence differ')
    return {
        'schema': 1, 'scope': 'Physical updater-policy RAM round trip, not a firmware update',
        'verifier_sha256': sha(Path(__file__).read_bytes()), 'producer_sha256': PROBE_SHA,
        'capture_id': capture.name, 'program_v14_sha256': PROGRAM_SHA,
        'policy_service_address': hex(TARGET), 'policy_link_address': '0x03f1801a',
        'policy_program_offset': '0x9801a', 'policy_values_read': [0, 1, 0],
        'complete_original_metadata_block_restored': True,
        'changed_metadata_byte_offsets': ['0x1a'], 'memory_write_requests': 2,
        'metadata_before_sha256': sha(before), 'metadata_temporary_sha256': sha(changed),
        'metadata_restored_sha256': sha(restored), 'installed_updater_block_sha256': sha(code),
        'producer_report_sha256': sha((capture / 'report.json').read_bytes()),
        'camera_or_network_access_by_this_verifier': False,
        'flash_programming_commands_sent': 0, 'firmware_update_started': False,
        'wire': wire,
        'limits': ['This proves the RAM policy field is writable and restorable.',
                   'It does not demonstrate a completed update or boot of modified firmware.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--program', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.capture, args.program)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('Physical policy 0 -> 1 -> 0, all wire exchanges and complete restoration verified offline.')


if __name__ == '__main__':
    main()
