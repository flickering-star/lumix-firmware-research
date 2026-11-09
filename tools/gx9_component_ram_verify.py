#!/usr/bin/env python3
"""Verify recovered GX9 plaintext against complete official UPD component hashes.

Offline only. Keeps raw RAM captures unchanged. Optional outputs contain only
components whose entire reconstructed plaintext matches the pinned update.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from tz30_control_verify import records


OFFICIAL_SHA = 'c08354c91d083d74b274c4884ab4f06d3f72e47ea289ea80c9685f2292f5b801'
INPUTS = {
    'prelinux': (2097152, '2c858e77ed23ca2a97f57e55a116388391e3e5b6485260c974ec4986c11efa59'),
    'rootfs1': (4194304, 'ac96cc0624e6a377a35eb48b1409f7303be565992d725aa286086cec1cf95e7c'),
    'rootfs2': (9437184, 'bffcef5640aca392689c27f00efbee14b4e68b34ece3e71b797a06e71c476c7b'),
}


def device_tree(data: bytes) -> dict:
    header = struct.unpack_from('>10I', data)
    magic, total, start, strings_at, reserved, version, compatible, cpu, strings_size, size = header
    if (magic != 0xD00DFEED or version != 17 or total > len(data)
            or start % 4 or start + size > total or strings_at + strings_size > total):
        raise ValueError('FDT header/extent differs')
    strings = data[strings_at:strings_at + strings_size]
    offset, stack, nodes, properties = start, [], [], []
    ended = False
    while offset < start + size:
        tag = struct.unpack_from('>I', data, offset)[0]
        offset += 4
        if tag == 1:
            end = data.find(b'\0', offset, start + size)
            if end < 0:
                raise ValueError('Unterminated FDT node')
            stack.append(data[offset:end].decode('ascii'))
            offset = (end + 4) & ~3
            nodes.append('/' + '/'.join(name for name in stack if name))
        elif tag == 2:
            if not stack:
                raise ValueError('Invalid FDT nesting')
            stack.pop()
        elif tag == 3:
            length, name_at = struct.unpack_from('>II', data, offset)
            offset += 8
            if not stack or name_at >= len(strings) or offset + length > start + size:
                raise ValueError('Invalid FDT property')
            end = strings.find(b'\0', name_at)
            if end < 0:
                raise ValueError('Unterminated FDT property name')
            name = strings[name_at:end].decode('ascii')
            value = data[offset:offset + length]
            offset = (offset + length + 3) & ~3
            row = {'node': nodes[0] if len(stack) == 1 else '/' + '/'.join(n for n in stack if n),
                   'property': name, 'bytes': length, 'value_hex': value.hex()}
            if name in ('compatible', 'status', 'bootargs', 'device_type', 'clock-names',
                        'model', 'clock-output-names'):
                row['strings'] = value.rstrip(b'\0').decode('ascii').split('\0')
            properties.append(row)
        elif tag == 4:
            continue
        elif tag == 9:
            if stack or offset != start + size:
                raise ValueError('FDT end/nesting differs')
            ended = True
            break
        else:
            raise ValueError('Unexpected FDT tag')
    if not ended or len(nodes) != 18 or len(properties) != 81:
        raise ValueError('Complete GX9 FDT structure differs')
    return {'total_size': total, 'version': version, 'nodes': nodes,
            'properties': properties, 'structure_parsed_to_end': True}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(firmware: bytes, captures: dict[str, bytes]) -> tuple[dict, dict[str, bytes]]:
    if sha(firmware) != OFFICIAL_SHA:
        raise ValueError('Expected the pinned official GX9 1.5 binary')
    directory = {entry['name']: entry for entry in records(firmware, b'MC282')}
    for label, (size, digest) in INPUTS.items():
        if len(captures[label]) != size or sha(captures[label]) != digest:
            raise ValueError('Captured input differs: ' + label)
    report = {'schema': 1, 'firmware_sha256': OFFICIAL_SHA,
              'firmware_version': '1.5', 'camera_version_owner_reported': '1.4',
              'camera_or_network_access': False, 'key_recovered': False,
              'raw_captures_modified': False, 'components': []}
    outputs = {}

    stub = captures['prelinux'][0x120000:0x120800]
    entry = directory['zboot']
    if entry['flags'] != 3 or entry['bytes'] != len(stub) or sha(stub) != entry['field32']:
        raise ValueError('Captured zboot does not match the complete official plaintext digest')
    outputs['zboot'] = stub
    report['components'].append({
        'component': 'zboot', 'service_start': '0x80120000', 'bytes': len(stub),
        'plaintext_sha256': sha(stub), 'official_plaintext_sha256': entry['field32'],
        'complete_digest_matches': True, 'reconstruction': 'Exact RAM slice; no byte changes',
        'stored_update_sha256': sha(firmware[entry['file_offset']:entry['file_offset'] + entry['bytes']]),
        'update_bytes_equal_plaintext': firmware[entry['file_offset']:entry['file_offset'] + entry['bytes']] == stub,
    })

    for label in ('rootfs1', 'rootfs2'):
        data, entry = captures[label], directory[label]
        if data[:4] != b'hsqs' or struct.unpack_from('<HH', data, 28) != (4, 0):
            raise ValueError('SquashFS header differs')
        used = struct.unpack_from('<Q', data, 40)[0]
        kept = (used + 4095) & ~4095
        if not 96 <= used <= kept <= len(data) <= entry['bytes'] or entry['flags'] != 3:
            raise ValueError('SquashFS/record extent differs')
        candidate = data[:kept] + b'\xff' * (entry['bytes'] - kept)
        if sha(candidate) != entry['field32']:
            raise ValueError('Reconstructed component does not match the complete official digest: ' + label)
        changed = [offset for offset in range(kept, len(data)) if data[offset] != 255]
        # In both captures only the final four bytes of the mapped region differ.
        if changed != list(range(len(data) - 4, len(data))):
            raise ValueError('Unexpected changes in the captured image padding')
        if data[-4:] != bytes.fromhex('40010000'):
            raise ValueError('Mapped-region footer differs')
        outputs[label] = candidate
        report['components'].append({
            'component': label, 'captured_bytes': len(data), 'captured_sha256': sha(data),
            'squashfs_bytes_used': used, 'captured_prefix_kept_bytes': kept,
            'official_component_bytes': entry['bytes'],
            'reconstruction': 'Preserve SquashFS through its 4-KiB boundary; restore remaining update padding to ff',
            'changed_captured_byte_offsets': [hex(offset) for offset in changed],
            'original_mapped_footer_hex': data[-4:].hex(),
            'appended_padding_bytes': entry['bytes'] - len(data),
            'plaintext_sha256': sha(candidate), 'official_plaintext_sha256': entry['field32'],
            'complete_digest_matches': True,
        })

    words = {offset: struct.unpack_from('<I', stub, offset)[0]
             for offset in (0x58, 0x68, 0x6C, 0x70, 0x160, 0x164, 0x168)}
    expected = {0x58: 0xE59F2100, 0x68: 0xE59F20F4, 0x6C: 0xE59F30F4,
                0x70: 0xE1A0F003, 0x160: 0x90200000,
                0x164: 0x922FF000, 0x168: 0x92300000}
    if words != expected:
        raise ValueError('Verified zboot native handoff differs')
    report['zboot_handoff'] = {
        'inferred_execution_base': '0x90120000',
        'base_evidence': 'Adjacent shared control at service 0x80128000 contains pointer 0x90120000; native stub and DTB layout agree',
        'core_three_entry_physical_address': '0x92300000',
        'core_three_r2_physical_address': '0x922ff000',
        'hypothesis': 'Linux boot image and device-tree handoff addresses, based on native register setup',
        'candidate_service_entry': '0x82300000',
        'candidate_service_r2': '0x822ff000',
        'these_service_addresses_read_in_this_report': False,
        'native_words_checked': {hex(offset): hex(value) for offset, value in words.items()},
    }
    if 'handoff' in captures:
        handoff = captures['handoff']
        if len(handoff) != 5120 or sha(handoff) != '7a8f9c7d216428708a9c15e310568d7f94b892d7da5b32419ff6491b7a20f768':
            raise ValueError('Pinned handoff-region capture differs')
        dtb, entry = handoff[:4096], directory['dtb']
        if len(dtb) != entry['bytes'] or sha(dtb) != entry['field32']:
            raise ValueError('Captured DTB does not match the complete official digest')
        outputs['dtb'] = dtb
        report['components'].append({
            'component': 'dtb', 'service_start': '0x822ff000', 'bytes': len(dtb),
            'plaintext_sha256': sha(dtb), 'official_plaintext_sha256': entry['field32'],
            'complete_digest_matches': True, 'reconstruction': 'Exact RAM slice; no byte changes',
        })
        report['device_tree'] = device_tree(dtb)
        report['zboot_handoff'].update(
            these_service_addresses_read_in_this_report=True,
            entry_sample_bytes=1024, entry_sample_sha256=sha(handoff[4096:]),
            entry_sample_has_standard_arm_zimage_magic=struct.unpack_from('<I', handoff, 4096 + 0x24)[0] == 0x016F2818,
        )
    report['limits'] = [
        'These matches recover selected plaintext components, not the GX9 encryption key or complete flash contents.',
        'Rootfs2 includes three MiB of reconstructed ff padding beyond its captured nine-MiB mapping; its entire twelve-MiB official digest matches.',
        'The captures came from the owner-reported 1.4 camera; these particular components match the official 1.5 records.',
        'A boot handoff address does not guarantee that its original bytes survive in live RAM after boot.',
        'No firmware or camera memory was written.',
    ]
    return report, outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--prelinux', type=Path, required=True)
    parser.add_argument('--rootfs1', type=Path, required=True)
    parser.add_argument('--rootfs2', type=Path, required=True)
    parser.add_argument('--handoff-heads', type=Path, help='Optional verified 5-KiB handoff-region capture containing the DTB')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--components', type=Path, help='Optional directory for verified plaintext components')
    args = parser.parse_args()
    captures = {label: getattr(args, label).read_bytes() for label in INPUTS}
    if args.handoff_heads:
        captures['handoff'] = args.handoff_heads.read_bytes()
    report, outputs = verify(args.firmware.read_bytes(), captures)
    report['verifier_sha256'] = sha(Path(__file__).read_bytes())
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    if args.components:
        args.components.mkdir(parents=True, exist_ok=True)
        for name, data in outputs.items():
            (args.components / (name + '.plaintext.bin')).write_bytes(data)
    print('Complete official plaintext digests match: ' + ', '.join(outputs) + '.')


if __name__ == '__main__':
    main()
