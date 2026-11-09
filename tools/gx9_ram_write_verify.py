#!/usr/bin/env python3
"""Check the fixed GX9 RAM write/restore experiment from saved USB evidence.

Offline only: no packet generation, device access or network operations.
An ACK alone is insufficient; this requires independent word/block readback,
exactly two changed bytes, complete restoration and unchanged code controls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from gx9_capture_verify import read_capture


COMPONENT_SHA = '16098771484d4724dd489583aa19c08c9d624596f4369781d983ba15aef8de37'
CODE_SHA = 'd982dd856084fcd5dfbfc9cc40f02922e2b610287ede1ddd1f347d90bfe1ddbe'
BLOCK, TARGET = 0x85370000, 0x85370020
ORIGINAL, TAG = bytes.fromhex('ffff'), bytes.fromhex('a55a')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(capture, component):
    wire = read_capture(capture)
    source = component.read_bytes()
    memory = (capture / 'memory.bin').read_bytes()
    if sha(source) != COMPONENT_SHA or len(source) != 131072 or len(memory) != 3072:
        raise ValueError('Pinned component or captured block extents differ')
    header = struct.unpack_from('<7I', source)
    if header != (0x44414f4c, 0x089b0000, 0x089b0000, 0x089b0000,
                  0x089b0000, 0x0537001c, 0x0537001c):
        raise ValueError('Expected the empty postboot3 LOAD header')
    before, tagged, restored = (memory[i:i + 1024] for i in (0, 1024, 2048))
    if before != source[:1024] or before[0x1c:] != bytes([255]) * (1024 - 0x1c):
        raise ValueError('Original padding block differs from the verified component')
    expected = before[:0x20] + TAG + before[0x22:]
    if tagged != expected or restored != before:
        raise ValueError('Exact tag or complete restoration is not established')

    events = [json.loads(line) for line in (capture / 'events.jsonl').read_text().splitlines()]
    pairs, request = [], None
    for event in events:
        if event.get('event') != 'bulk' or event['status'] != 0:
            continue
        data = bytes.fromhex(event['hex'])
        if event['endpoint'] == 1:
            request = data
        elif event['endpoint'] == 0x82 and len(data) > 1:
            pairs.append((request, data))
            request = None
    operations = [req[3] for req, _ in pairs]
    if operations != [0x35, 0x5c, 0x5c, 0x9b, 0x9c, 0x9b, 0x9c,
                      0x9b, 0x5c, 0x9c, 0x9b, 0x5c, 0x5c, 0x35]:
        raise ValueError('Capture differs from the fixed experiment sequence')
    if wire['service_requests'] != 14:
        raise ValueError('Unexpected extra or incomplete service exchanges')
    code, blocks, words, writes = [], [], [], []
    for (req, reply), transaction in zip(pairs, wire['transactions']):
        if req[3] == 0x35:
            if (transaction.get('area'), transaction.get('word_index'),
                    transaction.get('word_hex')) != ('0x10', 0x2000, 'f2b0'):
                raise ValueError('Known indexed-buffer control differs')
        elif req[3] == 0x5c:
            address = int.from_bytes(req[4:8], 'little')
            if not transaction['successful_read'] or int.from_bytes(req[8:12], 'little') != address + 1024:
                raise ValueError('Block read did not succeed with the fixed geometry')
            if address == 0x80208000:
                if sha(reply[4:-2]) != CODE_SHA:
                    raise ValueError('Known code control differs')
                code.append(reply[4:-2])
            elif address == BLOCK:
                blocks.append(reply[4:-2])
            else:
                raise ValueError('Unexpected block address')
        elif req[3] == 0x9b:
            if transaction.get('source_address') != hex(TARGET) or not transaction['successful_read']:
                raise ValueError('Independent word read differs')
            words.append(reply[4:6])
        elif req[3] == 0x9c:
            if transaction.get('destination_address') != hex(TARGET) or transaction['result'] != 'write_ack':
                raise ValueError('Fixed write was not acknowledged')
            writes.append(req[8:10])
    if (blocks != [before, tagged, restored] or len(code) != 2 or code[0] != code[1]
            or words != [ORIGINAL, ORIGINAL, TAG, ORIGINAL]
            or writes != [ORIGINAL, TAG, ORIGINAL]):
        raise ValueError('Word/block readback or write sequence differs')
    return {
        'schema': 1, 'scope': 'One fixed GX9 RAM word changed and restored; no setting change or flash programming',
        'capture': capture.name, 'verifier_sha256': sha(Path(__file__).read_bytes()),
        'wire_verifier_sha256': sha(Path(__file__).with_name('gx9_capture_verify.py').read_bytes()),
        'component': 'postboot3', 'component_bytes': len(source), 'component_sha256': COMPONENT_SHA,
        'empty_LOAD_header_verified': True, 'service_block_start': hex(BLOCK),
        'write_operation': '0x9c', 'write_service_address': hex(TARGET),
        'original_word_hex': ORIGINAL.hex(), 'test_word_hex': TAG.hex(),
        'before_block_sha256': sha(before), 'tagged_block_sha256': sha(tagged),
        'restored_block_sha256': sha(restored), 'captured_blocks_sha256': sha(memory),
        'changed_byte_offsets_in_block': ['0x20', '0x21'], 'changed_bytes': 2,
        'word_and_block_readbacks_match': True, 'complete_block_restored': True,
        'code_and_buffer_controls_unchanged': True, 'memory_write_requests_sent': 3,
        'flash_programming_commands_sent': 0, 'user_setting_changed': False,
        'wire': wire,
        'limits': [
            'Only this fixed padding address and two word values were tested.',
            'This does not establish arbitrary-address write permissions or any persistent flash writer.',
            'USB writer reachability does not establish an accepted modified update or external shell.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--component', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.capture, args.component)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('Three RAM write requests, exact two-byte change and complete restoration verified offline.')


if __name__ == '__main__':
    main()
