#!/usr/bin/env python3
"""Check the staged Git tree for private artifacts, binaries and credentials."""
from __future__ import annotations

from pathlib import PurePosixPath
import hashlib
import json
import re
import struct
import subprocess
import zlib

TEXT_SUFFIXES = {".md", ".py", ".c", ".m", ".h", ".sh", ".S", ".json", ".txt", ".igen", ".yml", ".yaml"}
TEXT_NAMES = {".gitignore", ".gitattributes", "COPYING", "LICENSE", "NOTICE", "Makefile"}
PRIVATE_ROOTS = {"work", "captures", "firmware", ".ssh", ".env"}
PATTERNS = (
    ("private-key material", re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("GitHub access token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("personal absolute path", re.compile("/"+"Users"+r"/(?!USERNAME\b)[^/\s<>]+/")),
    ("large embedded hex payload", re.compile(r"\b[0-9a-fA-F]{2048,}\b")),
)


def staged(path):
    return subprocess.check_output(['git','show',':'+path])


def catalog_deltas():
    """Only catalog-listed, hash-pinned XOR deltas may be binary artifacts."""
    root='apps/lumix_updater/patches/'
    try:
        parent=json.loads(staged(root+'catalog.json'))
    except subprocess.CalledProcessError:
        return {}
    result={}
    for model,directory in parent.get('models',{'DMC-GM5':'.'}).items():
        if model not in ('DMC-GM1','DMC-GM5') or directory not in ('.','gm1'):
            raise ValueError('Unexpected updater model/directory')
        prefix=root+('' if directory=='.' else directory+'/')
        raw=staged(prefix+'catalog.json');catalog=json.loads(raw)
        if model!='DMC-GM5' and hashlib.sha256(raw).hexdigest()!=parent['model_catalog_sha256'][model]:
            raise ValueError('Staged model catalog hash differs')
        groups=[c['components'] for c in catalog['choices'].values()]
        groups+=list(catalog.get('restore_components_by_profile',{}).values())
        for group in groups:
            for component in group.values():
                name=component['file']
                if not name:continue
                if PurePosixPath(name).name!=name or not name.endswith('.lxdp'):
                    raise ValueError('Invalid updater delta path')
                at=prefix+name;digest=component['patch_sha256']
                if at in result and result[at]!=digest:
                    raise ValueError('Conflicting delta hash')
                result[at]=digest
    return result


def valid_delta(raw,digest):
    if hashlib.sha256(raw).hexdigest()!=digest or len(raw)>4*1024*1024:
        return False
    decoder=zlib.decompressobj();data=decoder.decompress(raw,40*1024*1024)
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or data[:8]!=b'LUMIXDP1':
        return False
    size,count=struct.unpack_from('<II',data,8)
    if size not in (0x800000,0x900000,0xB00000,0xC00000,0x360000) or not 0<count<size:
        return False
    pos=16;end=0;covered=0
    for _ in range(count):
        if pos+8>len(data):return False
        at,n=struct.unpack_from('<II',data,pos);pos+=8
        if not n or at<end or at+n>size or pos+n>len(data):return False
        covered+=n;end=at+n;pos+=n
    # Never admit a complete firmware image disguised as a delta. The existing
    # GM5 factory/official secondary delta changes43% of its component.
    return pos==len(data) and covered<size//2


def audit() -> list[str]:
    listing = subprocess.check_output(["git", "ls-files", "--stage", "-z"])
    errors = []
    try:
        deltas=catalog_deltas()
    except (ValueError,KeyError,subprocess.CalledProcessError) as exc:
        print('Updater catalog refused: '+str(exc))
        return ['Invalid staged updater catalogs']
    count = 0
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, blob, stage = metadata.decode().split()
        path = raw_path.decode()
        name = PurePosixPath(path)
        count += 1
        if path in deltas and mode in ('100644','100755') and stage=='0':
            raw=subprocess.check_output(['git','cat-file','blob',blob])
            try:
                valid=valid_delta(raw,deltas[path])
            except (ValueError,struct.error,zlib.error):
                valid=False
            if not valid:errors.append(f'{path}: invalid or unpinned XOR delta')
            continue
        if (stage != "0" or mode not in ("100644", "100755")
                or name.parts[0] in PRIVATE_ROOTS
                or name.name == "PRIVATE.zip"
                or name.suffix not in TEXT_SUFFIXES and name.name not in TEXT_NAMES):
            errors.append(f"{path}: unapproved artifact path/type")
            continue
        raw = subprocess.check_output(["git", "cat-file", "blob", blob])
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{path}: non-text content")
            continue
        if any(byte < 32 and byte not in (9, 10, 13) for byte in raw):
            errors.append(f"{path}: binary/control characters")
        for label, pattern in PATTERNS:
            if pattern.search(text):
                errors.append(f"{path}: {label}")
    print(f"Audited {count} staged-tree files; {len(errors)} findings.")
    return errors


if __name__ == "__main__":
    findings = audit()
    for finding in findings:
        print(finding)
    raise SystemExit(bool(findings))
