#!/usr/bin/env python3
"""Verify a saved post-flash GX9 inspection from its USB bytes, offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import gx9_policy_helper_windows as helper


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(capture):
    transport, probe, sha = helper.transport, helper.probe, helper.sha
    report = json.loads((capture / 'report.json').read_text())
    events_raw = (capture / 'events.jsonl').read_bytes()
    events = [json.loads(line) for line in events_raw.splitlines() if line]
    memory = (capture / 'memory.bin').read_bytes()
    for event in events:
        if event['event'] in ('api', 'bulk'):
            require(event['status'] >= 0, 'USB failure in saved events')
        if event['event'] == 'prepare':
            require(event['setup_hex'] in ('4000000000000000', '4000000001000000'),
                    'Unexpected control request')
    bulk = [event for event in events if event['event'] == 'bulk']
    transport.PROFILES['policy-metadata'] = (probe.METADATA, probe.METADATA + 1024)
    transport.PROFILES['policy-updater'] = (probe.UPDATER, probe.UPDATER + 1024)
    buffer_request = transport.packet(0x35, 0x2000)
    linux = transport.block_packet(0x80208000, 'linux-prefix')
    updater = transport.block_packet(probe.UPDATER, 'policy-updater')
    metadata = transport.block_packet(probe.METADATA, 'policy-metadata')
    expected = [
        ('buffer', buffer_request), ('linux', linux), ('updater', updater),
        ('metadata', metadata), ('absolute', probe.packet()),
        ('shadow', helper.shadow_packet()), ('absolute', probe.packet()),
        ('shadow', helper.shadow_packet()), ('metadata', metadata),
        ('updater', updater), ('linux', linux), ('buffer', buffer_request),
    ]
    require(len(bulk) == len(expected) * 3, 'Unexpected USB exchange count')
    decoded, blocks, transactions = {}, [], []
    for index, (kind, request) in enumerate(expected):
        sent, header, received = bulk[index * 3:index * 3 + 3]
        data = [bytes.fromhex(event['hex']) for event in (sent, header, received)]
        require([event['endpoint'] for event in (sent, header, received)] == [1, 0x82, 0x82],
                'Unexpected USB direction')
        require(all(event['bytes'] == len(value)
                    for event, value in zip((sent, header, received), data)),
                'Recorded transfer length differs')
        require(data[0] == request, 'Unexpected request; inspection permits only reviewed reads')
        reply = data[2]
        require(len(data[1]) == 1 and data[1] == reply[:1], 'Response type differs')
        if kind in ('linux', 'updater', 'metadata'):
            value = transport.block_response(reply, request)
            blocks.append(value)
        elif kind == 'buffer':
            value = transport.response(reply)
        else:
            value = probe.checked_reply(reply)
        decoded.setdefault(kind, []).append(value)
        transactions.append({'kind': kind, 'opcode': hex(request[3]),
                             'request_sha256': sha(request), 'reply_sha256': sha(reply)})
    require(memory == b''.join(blocks), 'Saved memory differs from decoded USB payloads')
    for kind in ('linux', 'updater', 'metadata', 'buffer'):
        require(decoded[kind][0] == decoded[kind][1], kind + ' repeat differs')
    for kind in ('linux', 'updater'):
        require(sha(decoded[kind][0]) == probe.GUARDS[kind], kind + ' code guard differs')
    policy_block = decoded['metadata'][0]
    require(sha(helper.canonical_metadata(policy_block)) == probe.GUARDS['metadata'],
            'Complete normalized metadata differs')
    require(policy_block[0x1a:0x1c] == b'\x01\0', 'Metadata policy is not one')
    require(decoded['absolute'] == decoded['shadow'] == [1, 1], 'Policy readers disagree')
    require(decoded['buffer'][0] in helper.BUFFER_WORDS, 'Unknown settings-buffer control')
    require(report['mode'] == 'inspect' and report['ok'], 'Inspection report did not complete')
    require(report['helper_sha256'] == sha(Path(helper.__file__).read_bytes()),
            'Report belongs to a different helper revision')
    require(report['service_requests'] == len(expected)
            and report['memory_write_requests_attempted'] == report['flash_programming_commands'] == 0
            and not report['firmware_update_started'], 'Report disagrees with read-only wire sequence')
    return {
        'schema': 1, 'scope': 'Post-flash physical USB inspection, independently decoded offline',
        'verifier_sha256': sha(Path(__file__).read_bytes()),
        'helper_sha256': sha(Path(helper.__file__).read_bytes()),
        'events_sha256': sha(events_raw), 'memory_sha256': sha(memory),
        'service_requests': len(expected), 'memory_write_commands': 0,
        'flash_programming_commands': 0, 'firmware_update_started': False,
        'policy_service_address': hex(probe.TARGET), 'absolute_policy_reads': decoded['absolute'],
        'fixed_shadow_selector': {'opcode': '0x35', 'area': '0x22', 'word_index': '0xc00d'},
        'fixed_shadow_policy_reads': decoded['shadow'], 'metadata_policy': 1,
        'settings_buffer_word': decoded['buffer'][0].hex(),
        'code_and_metadata_repeats_exact': True,
        'linux_code_sha256': sha(decoded['linux'][0]),
        'updater_code_sha256': sha(decoded['updater'][0]),
        'metadata_sha256': sha(policy_block),
        'normalized_metadata_sha256': sha(helper.canonical_metadata(policy_block)),
        'complete_normalized_metadata_matches_original': True,
        'transactions': transactions,
        'limits': ['Readback covers the policy and three 1 KiB blocks, not the full installed firmware.',
                   'This inspection does not perform a flash write or a power-cycle test.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.capture)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('Twelve read-only USB exchanges verified; policy one agrees through both paths.')


if __name__ == '__main__':
    main()
