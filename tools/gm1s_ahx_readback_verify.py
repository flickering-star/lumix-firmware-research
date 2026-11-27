#!/usr/bin/env python3
"""Verify retained GM1S before/after AHX policy captures, entirely offline.

Requires the original full backup and the two capture directories. No USB
library, camera connection, firmware generation or memory write is involved.
The public report contains addresses, values and hashes, never raw captures,
firmware bytes, calibration contents or USB serials.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct

ORIGINAL_SHA = '31a976014477704164844ccb9618bf5e920f50a0cc250ecf824ca9189d5f3230'
PAGES = (0x40000400, 0x40692400, 0x70A4E800, 0x701A7400, 0x41FE9400)
ROM, RAM = 0x40692634, 0x70A4EBC4


def sha(raw): return hashlib.sha256(raw).hexdigest()


def require(ok, message):
    if not ok: raise ValueError(message)


def capture(folder):
    report = json.loads((folder/'report.json').read_text())
    require(report['passed'] and report['model'] == 'DMC-GM1S'
            and report['camera_ram_or_flash_writes'] == 0 and not report['automatic_retries'],
            'Capture is not a successful read-only GM1S inspection')
    rows = [json.loads(line) for line in (folder/'frames.jsonl').read_text().splitlines()]
    require([row['address'] for row in rows] == list(PAGES), 'Unexpected/duplicate/missing read addresses')
    pages = {}
    for row in rows:
        address = row['address']
        request = bytearray(1030); request[:4] = b'\x01\0\xff\x5c'
        struct.pack_into('<II', request, 4, address, address+1024)
        request[-2] = sum(request[1:-2]) & 255
        wire = bytes.fromhex(row['response_hex'])
        require(bytes.fromhex(row['request_hex']) == request, 'Saved request is not the exact fixed memory read')
        require(len(wire) == 1030 and wire[:4] == b'\x01\0\xff\x05'
                and not wire[-1] and wire[-2] == sum(wire[1:-2]) & 255,
                'Invalid response framing/checksum')
        data = wire[4:-2]
        require(data != request[4:-2] and data == (folder/(format(address, '08x')+'.data')).read_bytes(),
                'Saved payload differs or request buffer was not replaced')
        pages[address] = data
    require(len(report['reads']) == 5 and all(item['bytes'] == 1024
            and item['sha256'] == sha(pages[int(item['address'], 0)]) for item in report['reads']),
            'Reported block lengths/hashes disagree with saved wire frames')
    require(report['ROM_policy'] == struct.unpack_from('<H', pages[0x40692400], ROM-0x40692400)[0]
            and report['RAM_policy'] == struct.unpack_from('<H', pages[0x70A4E800], RAM-0x70A4E800)[0]
            and report['native_flash_type'] == pages[0x701A7400][0x2ED], 'Reported policy/type disagrees with actual payload')
    return report, pages


def verify(backup_path, before_dir, after_dir):
    backup = backup_path.read_bytes()
    require(len(backup) == 0x2000000 and sha(backup) == ORIGINAL_SHA, 'Pinned complete original backup changed')
    before, old = capture(before_dir); after, new = capture(after_dir)
    require((before['ROM_policy'], before['RAM_policy']) == (1, 1)
            and (after['ROM_policy'], after['RAM_policy']) == (0, 0), 'Expected physical1/1 ->0/0 policy transition')
    changes = [0x40692400+i for i, (a, b) in enumerate(zip(old[0x40692400], new[0x40692400])) if a != b]
    require(changes == [ROM], 'Another byte in the complete flash policy page changed')
    for address in (0x40000400, 0x40692400, 0x41FE9400):
        require(old[address] == backup[address-0x40000000:address-0x40000000+1024], 'Before-update flash page differs from original backup')
    for address in (0x40000400, 0x41FE9400, 0x701A7400):
        require(new[address] == old[address], 'Header/calibration/type guard changed')
    require(struct.unpack_from('<2H', new[0x40000400], 0x2A0) == (0x106, 0x106)
            and after['native_flash_type'] == before['native_flash_type'] == 4, 'Revision/flash type differs')
    old_identity = json.loads((before_dir/'private-identity.json').read_text())
    new_identity = json.loads((after_dir/'private-identity.json').read_text())
    require(old_identity == new_identity and old_identity['model'] == 'DMC-GM1S', 'Before/after USB identity differs')
    return dict(schema=1, passed=True, verified_at_utc=datetime.now(timezone.utc).isoformat(),
                model='DMC-GM1S', internal_revision='0x0106', original_backup_bytes=len(backup), original_backup_sha256=sha(backup),
                policy=dict(flash_address=hex(ROM), RAM_address=hex(RAM), flash_before=1, flash_after=0, RAM_before=1, RAM_after=0,
                            flash_page_changed_bytes=1, flash_page_changed_addresses=[hex(address) for address in changes]),
                before_time_utc=before['time_utc'], after_time_utc=after['time_utc'],
                native_flash_type=4, verified_wire_frames=10, bytes_per_capture=5120,
                before_pages=before['reads'], after_pages=after['reads'],
                USB_identity_matches=True, USB_serial_is_nonempty=bool(old_identity.get('serial')),
                agent_camera_memory_writes=0, automatic_retries=False,
                header_and_sampled_fixed_calibration_unchanged=True, complete_post_update_flash_readback=False,
                additional_manual_power_cycle_tested=False, offline_verifier_sha256=sha(Path(__file__).read_bytes()),
                scope='Consistency of retained wire responses and source-backup guards; no device I/O or independent hardware attestation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.backup, args.before, args.after)
    with args.out.open('x') as output: output.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(passed=True, policy=result['policy'], verified_wire_frames=10)), flush=True)
