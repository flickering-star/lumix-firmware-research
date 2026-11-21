#!/usr/bin/env python3
"""Assemble a Windows candidate from the owner-tested0.1.1 native runtime.

Run with the same CPython3.12.3 bytecode compiler as the original Windows app.
Only application PYZ entries and patch catalogs/deltas change. The PE loader,
bootstrap bytecode, Windows standard library and every native DLL/PYD are
preserved. This produces an actual Windows EXE, NOT a Windows execution test.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import marshal
from pathlib import Path
import struct
import sys
import types
import zipfile
import zlib

REPO=Path(__file__).resolve().parents[1]
PARENT_SHA='b2c4427c2d441f0734b8b8542eeb49e574944544e743a81f80ec9de2c05c831d'
ROOT='Lumix Firmware Updater/'
EXE=ROOT+'Lumix Firmware Updater.exe'
PATCHES=ROOT+'_internal/apps/lumix_updater/patches/'
COOKIE='!8sIIII64s'
COOKIE_MAGIC=b'MEI\x0c\x0b\x0a\x0b\x0e'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def carchive(raw):
    length=struct.calcsize(COOKIE)
    magic,size,toc_at,toc_size,version,pylib=struct.unpack(COOKIE,raw[-length:])
    if magic!=COOKIE_MAGIC or version!=312 or pylib.rstrip(b'\0')!=b'python312.dll':
        raise ValueError('Expected the exact reviewed Windows CPython3.12 archive')
    start=len(raw)-size
    if not 0<start<start+toc_at<=start+toc_at+toc_size==len(raw)-length:
        raise ValueError('Invalid parent archive extents')
    entries=[];pos=start+toc_at;names=set()
    while pos<start+toc_at+toc_size:
        n,offset,packed,plain,compressed,kind=struct.unpack_from('!IIIIBc',raw,pos)
        if n<18 or n%16 or pos+n>start+toc_at+toc_size:
            raise ValueError('Invalid parent archive record size')
        name=raw[pos+18:pos+n].split(b'\0',1)[0].decode('utf-8')
        if name in names or compressed not in (0,1) or offset+packed>toc_at:
            raise ValueError('Duplicate/out-of-range parent archive record')
        payload=raw[start+offset:start+offset+packed]
        unpacked=zlib.decompress(payload) if compressed else payload
        if len(unpacked)!=plain:raise ValueError('Parent archive record size mismatch')
        entries.append(dict(name=name,kind=kind,payload=payload,unpacked=unpacked,compressed=compressed))
        names.add(name);pos+=n
    return start,entries,pylib


def rewrite_pyz(raw,modules):
    if raw[:4]!=b'PYZ\0' or raw[4:8]!=importlib.util.MAGIC_NUMBER:
        raise ValueError('Windows PYZ and the local compiler have different bytecode versions')
    toc_at=struct.unpack_from('!i',raw,8)[0];original=marshal.loads(raw[toc_at:])
    if not isinstance(original,list) or len(original)!=len(dict(original)):
        raise ValueError('Expected a unique ordered PYZ table')
    out=bytearray(raw[:min(v[1] for _,v in original)]);toc=[];unchanged={};app_records={}
    old=dict(original)
    for name in [*(n for n,_ in original),*(n for n in sorted(modules) if n not in old)]:
        if name in modules:
            path,package=modules[name];source=path.read_bytes()
            code=compile(source,str(path.relative_to(REPO)).replace('\\','/'),'exec',dont_inherit=True,optimize=0)
            if not isinstance(code,types.CodeType):raise ValueError('Application compilation failed')
            marshalled=marshal.dumps(code)
            packed=zlib.compress(marshalled,6);kind=1 if package else 0
            if marshal.loads(zlib.decompress(packed))!=code:raise ValueError('Bytecode round trip differs')
            app_records[name]=dict(source_path=str(path.relative_to(REPO)),source_sha256=sha(source),
                                   marshalled_code_sha256=sha(marshalled),package=package)
        else:
            if name=='apps' or name.startswith('apps.'):
                raise ValueError('Undeclared old application module would survive')
            kind,pos,n=old[name];packed=raw[pos:pos+n]
            unchanged[name]=sha(packed)
        toc.append((name,(kind,len(out),len(packed))));out.extend(packed)
    struct.pack_into('!i',out,8,len(out));out.extend(marshal.dumps(toc))
    # Parse independently from the serialized table and verify every retained
    # standard-library entry plus every compiled application code object.
    checked=dict(marshal.loads(out[struct.unpack_from('!i',out,8)[0]:]))
    for name,digest in unchanged.items():
        _,at,n=checked[name]
        if sha(out[at:at+n])!=digest:raise ValueError('A Windows library bytecode entry changed')
    for name,record in app_records.items():
        _,at,n=checked[name];marshalled=zlib.decompress(out[at:at+n]);marshal.loads(marshalled)
        if sha(marshalled)!=record['marshalled_code_sha256']:
            raise ValueError('Compiled application entry differs')
    return bytes(out),app_records,unchanged


def pe_checksum(raw,offset):
    value=0
    for i in range(0,len(raw),2):
        if offset<=i<offset+4:continue
        word=raw[i]+((raw[i+1] if i+1<len(raw) else 0)<<8)
        value+=word;value=(value&0xFFFF)+(value>>16)
    value=(value&0xFFFF)+(value>>16)
    return (value+len(raw))&0xFFFFFFFF


def rewrite_exe(raw,modules):
    if raw[:2]!=b'MZ':raise ValueError('Expected a Windows PE executable')
    pe=struct.unpack_from('<I',raw,0x3C)[0]
    if raw[pe:pe+4]!=b'PE\0\0' or struct.unpack_from('<H',raw,pe+4)[0]!=0x8664:
        raise ValueError('Expected the tested Windows x64 PE loader')
    optional=pe+24
    if struct.unpack_from('<H',raw,optional)[0]!=0x20B or raw[optional+144:optional+152]!=bytes(8):
        raise ValueError('Expected PE32+ without an Authenticode overlay')
    start,records,pylib=carchive(raw);prefix=bytearray(raw[:start]);checksum_at=optional+64
    section_table=optional+struct.unpack_from('<H',raw,pe+20)[0]
    sections=struct.unpack_from('<H',raw,pe+6)[0]
    for i in range(sections):
        size,position=struct.unpack_from('<II',raw,section_table+40*i+16)
        if position+size>start:raise ValueError('Native PE section overlaps the appended archive')
    data=bytearray();toc=bytearray();apps=None;unchanged=None
    for r in records:
        packed=r['payload'];plain_size=len(r['unpacked'])
        if r['kind']==b'z':
            if r['name']!='PYZ.pyz' or r['compressed'] or apps is not None:
                raise ValueError('Unexpected embedded PYZ inventory')
            packed,apps,unchanged=rewrite_pyz(r['unpacked'],modules);plain_size=len(packed)
        name=r['name'].encode('utf-8')+b'\0';length=(18+len(name)+15)&~15
        toc.extend(struct.pack('!IIIIBc',length,len(data),len(packed),plain_size,r['compressed'],r['kind'])+
                   name+bytes(length-18-len(name)))
        data.extend(packed)
    if apps is None:raise ValueError('No application archive')
    cookie=struct.pack(COOKIE,COOKIE_MAGIC,len(data)+len(toc)+struct.calcsize(COOKIE),len(data),len(toc),312,pylib)
    out=prefix+data+toc+cookie
    struct.pack_into('<I',out,checksum_at,pe_checksum(out,checksum_at))
    before=bytearray(raw[:start]);after=bytearray(out[:start])
    before[checksum_at:checksum_at+4]=bytes(4);after[checksum_at:checksum_at+4]=bytes(4)
    if before!=after:raise ValueError('Native loader/PE resources changed outside the checksum')
    check_start,checked,_=carchive(out)
    if check_start!=start or len(checked)!=len(records):raise ValueError('Rebuilt EXE archive differs')
    for old,new in zip(records,checked):
        if old['name']!=new['name'] or old['kind']!=new['kind']:
            raise ValueError('Native bootstrap archive inventory changed')
        if old['name']!='PYZ.pyz' and old['payload']!=new['payload']:
            raise ValueError('A native bootstrap bytecode record changed')
    return bytes(out),dict(application_modules=apps,unchanged_pyz_entry_sha256=unchanged,
        native_loader_prefix_bytes=start,native_loader_unchanged_except_checksum=True,
        windows_bootstrap_records_preserved=len(records)-1,python_archive_version=312,
        executable_checksum=hex(struct.unpack_from('<I',out,checksum_at)[0]))


def repack(output,parent,assets):
    if sys.version_info[:3]!=(3,12,3):raise ValueError('Use the exact matching private CPython3.12.3 compiler')
    sys.path.insert(0,str(REPO))
    from apps.lumix_updater.firmware import catalog_assets
    from apps.lumix_updater import __version__
    if sha(parent.read_bytes())!=PARENT_SHA:raise ValueError('The owner-tested Windows parent archive differs')
    expected,profiles=catalog_assets(assets)
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    (output/'builder-source.py').write_bytes(Path(__file__).read_bytes())
    modules={'apps':(REPO/'apps/__init__.py',True),'apps.lumix_updater':(REPO/'apps/lumix_updater/__init__.py',True)}
    for f in sorted((REPO/'apps/lumix_updater').glob('*.py')):
        if f.stem!='__init__':modules['apps.lumix_updater.'+f.stem]=(f,False)
    target=output/'Lumix-Firmware-Updater-win32-x86_64.zip'
    preserved={};new_members={};excluded=[]
    with zipfile.ZipFile(parent) as old,zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as new:
        if old.testzip():raise ValueError('Owner-tested parent ZIP CRC differs')
        entries=old.infolist()
        if len(entries)!=len({e.filename for e in entries}):raise ValueError('Duplicate parent ZIP member')
        for entry in entries:
            name=entry.filename
            if name.startswith(PATCHES):excluded.append(name);continue
            raw=old.read(entry)
            if name==EXE:
                raw,details=rewrite_exe(raw,modules)
                new_members[name]=sha(raw)
            else:preserved[name]=sha(raw)
            new.writestr(entry,raw)
        for name,digest in expected.items():
            raw=(assets/name).read_bytes()
            if sha(raw)!=digest:raise ValueError('Catalog changed during assembly')
            member=PATCHES+name.replace('\\','/');new.writestr(member,raw)
            new_members[member]=digest
    with zipfile.ZipFile(target) as z:
        if z.testzip():raise ValueError('Rebuilt Windows ZIP CRC differs')
        if set(z.namelist())!=set(preserved)|set(new_members):raise ValueError('Undeclared Windows archive contents')
        for name,digest in {**preserved,**new_members}.items():
            if sha(z.read(name))!=digest:raise ValueError('Windows archive member changed')
        # Re-read the final shipped EXE, not the preceding in-memory buffer.
        _,final_records,_=carchive(z.read(EXE))
        pyz=next(r['unpacked'] for r in final_records if r['name']=='PYZ.pyz')
        pyz_toc=dict(marshal.loads(pyz[struct.unpack_from('!i',pyz,8)[0]:]))
        for name,record in details['application_modules'].items():
            _,at,n=pyz_toc[name];marshalled=zlib.decompress(pyz[at:at+n]);marshal.loads(marshalled)
            if sha(marshalled)!=record['marshalled_code_sha256']:raise ValueError('Shipped app code differs')
    result=dict(schema=1,time_utc=datetime.now(timezone.utc).isoformat(),version=__version__,
        status='assembled-windows-candidate-execution-pending',platform='win32',architecture='x86_64',
        compiler_python=sys.version,assembly_platform=sys.platform,
        parent_archive=str(parent),parent_sha256=PARENT_SHA,
        archive=dict(path=str(target),bytes=target.stat().st_size,sha256=sha(target.read_bytes())),
        source_sha256={q.name:sha(q.read_bytes()) for q in (REPO/'apps/lumix_updater').glob('*.py')},
        patch_catalog_sha256=sha((assets/'catalog.json').read_bytes()),supported_models=list(profiles),
        unchanged_zip_member_sha256=preserved,replaced_zip_member_sha256=new_members,
        removed_old_patch_members=excluded,bytecode=details,
        windows_executable_assembled=True,windows_execution_verified=False,
        native_dll_pyd_and_stdlib_preserved=True,original_owner_test_does_not_cover_new_code=True,
        firmware_binaries_or_camera_keys_bundled=False,camera_contacted=False,published=False)
    (output/'assembly.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(result['archive']['sha256']+'  '+target.name+'\n')
    print(json.dumps(dict(status=result['status'],archive=result['archive'],windows_execution_verified=False)),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--parent',type=Path,required=True);p.add_argument('--assets',type=Path,required=True)
    a=p.parse_args();repack(a.out,a.parent,a.assets)
