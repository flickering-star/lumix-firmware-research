"""Read the fixed 32 MiB flash window with verified, durable resume checkpoints."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

from .camera import updater_transport
from .models import MODELS
from .protocol import Service

BASE, SIZE, BLOCK = 0x40000000, 32*1024*1024, 1024
PAGES = range(BASE, BASE+SIZE, BLOCK)
SLEEP_INSTRUCTIONS = (
    'Before starting, use normal camera mode: MENU/SET → Setup (wrench) → '
    'Economy → Sleep Mode → OFF. Then return to service mode and reconnect USB. '
    'Use a fully charged battery or the correct external power adapter, and keep '
    'the computer awake. A full 32 MiB copy can take an hour or longer. '
    'If it stops, wake/reconnect the same camera, choose Data backup again, and '
    'select the SAME backup folder to resume. The app never changes sleep settings.')


class BackupError(ValueError):
    pass


def digest(raw): return hashlib.sha256(raw).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()


def save_json(path, data):
    pending = path.with_name(path.name+'.tmp')
    with pending.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(pending, path)


@contextmanager
def exclusive(root):
    """OS-owned lock: an interrupted process never leaves an unresumable lock."""
    with (root/'backup.lock').open('a+b') as lock:
        lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise BackupError('This backup folder is already open in another operation') from error
        try: yield
        finally:
            if sys.platform == 'win32':
                lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def verify_prefix(root):
    """Trust only complete journal records whose saved blocks still hash exactly.

    The data is fsynced before its journal record. A crash can therefore leave
    extra data or a partial final record; these uncommitted tails are discarded
    after the committed prefix is fully checked.
    """
    partial, final = root/'flash32m.bin.part', root/'flash32m.bin'
    if partial.exists() and final.exists(): raise BackupError('Backup contains both partial and final images; keep the folder for inspection')
    data_path = final if final.exists() else partial
    journal_path = root/'blocks.jsonl'
    if not data_path.exists():
        if journal_path.exists() and journal_path.stat().st_size:
            raise BackupError('The saved backup data is missing')
        data_path.touch(exist_ok=False)
    records = []; full = hashlib.sha256(); committed_journal = 0
    with journal_path.open('a+b') as journal, data_path.open('rb') as stream:
        journal.seek(0)
        while line := journal.readline():
            if not line.endswith(b'\n'):
                break
            try: record = json.loads(line)
            except (ValueError, UnicodeDecodeError) as error:
                raise BackupError('A saved backup checkpoint is corrupt') from error
            index = len(records)
            if (index >= SIZE//BLOCK or set(record) != {'index', 'sha256'} or type(record['index']) is not int
                    or record['index'] != index):
                raise BackupError('The saved backup checkpoint order is invalid')
            raw = stream.read(BLOCK)
            if len(raw) != BLOCK or digest(raw) != record['sha256']:
                raise BackupError(f'Saved backup block {index} failed verification. Keep this folder and start a new backup in another folder.')
            records.append(record); full.update(raw); committed_journal = journal.tell()
        if final.exists() and (len(records)*BLOCK != SIZE or stream.read(1)):
            raise BackupError('The final backup image is incomplete or has extra data')
        # Preserve every verified committed block, and remove only interrupted
        # bytes that never acquired a complete durable checkpoint record.
        journal.truncate(committed_journal); journal.flush(); os.fsync(journal.fileno())
    if not final.exists():
        with partial.open('r+b') as stream:
            stream.truncate(len(records)*BLOCK); stream.flush(); os.fsync(stream.fileno())
    return data_path, records, full


def copy_flash(destination, transport_factory=None, progress=lambda *_: None, cancel=None):
    """Backup works without a patch inspection or a supported firmware revision."""
    root = Path(destination).expanduser().absolute(); root.mkdir(parents=True, exist_ok=True)
    with exclusive(root):
        metadata_path = root/'camera.json'
        if not metadata_path.exists():
            unexpected = [p for p in root.iterdir() if p.name != 'backup.lock']
            if unexpected: raise BackupError('Choose an empty folder, or an existing Data backup folder')
        metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else None
        if metadata is not None and (metadata.get('schema') != 1 or metadata.get('base') != BASE
                or metadata.get('bytes') != SIZE or metadata.get('block_bytes') != BLOCK
                or metadata.get('camera', {}).get('model') not in MODELS):
            raise BackupError('This folder has a different backup format or camera model')
        # A new folder has no data/checkpoints until identity is known.
        records, full, data_path = [], hashlib.sha256(), root/'flash32m.bin.part'
        if metadata is not None:
            progress('Verifying saved backup blocks', 0, SIZE)
            data_path, records, full = verify_prefix(root)
        try:
            if len(records)*BLOCK < SIZE:
                with (transport_factory or updater_transport)() as transport:
                    identity = dict(transport.identity)
                    if identity.get('model') not in MODELS: raise BackupError('Data backup supports GM1 and GM5 service cameras')
                    if metadata is not None and identity != metadata['camera']:
                        raise BackupError('The connected camera identity differs from this backup. Reconnect the original camera or choose a new folder.')
                    if metadata is None:
                        metadata = dict(schema=1, created_utc=now(), camera=identity, base=BASE,
                                        bytes=SIZE, block_bytes=BLOCK, camera_writes=False)
                        save_json(metadata_path, metadata)
                        data_path, records, full = verify_prefix(root)
                    service = Service(transport, PAGES, model=identity['model'])
                    # Reconnect validation uses beginning/middle/end of the
                    # committed prefix. It never substitutes a different body.
                    if records:
                        with data_path.open('rb') as stream:
                            for index in sorted({0, len(records)//2, len(records)-1}):
                                stream.seek(index*BLOCK); expected = stream.read(BLOCK)
                                if service.read(BASE+index*BLOCK) != expected:
                                    raise BackupError('Camera data changed at a resume checkpoint. Keep this backup and start a new one in another folder.')
                    with data_path.open('ab') as stream, (root/'blocks.jsonl').open('ab') as journal:
                        for index in range(len(records), SIZE//BLOCK):
                            if cancel is not None and cancel.is_set():
                                raise BackupError('Backup paused. Select this same folder to resume.')
                            raw = service.read(BASE+index*BLOCK)
                            if len(raw) != BLOCK: raise BackupError('Incomplete camera backup block')
                            record = dict(index=index, sha256=digest(raw))
                            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                            journal.write((json.dumps(record, separators=(',', ':'))+'\n').encode('ascii'))
                            journal.flush(); os.fsync(journal.fileno())
                            records.append(record); full.update(raw)
                            done = (index+1)*BLOCK
                            progress(f'Backing up {done/1048576:.2f} / 32 MiB ({done*100//SIZE}%)', done, SIZE)
            progress('Verifying the saved 32 MiB image', SIZE, SIZE)
            data_path, checked, saved_hash = verify_prefix(root)
            if len(checked)*BLOCK != SIZE or saved_hash.hexdigest() != full.hexdigest():
                raise BackupError('The saved full backup failed final verification')
            if data_path.name.endswith('.part'):
                os.replace(data_path, root/'flash32m.bin')
            result = dict(schema=1, complete=True, completed_utc=now(), camera=metadata['camera'],
                          base=BASE, bytes=SIZE, verified_blocks=len(records), sha256=full.hexdigest(),
                          image='flash32m.bin', camera_writes=False, patch_compatibility_verified=False,
                          note='Complete recovery backup: sequential read of the entire mapped 32 MiB flash window. Not an atomic snapshot; no automatic restore or patch compatibility is implied.')
            save_json(root/'backup.json', result)
            (root/'SHA256SUMS').write_text(result['sha256']+'  flash32m.bin\n', encoding='ascii')
            progress('Data backup complete — 32 MiB verified', SIZE, SIZE)
            return dict(result, folder=str(root))
        except Exception as error:
            if metadata is not None:
                save_json(root/'backup.json', dict(schema=1, complete=False, stopped_utc=now(),
                    camera=metadata['camera'], verified_bytes=len(records)*BLOCK, total_bytes=SIZE,
                    error=str(error), camera_writes=False))
            raise BackupError(str(error)+'\n\nVerified blocks are saved. Wake/reconnect the camera, choose Data backup, '
                              'and select the same folder to resume.\n'+str(root)) from error
