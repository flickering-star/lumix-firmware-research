#!/usr/bin/env python3
"""Reproduce the tested GM5 LUT update from the owner's exact local inputs.

Offline only. No camera I/O or SD writes. No firmware or encryption key is
bundled: the guarded recipe contains only changed bytes, and the key is read
from the supplied backup. Unknown components and output hashes are refused.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile
import zlib

from panasonic_upd import parse, PAYLOAD_START, TABLE_OFFSET, ENTRY_SIZE

ROOT=Path(__file__).resolve().parents[1]
RECIPE=ROOT/'recipes/gm5-v11-luts.json'
PACKAGE_SHA='fa17315ef8527dfad4bd72444caac786fe0a2e96d85e4802e26c68995989597d'
OFFICIAL_SHA='d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243'
LAYOUT=(('program',0,0x800000,0x7A0000),
        ('guires',0x800000,0xC00000,0xC00000),
        ('program2',0x1400000,0x360000,0x360000))


def sha(raw):return hashlib.sha256(raw).hexdigest()


def official(path):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>40*1024*1024:
        raise ValueError('Expected the official GM5 1.1 BIN or ZIP')
    raw=path.read_bytes()
    if raw.startswith(b'PK\x03\x04'):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files=[item for item in archive.infolist() if not item.is_dir()]
            if (len(files)!=1 or files[0].filename!='GM5__V11.bin'
                    or files[0].file_size!=31901184 or files[0].flag_bits&1):
                raise ValueError('Expected the official ZIP containing GM5__V11.bin')
            raw=archive.read(files[0])
    if len(raw)!=31901184 or sha(raw)!=OFFICIAL_SHA:
        raise ValueError('Official firmware SHA-256 differs from the reviewed GM5 1.1 input')
    return raw


def edits(source,records):
    """Require bounded, ordered, disjoint replacements with exact preimages."""
    output=bytearray(source);end=0
    for record in records:
        at=record['offset']
        if type(at) is not int:
            raise ValueError('Patch offset must be an integer')
        before,after=bytes.fromhex(record['before']),bytes.fromhex(record['after'])
        if (not 1<=len(before)<=256 or len(before)!=len(after)
                or at<end or at+len(before)>len(output) or output[at:at+len(before)]!=before):
            raise ValueError('Patch preimage, bounds or ordering differs')
        output[at:at+len(before)]=after;end=at+len(before)
    return bytes(output)


def components(backup,recipe):
    if len(backup)!=0x2000000:
        raise ValueError('A complete 32 MiB backup of this camera is required')
    if len(recipe['components'])!=3:
        raise ValueError('Expected exactly three reviewed program components')
    result=[]
    for item,(name,at,size,write) in zip(recipe['components'],LAYOUT):
        if (item['name'],item['destination'],item['bytes'],item['write_bytes'])!=(name,at,size,write):
            raise ValueError('Recipe component geometry differs')
        raw=backup[at:at+size]
        if name=='program':
            baseline=next((b for b in recipe['accepted_main_baselines'] if b['sha256']==sha(raw)),None)
            if baseline is None:
                raise ValueError('Unsupported installed main. Keep your original stock/policy/language backup.')
            raw=edits(raw,baseline['normalize'])
        if sha(raw)!=item['source_sha256']:
            raise ValueError('Backup component differs from the reviewed factory build: '+name)
        patched=edits(raw,item['edits'])
        if sha(patched)!=item['target_sha256']:
            raise ValueError('Patched component SHA-256 differs: '+name)
        if name=='program':
            if (struct.unpack_from('<2H',patched,0x6A0)!=(0x111,0x111)
                    or patched[0x6B1BDC:0x6B1BDE]!=bytes(2)
                    or patched[write:]!=b'\xff'*(size-write)):
                raise ValueError('Patched revision/policy or saved-bank exclusion differs')
        result.append((name,at,patched[:write]))
    return result


def codec_run(codec,arguments):
    result=subprocess.run([str(codec),*map(str,arguments)],capture_output=True,timeout=300)
    if result.returncode:
        # The command contains a locally recovered key. Never echo its argv.
        raise ValueError('Native firmware codec failed; no verified output was published')


def package(template,parts,ciphertexts,recipe):
    templates={e['name']:e for e in parse(template)}
    output=bytearray(template[:PAYLOAD_START])+b''.join(ciphertexts)
    output[0x200]=0;output[0x220:0x260]=bytes(64)
    struct.pack_into('<HH',output,0x1C,0x011F,0x011F)
    struct.pack_into('<I',output,0x3C,len(output)-512)
    output[0x2A0:0x2E0]=output[:64]
    struct.pack_into('<I',output,0x2E8,3)
    output[TABLE_OFFSET:PAYLOAD_START]=bytes(PAYLOAD_START-TABLE_OFFSET)
    position=PAYLOAD_START
    for i,(name,destination,plain) in enumerate(parts):
        entry=templates[name]
        struct.pack_into('<12s4I32s16s16s',output,TABLE_OFFSET+ENTRY_SIZE*i,
            name.encode('ascii'),position-512,len(plain),destination,3,
            hashlib.sha256(plain).digest(),bytes.fromhex(entry['field16_hex']),
            bytes.fromhex(entry['reserved16_hex']))
        position+=len(plain)
    struct.pack_into('<I',output,0x40,zlib.crc32(output[512:]))
    if (len(output)!=24118784 or recipe['package_bytes']!=len(output)
            or recipe['package_sha256']!=PACKAGE_SHA or sha(output)!=PACKAGE_SHA):
        raise ValueError('Final update differs from the exact tested LUT package')
    parsed=parse(output,allow_unsigned=True)
    for entry,(name,destination,plain) in zip(parsed,parts):
        if (entry['name'],entry['destination_offset_candidate'],entry['size'],entry['field32_hex'])!=(
                name,destination,len(plain),sha(plain)):
            raise ValueError('Final update directory differs from the reviewed components')
    return bytes(output)


def build(firmware_path,backup_path,codec_path,output):
    output=Path(output).absolute();codec=Path(codec_path).resolve()
    if output.exists():raise FileExistsError('Choose a new output directory')
    recipe=json.loads(RECIPE.read_text(encoding='utf-8'))
    if recipe['schema']!=1 or recipe['id']!='gm5-0111-luts-fa17315e':
        raise ValueError('Unsupported LUT recipe')
    backup_path=Path(backup_path)
    if backup_path.stat().st_size!=0x2000000:
        raise ValueError('A complete 32 MiB backup of this camera is required')
    backup=backup_path.read_bytes();parts=components(backup,recipe)
    page=backup[0x64B400:0x64B800];key=page[0xCC:0xDC]
    if sha(page)!=recipe['key_page_sha256'] or sha(key)!=recipe['key_sha256']:
        raise ValueError('Backup encryption-key page differs from the reviewed build')
    template=official(firmware_path)
    entries={e['name']:e for e in parse(template)}
    codec_run(codec,['--selftest'])
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.gm5-luts-',dir=output.parent) as temporary:
        temporary=Path(temporary);ciphertexts=[]
        for name,_,plain in parts:
            source=temporary/(name+'.plain');encoded=temporary/(name+'.encoded')
            decoded=temporary/(name+'.decoded')
            source.write_bytes(plain)
            codec_run(codec,['--encrypt',source,encoded,key.hex(),entries[name]['field16_hex'],0,len(plain)])
            codec_run(codec,[encoded,decoded,key.hex(),entries[name]['field16_hex'],0,len(plain)])
            if decoded.read_bytes()!=plain:raise ValueError('Complete component codec round trip differs')
            ciphertexts.append(encoded.read_bytes())
        raw=package(template,parts,ciphertexts,recipe)
        ready=temporary/'ready';ready.mkdir()
        target=ready/'GM5__V11.bin';target.write_bytes(raw)
        if sha(target.read_bytes())!=PACKAGE_SHA:raise ValueError('Saved package verification failed')
        report=dict(schema=1,recipe=recipe['id'],package_sha256=PACKAGE_SHA,bytes=len(raw),
            components=[dict(name=n,destination=d,bytes=len(p),sha256=sha(p)) for n,d,p in parts],
            official_input_sha256=sha(template),recipe_sha256=sha(RECIPE.read_bytes()),
            codec_sha256=sha(codec.read_bytes()),complete_component_codec_round_trips=True,
            exact_owner_tested_package=True,settings_calibration_arm_components_excluded=True,
            saved_lut_banks_excluded=True,key_in_report=False,camera_contacted=False,sd_card_written=False)
        (ready/'build-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        (ready/'SHA256SUMS').write_text(PACKAGE_SHA+'  GM5__V11.bin\n',encoding='utf-8')
        if output.exists():raise FileExistsError('Output directory appeared during preparation')
        os.rename(ready,output)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware',type=Path,required=True,help='Official GM5 1.1 BIN or ZIP')
    parser.add_argument('--backup',type=Path,required=True,help='Your complete 32 MiB NOR backup')
    parser.add_argument('--codec',type=Path,required=True,help='Locally built panasonic-aes5 executable')
    parser.add_argument('--out',type=Path,required=True,help='New output directory')
    args=parser.parse_args()
    try:
        result=build(args.firmware,args.backup,args.codec,args.out)
        print('Reproduced the tested GM5 LUT update: '+result['package_sha256'])
    except (OSError,ValueError,KeyError,zipfile.BadZipFile,subprocess.TimeoutExpired) as error:
        parser.exit(1,'LUT package refused: '+str(error)+'\n')
