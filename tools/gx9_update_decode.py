#!/usr/bin/env python3
"""Decode a GX9 UPD package and require every complete component SHA-256 to match.

Offline only. The key can come from a local 16-byte file or the pinned ARM RAM
image. Neither the key value nor proprietary plaintext is written to the report.
Plaintext outputs, when requested, belong in the private work directory.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import tempfile

from panasonic_buffer_key_check import HostCodec, selftest
from tz30_control_verify import records


MAIN_RAM_SHA = 'f6bbc883c4b845bbed2622aa386f09b0bc03f5ed20377851305bd0ccc56d5e07'
KEY_OFFSET = 0x8d0284
KEY_SHA = '527bb069f7940900d77f3878a71e9c8bc9a4ac39145a505a4b6fda83c331ac9b'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode_bytes(codec, data, key, iv):
    # The helper accepts at most 16 MiB per call. Continue CBC with the preceding
    # ciphertext block when a component spans more than one bounded call.
    output = bytearray()
    for start in range(0, len(data), 8 * 1024 * 1024):
        chunk = data[start:start + 8 * 1024 * 1024]
        source = (C.c_ubyte * len(chunk)).from_buffer_copy(chunk)
        target = (C.c_ubyte * len(chunk))()
        previous = data[start - 16:start] if start else iv
        k = (C.c_ubyte * 16).from_buffer_copy(key)
        v = (C.c_ubyte * 16).from_buffer_copy(previous)
        if codec.decrypt(source, len(chunk), target, k, v, 5) != 1:
            raise ValueError('Host codec rejected the component extent')
        output.extend(target)
    return bytes(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', type=Path)
    key_source = parser.add_mutually_exclusive_group(required=True)
    key_source.add_argument('--key-file', type=Path)
    key_source.add_argument('--main-ram', type=Path)
    parser.add_argument('--components', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.main_ram:
        source = args.main_ram.read_bytes()
        if sha(source) != MAIN_RAM_SHA:
            raise ValueError('Expected the verified ARM RAM acquisition')
        key = source[KEY_OFFSET:KEY_OFFSET + 16]
    else:
        key = args.key_file.read_bytes()
    if len(key) != 16 or sha(key) != KEY_SHA:
        raise ValueError('Expected the independently verified GX9 key')
    firmware = args.firmware.read_bytes()
    entries = records(firmware, b'MC282')
    report = {
        'schema': 1, 'model_id': 'MC282', 'firmware_bytes': len(firmware),
        'firmware_sha256': sha(firmware), 'algorithm': 'AES-128-CBC with five rounds',
        'key_sha256': KEY_SHA, 'key_source_arm_image_sha256': MAIN_RAM_SHA,
        'key_source_image_offset': hex(KEY_OFFSET),
        'key_source_service_address': '0x84750284',
        'verifier_sha256': sha(Path(__file__).read_bytes()),
        'camera_or_network_access': False, 'camera_writes': 0,
        'components': [], 'all_nonempty_components_verified': False,
    }
    if args.components:
        args.components.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gx9-update-decode-') as folder:
        codec = HostCodec(Path(folder))
        selftest(codec)
        for entry in entries:
            name, size, offset = entry['name'], entry['bytes'], entry['file_offset']
            if not re.fullmatch(r'[A-Za-z0-9_]+', name):
                raise ValueError('Unexpected component name')
            raw = firmware[offset:offset + size]
            if not size:
                report['components'].append({'name': name, 'bytes': 0, 'empty_record': True})
                continue
            if entry['flags'] == 3:
                plaintext = decode_bytes(codec, raw, key, bytes.fromhex(entry['field16']))
            elif entry['flags'] == 2:
                plaintext = raw
            else:
                raise ValueError('Unreviewed component flags: ' + name)
            actual = sha(plaintext)
            if actual != entry['field32']:
                raise ValueError('Complete plaintext hash differs: ' + name)
            row = {'name': name, 'bytes': size, 'flags': entry['flags'],
                   'stored_sha256': sha(raw), 'plaintext_sha256': actual,
                   'official_plaintext_sha256': entry['field32'],
                   'complete_digest_matches': True,
                   'uniform_fill_byte': plaintext[0] if plaintext.count(plaintext[:1]) == size else None}
            report['components'].append(row)
            if args.components:
                path = args.components / (name + '.plaintext.bin')
                if path.exists():
                    if sha(path.read_bytes()) != actual:
                        raise ValueError('Existing plaintext output differs: ' + name)
                else:
                    with path.open('xb') as stream:
                        stream.write(plaintext)
            args.out.write_text(json.dumps(report, indent=2) + '\n')
            print(name + ': complete plaintext hash verified', flush=True)
    report.update(all_nonempty_components_verified=True,
                  verified_nonempty_components=sum(bool(e['bytes']) for e in entries),
                  total_plaintext_bytes=sum(e['bytes'] for e in entries),
                  directory_records=len(entries))
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(str(report['verified_nonempty_components']) + ' nonempty components verified; no camera access.')


if __name__ == '__main__':
    main()
