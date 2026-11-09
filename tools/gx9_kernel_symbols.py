#!/usr/bin/env python3
"""Recover GX9 Linux symbols from a pinned six-MiB USB RAM capture, offline.

This reads the captured kernel's own lookup-function literals and compressed
symbol tables. It never opens the camera, network or an extracted executable.
The combined input spans several captures and is not a simultaneous snapshot.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct


INPUT_SHA256 = '3d84fc929a16f46a190170d2f3ac1d8d9a4b0e19365137aba3a7ddcb71403b78'
VIRTUAL_BASE = 0xC0000000
SERVICE_BASE = 0x80200000
INPUT_BYTES = 6 * 1024 * 1024
EXPORT_START, EXPORT_END = 0x3E53A0, 0x3EE2E8

# Instruction offsets and literal values traced in this GX9's native code.
LOADS = {
    'count': (0x721F4, 0xE59F3060, 0xC036B410),
    'addresses': (0x72238, 0x059F3020, 0xC0350F20),
    'names': (0x720E8, 0xE59F207C, 0xC036B420),
    'token_index': (0x72100, 0xE59F7068, 0xC03B6190),
    'token_table': (0x72108, 0xE59F8064, 0xC03B5E10),
}


def recover(data: bytes) -> tuple[dict, list[dict]]:
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != INPUT_BYTES or digest != INPUT_SHA256:
        raise ValueError('Expected the verified GX9 six-MiB combined kernel capture')

    def word(offset: int) -> int:
        return struct.unpack_from('<I', data, offset)[0]

    def string(offset: int, maximum: int = 256) -> bytes:
        if not 0 <= offset < len(data):
            raise ValueError('String pointer outside capture')
        end = data.find(b'\0', offset, min(offset + maximum, len(data)))
        if end < 0:
            raise ValueError('Unterminated table string')
        return data[offset:end]

    locations, native = {}, []
    for name, (offset, instruction, expected) in LOADS.items():
        if word(offset) != instruction or instruction & 0x0FFF0000 != 0x059F0000:
            raise ValueError('Native lookup instruction differs: ' + name)
        literal = offset + 8 + (instruction & 0xFFF)
        if word(literal) != expected:
            raise ValueError('Native lookup literal differs: ' + name)
        locations[name] = expected - VIRTUAL_BASE
        native.append({'table': name, 'instruction_virtual_address': hex(VIRTUAL_BASE + offset),
                       'instruction_word': hex(instruction),
                       'literal_virtual_address': hex(VIRTUAL_BASE + literal),
                       'table_virtual_address': hex(expected)})

    count = word(locations['count'])
    if count != 26938:
        raise ValueError('Kernel symbol count differs')
    addresses = struct.unpack_from('<' + str(count) + 'I', data, locations['addresses'])
    if any(a > b for a, b in zip(addresses, addresses[1:])):
        raise ValueError('Kernel symbol addresses are not sorted')
    indices = struct.unpack_from('<256H', data, locations['token_index'])
    tokens = [string(locations['token_table'] + offset) for offset in indices]
    offset, markers, symbols = locations['names'], [], []
    for number, address in enumerate(addresses):
        if number % 256 == 0:
            markers.append(offset - locations['names'])
        length = data[offset]
        if not length:
            raise ValueError('Empty compressed symbol')
        full = b''.join(tokens[token] for token in data[offset + 1:offset + length + 1])
        offset += length + 1
        if not full or any(byte < 33 or byte > 126 for byte in full):
            raise ValueError('Invalid expanded symbol')
        symbols.append({'virtual_address': hex(address), 'type': chr(full[0]),
                        'name': full[1:].decode('ascii')})

    marker_start = (offset + 15) & ~15
    actual_markers = struct.unpack_from('<' + str(len(markers)) + 'I', data, marker_start)
    if tuple(markers) != actual_markers:
        raise ValueError('Reconstructed stream disagrees with saved marker table')

    by_name = defaultdict(set)
    for symbol in symbols:
        by_name[symbol['name']].add(int(symbol['virtual_address'], 16))
    anchors = {'_stext': 0xC0008180, 'kallsyms_expand_symbol.constprop.3': 0xC00720E8,
               'kallsyms_lookup_name': 0xC00721F4, '_einittext': 0xC043AD8C}
    for name, address in anchors.items():
        if address not in by_name[name]:
            raise ValueError('Decoded symbol disagrees with native anchor: ' + name)

    matched, data_only = 0, []
    for position in range(EXPORT_START, EXPORT_END, 8):
        address, name_address = struct.unpack_from('<II', data, position)
        name = string(name_address - VIRTUAL_BASE).decode('ascii')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.]*', name):
            raise ValueError('Invalid export name')
        if name in by_name:
            if address not in by_name[name]:
                raise ValueError('Export address disagrees with compressed symbols: ' + name)
            matched += 1
        else:
            if not VIRTUAL_BASE + 0x440000 <= address < VIRTUAL_BASE + len(data):
                raise ValueError('Unexpected export absent from text/rodata symbol table')
            data_only.append(name)
    if matched != 4357 or len(data_only) != 228:
        raise ValueError('Independent export comparison differs')

    terms = ('uart', 'pl011', '8250', 'kgdb', 'kdb_', 'usb_gadget', 'g_serial',
             'ttyGS', 'nand_scan', 'nand_read', 'spi_nor', 'physmap', 'slram')
    selected_names = set(anchors) | {'slram_read', 'mtd_read', 'get_mtd_device',
                                    'init_slram', 'pvc_map_io', 'call_usermodehelper'}
    report = {
        'schema': 1, 'input_bytes': len(data), 'input_sha256': digest,
        'service_start': hex(SERVICE_BASE),
        'service_end_exclusive': hex(SERVICE_BASE + len(data)),
        'virtual_base_for_this_capture': hex(VIRTUAL_BASE),
        'simultaneous_snapshot': False, 'camera_or_network_access': False,
        'native_lookup_literals': native, 'symbols': count,
        'symbol_types': dict(Counter(symbol['type'] for symbol in symbols)),
        'name_stream_end_virtual_address': hex(VIRTUAL_BASE + offset),
        'marker_table_virtual_address': hex(VIRTUAL_BASE + marker_start),
        'marker_entries_checked': len(markers), 'all_markers_match': True,
        'export_comparison': {'entries': matched + len(data_only),
                              'matching_symbols': matched, 'address_disagreements': 0,
                              'data_exports_absent_from_text_rodata_symbols': len(data_only)},
        'selected_symbols': [symbol for symbol in symbols if symbol['name'] in selected_names],
        'symbol_name_search': {term: sum(term in symbol['name'] for symbol in symbols)
                               for term in terms},
        'limits': [
            'Core kernel text/rodata/init symbols only; writable data and separately loaded modules are not an exhaustive part of this table.',
            'A driver-like symbol does not establish that hardware was registered or probed.',
            'An absent symbol-name substring is not an exhaustive hardware capability test.',
            'No kernel function was executed and no shell or flash read was enabled.',
        ],
    }
    return report, symbols


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('memory', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--symbols', type=Path, help='Optional full symbol list for private analysis')
    args = parser.parse_args()
    report, symbols = recover(args.memory.read_bytes())
    report['decoder_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    if args.symbols:
        args.symbols.write_text(''.join(symbol['virtual_address'][2:] + ' ' + symbol['type'] +
                                       ' ' + symbol['name'] + '\n' for symbol in symbols))
    print(f"Recovered {len(symbols):,} core kernel symbols; all 106 markers and 4,357 export addresses agree.")


if __name__ == '__main__':
    main()
