#!/usr/bin/env python3
"""Check captured GX9 bytes as raw AES keys using known component prefixes.

Offline only. A four-byte header match is a candidate, not a recovered key:
the entire official component must also match its expected SHA256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

from panasonic_buffer_key_check import HostCodec, selftest


OFFICIAL_SHA = 'c08354c91d083d74b274c4884ab4f06d3f72e47ea289ea80c9685f2292f5b801'
MAGICS = {'dtb': bytes.fromhex('d00dfeed'), 'rootfs1': b'hsqs', 'rootfs2': b'hsqs',
          # Exact recovered stub matches the official component's full SHA256.
          'zboot': bytes.fromhex('c0000cf1')}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('windows', type=Path, nargs='+')
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raw = args.firmware.read_bytes()
    if hashlib.sha256(raw).hexdigest() != OFFICIAL_SHA:
        raise ValueError('Expected the pinned official GX9 1.5 binary')
    inventory = json.loads(args.inventory.read_text())
    if inventory['bin_sha256'] != OFFICIAL_SHA or inventory['model_id'] != 'MC282':
        raise ValueError('Inventory identity differs')
    probes = []
    for name, magic in MAGICS.items():
        entries = [e for e in inventory['entries'] if e['name'] == name]
        if len(entries) != 1:
            raise ValueError('Ambiguous component '+name)
        entry = entries[0]
        offset, size = entry['file_offset'], entry['bytes']
        if entry['flags'] != 3 or offset < 4096 or size <= 0 or size % 16 or offset+size > len(raw):
            raise ValueError('Component bounds differ')
        probes.append({'name': name, 'ciphertext': raw[offset:offset+size],
                       'iv': bytes.fromhex(entry['field16']), 'magic': magic,
                       'expected_sha256': entry['field32']})
    if sum(p.stat().st_size for p in args.windows) > 64*1024*1024:
        raise ValueError('Combined candidate input exceeds 64 MiB')
    report = {'schema': 1, 'scope': 'Raw contiguous 16-byte candidates, AES-128-CBC at five/ten rounds only',
              'firmware_sha256': OFFICIAL_SHA,
              'probe_components': [{'name': p['name'], 'bytes': len(p['ciphertext']),
                                    'magic_hex': p['magic'].hex(), 'iv_hex': p['iv'].hex(),
                                    'expected_plaintext_sha256': p['expected_sha256']} for p in probes],
              'windows': [], 'header_candidates': [], 'verified_keys': [],
              'adjacent_identical_candidates_skipped': True,
              'camera_or_network_access': False,
              'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='gx9-ram-key-') as temporary:
        codec = HostCodec(Path(temporary))
        selftest(codec)
        seen = set()
        for path in args.windows:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            if not 16 <= len(data) <= 16*1024*1024:
                raise ValueError('Each candidate input must be 16 bytes to 16 MiB')
            begun = time.monotonic()
            hits = codec.probe_window(data, probes)
            report['windows'].append({'path': str(path), 'bytes': len(data), 'sha256': digest,
                                      'candidate_positions': len(data)-15,
                                      'elapsed_seconds': time.monotonic()-begun,
                                      'header_candidate_count': len(hits)})
            for hit in hits:
                probe = probes[hit['probe_index']]
                key = bytes.fromhex(hit['key_hex'])
                actual = codec.digest(probe['ciphertext'], key, probe['iv'], hit['rounds'])
                candidate = {**hit, 'source': str(path), 'component': probe['name'],
                             'plaintext_sha256': actual, 'complete_digest_matches': actual == probe['expected_sha256']}
                report['header_candidates'].append(candidate)
                if candidate['complete_digest_matches']:
                    report['verified_keys'].append(candidate)
            args.out.write_text(json.dumps(report, indent=2)+'\n')
            print(f'{path.name}: {len(data):,} bytes, {len(hits)} header candidates', flush=True)
    report['elapsed_seconds'] = time.monotonic()-started
    report['candidate_positions'] = sum(w['candidate_positions'] for w in report['windows'])
    report['limits'] = ['No derived, byte-reordered or expanded-schedule keys are tested.',
                        'Assumes direct DTB/SquashFS prefixes and the independently verified zboot prefix.',
                        'A negative result does not identify the GX9 cipher or exclude other memory regions.']
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(f"Verified keys: {len(report['verified_keys'])}; report: {args.out}")
    return 0 if report['verified_keys'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
