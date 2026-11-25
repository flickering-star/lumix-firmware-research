"""Backup interruption/integrity tests over a read-only framed camera peer."""
from pathlib import Path
import hashlib
import json
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

from apps.lumix_updater.backup import (BASE, SIZE, BLOCK, BackupError, copy_flash, exclusive, verify_prefix)
from apps.lumix_updater.protocol import checksum


def block(index):
    return struct.pack('<I', index)*256


class Peer:
    def __init__(self, model='DMC-GM1', fail=None):
        self.identity = dict(model=model, serial='backup-test-body', usb_release=0x100)
        self.fail = fail; self.reads = []; self.changed = None

    def __call__(self): return self
    def __enter__(self): return self
    def __exit__(self, *_): pass

    def exchange(self, request, kind, size):
        assert (kind, size, len(request)) == (1, 1030, 1030), 'Backup attempted a camera write'
        assert request[:4] == bytes.fromhex('0100ff5c') and request[-2] == checksum(request)
        at, end = struct.unpack_from('<II', request, 4)
        assert BASE <= at < BASE+SIZE and at % BLOCK == 0 and end == at+BLOCK
        index = (at-BASE)//BLOCK; self.reads.append(index)
        if index == self.fail: raise RuntimeError('Simulated disconnect')
        raw = bytearray(block(index))
        if index == self.changed: raw[0] ^= 1
        response = bytearray(bytes.fromhex('0100ff05')+raw+b'\0\0'); response[-2] = checksum(response)
        return bytes(response)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)/'backup'

    def tearDown(self): self.temp.cleanup()

    def interrupted(self, model='DMC-GM1'):
        peer = Peer(model, fail=5)
        with self.assertRaisesRegex(BackupError, 'same folder'):
            copy_flash(self.root, peer)
        self.assertEqual((self.root/'flash32m.bin.part').read_bytes(), b''.join(block(i) for i in range(5)))
        self.assertEqual(json.loads((self.root/'backup.json').read_text())['verified_bytes'], 5*BLOCK)
        return peer

    def test_entire_32m_resume_hash_final_address_and_completed_reopen(self):
        self.interrupted(); peer = Peer(); progress = []
        # Avoid 65,536 filesystem barriers in a synthetic full-window test;
        # interruption and cancel tests above/below use actual fsync calls.
        with patch('apps.lumix_updater.backup.os.fsync'):
            report = copy_flash(self.root, peer, lambda _, done, total: progress.append((done, total)))
        expected = b''.join(block(i) for i in range(SIZE//BLOCK))
        self.assertTrue(report['complete']); self.assertEqual(report['bytes'], 33554432)
        self.assertEqual((self.root/'flash32m.bin').read_bytes(), expected)
        self.assertEqual(report['sha256'], hashlib.sha256(expected).hexdigest())
        self.assertEqual(peer.reads[:3], [0, 2, 4]); self.assertEqual(peer.reads[3:], list(range(5, 32768)))
        self.assertEqual(progress[-1], (SIZE, SIZE)); self.assertFalse((self.root/'flash32m.bin.part').exists())
        def never(): raise AssertionError('Completed local verification opened USB')
        again = copy_flash(self.root, never)
        self.assertEqual(again['sha256'], report['sha256']); self.assertFalse(again['camera_writes'])

    def test_corrupt_disk_prefix_is_preserved_and_refused_before_camera(self):
        self.interrupted(); data = self.root/'flash32m.bin.part'; raw = bytearray(data.read_bytes()); raw[100] ^= 1
        data.write_bytes(raw)
        def never(): raise AssertionError('Corrupt backup opened USB')
        with self.assertRaisesRegex(BackupError, 'failed verification'): copy_flash(self.root, never)
        self.assertEqual(data.read_bytes(), raw)

    def test_different_body_or_changed_anchor_refused_without_append(self):
        self.interrupted(); data = (self.root/'flash32m.bin.part').read_bytes()
        for kind in ('identity', 'anchor'):
            peer = Peer()
            if kind == 'identity': peer.identity['serial'] = 'other-body'
            else: peer.changed = 2
            with self.subTest(kind=kind), self.assertRaises(BackupError): copy_flash(self.root, peer)
            self.assertEqual((self.root/'flash32m.bin.part').read_bytes(), data)
            self.assertNotIn(5, peer.reads)

    def test_crash_tails_are_discarded_only_after_verified_committed_prefix(self):
        self.interrupted()
        with (self.root/'flash32m.bin.part').open('ab') as stream: stream.write(block(5)+b'partial-data')
        with (self.root/'blocks.jsonl').open('ab') as stream: stream.write(b'{"index":5,"sha')
        _, records, full = verify_prefix(self.root)
        self.assertEqual(len(records), 5)
        self.assertEqual((self.root/'flash32m.bin.part').stat().st_size, 5*BLOCK)
        self.assertEqual(full.hexdigest(), hashlib.sha256(b''.join(block(i) for i in range(5))).hexdigest())
        self.assertTrue((self.root/'blocks.jsonl').read_bytes().endswith(b'\n'))

    def test_pause_durably_saves_current_block_and_gm5_backup_needs_no_patch_profile(self):
        stop = threading.Event(); peer = Peer('DMC-GM5')
        def progress(_, done, total):
            if done == 3*BLOCK: stop.set()
        with self.assertRaisesRegex(BackupError, 'paused'): copy_flash(self.root, peer, progress, stop)
        self.assertEqual(peer.reads, [0, 1, 2])
        self.assertEqual((self.root/'flash32m.bin.part').read_bytes(), b''.join(block(i) for i in range(3)))

    def test_nonbackup_folder_and_concurrent_operation_are_refused(self):
        self.root.mkdir(); (self.root/'unrelated.txt').write_text('keep')
        with self.assertRaisesRegex(BackupError, 'empty folder'): copy_flash(self.root, Peer())
        with exclusive(self.root):
            with self.assertRaisesRegex(BackupError, 'already open'): copy_flash(self.root, Peer())
        self.assertEqual((self.root/'unrelated.txt').read_text(), 'keep')


if __name__ == '__main__': unittest.main()
