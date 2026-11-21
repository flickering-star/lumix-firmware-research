#!/usr/bin/env python3
"""Independently parse a cross-assembled Windows candidate; never execute it.

Use PyInstaller's readers and pefile, not the assembler's parsers. Compare the
actual shipped code to fresh compilation and every non-application library to
the owner-tested parent. A green audit is not Windows runtime validation.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import marshal
from pathlib import Path,PurePosixPath
import sys
import tempfile
import zipfile
import zlib

import pefile
from PyInstaller.archive.readers import CArchiveReader

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
sys.path.insert(0,str(REPO/'tools'))
from lumix_updater_release_check import archive_catalog


def sha(raw):return hashlib.sha256(raw).hexdigest()


def audit(output,assembly,mac_bundle):
    if sys.version_info[:3]!=(3,12,3):raise ValueError('Use the matching CPython3.12.3 bytecode reader')
    b=json.loads(assembly.read_text());mac=json.loads(mac_bundle.read_text())
    target=Path(b['archive']['path']);parent=Path(b['parent_archive'])
    if (sha(target.read_bytes())!=b['archive']['sha256'] or sha(parent.read_bytes())!=b['parent_sha256']
            or b['windows_execution_verified'] or b['status']!='assembled-windows-candidate-execution-pending'):
        raise ValueError('Need the exact unexecuted assembled candidate and parent')
    sources={q.name:sha(q.read_bytes()) for q in (REPO/'apps/lumix_updater').glob('*.py')}
    if sources!=b['source_sha256'] or sources!=mac['source_sha256']:
        raise ValueError('Mac/Windows/current application sources differ')
    if b['patch_catalog_sha256']!=mac['patch_catalog_sha256']:raise ValueError('Mac and Windows catalogs differ')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    (output/'audit-source.py').write_bytes(Path(__file__).read_bytes())
    shipped=archive_catalog(target,b['patch_catalog_sha256'])
    executable='Lumix Firmware Updater/Lumix Firmware Updater.exe'
    patch_root='Lumix Firmware Updater/_internal/apps/lumix_updater/patches/'
    with zipfile.ZipFile(parent) as old,zipfile.ZipFile(target) as new,tempfile.TemporaryDirectory(dir=output) as tmp:
        names=new.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate candidate ZIP member')
        for name in names:
            if '..' in PurePosixPath(name).parts or name.startswith('/') or '\\' in name:
                raise ValueError('Unsafe candidate ZIP path')
        nonpatch={n for n in old.namelist() if not n.startswith(patch_root)}
        if nonpatch!={n for n in names if not n.startswith(patch_root)}:
            raise ValueError('Nonpatch ZIP inventory changed')
        preserved={}
        for name in nonpatch-{executable}:
            if old.read(name)!=new.read(name):raise ValueError('Native library or runtime file changed: '+name)
            preserved[name]=sha(new.read(name))
        before,after=old.read(executable),new.read(executable)
        po=pefile.PE(data=before);pn=pefile.PE(data=after)
        if (po.FILE_HEADER.Machine,pn.FILE_HEADER.Machine)!=(0x8664,0x8664):raise ValueError('Unexpected executable architecture')
        if pn.generate_checksum()!=pn.OPTIONAL_HEADER.CheckSum:raise ValueError('Independent PE checksum disagrees')
        old_exe,new_exe=Path(tmp)/'old.exe',Path(tmp)/'new.exe'
        old_exe.write_bytes(before);new_exe.write_bytes(after)
        oa,na=CArchiveReader(str(old_exe)),CArchiveReader(str(new_exe))
        if oa.options!=na.options or set(oa.toc)!=set(na.toc) or oa._start_offset!=na._start_offset:
            raise ValueError('Native loader archive/bootstrap inventory changed')
        offset=pn.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum')
        x,y=bytearray(before[:oa._start_offset]),bytearray(after[:na._start_offset])
        x[offset:offset+4]=bytes(4);y[offset:offset+4]=bytes(4)
        if x!=y:raise ValueError('Native PE loader changed outside its required checksum')
        for name in oa.toc:
            if name!='PYZ.pyz' and oa.extract(name)!=na.extract(name):
                raise ValueError('A Windows bootstrap code object changed')
        op,np=oa.open_embedded_archive('PYZ.pyz'),na.open_embedded_archive('PYZ.pyz')
        old_pyz,new_pyz=oa.extract('PYZ.pyz'),na.extract('PYZ.pyz')
        original_modules={n for n in op.toc if n!='apps' and not n.startswith('apps.')}
        if original_modules!={n for n in np.toc if n!='apps' and not n.startswith('apps.')}:
            raise ValueError('Windows standard/library module inventory changed')
        for name in original_modules:
            ot,at,n=op.toc[name];nt,bt,m=np.toc[name]
            if ot!=nt or old_pyz[at:at+n]!=new_pyz[bt:bt+m]:
                raise ValueError('A frozen Windows library code object changed: '+name)
        compiled={}
        for name,record in b['bytecode']['application_modules'].items():
            path=REPO/record['source_path']
            if sha(path.read_bytes())!=record['source_sha256']:raise ValueError('Application source pin differs')
            actual=np.extract(name)
            expected=compile(path.read_bytes(),record['source_path'],'exec',dont_inherit=True,optimize=0)
            if actual!=expected:raise ValueError('Shipped application code differs from fresh matching compilation: '+name)
            kind,at,n=np.toc[name]
            if kind!=int(record['package']) or sha(zlib.decompress(new_pyz[at:at+n]))!=record['marshalled_code_sha256']:
                raise ValueError('Actual application package/bytecode digest differs')
            compiled[name]=record['source_sha256']
        if set(np.toc)!=(original_modules|set(compiled)):raise ValueError('Undeclared application/library module')
        init=np.extract('apps.lumix_updater');values={}
        exec(init,values)
        if values.get('__version__')!=b['version']:raise ValueError('Shipped application version differs')
    result=dict(schema=1,time_utc=datetime.now(timezone.utc).isoformat(),passed=True,
        assembly=str(assembly),assembly_sha256=sha(assembly.read_bytes()),mac_bundle_sha256=sha(mac_bundle.read_bytes()),
        windows_archive_sha256=sha(target.read_bytes()),shipped=shipped,
        independently_parsed_pe_machine='AMD64',independent_pe_checksum=True,
        native_loader_unchanged_except_checksum=True,unchanged_runtime_zip_members=len(preserved),
        unchanged_frozen_library_modules=len(original_modules),freshly_compiled_application_modules=len(compiled),
        compiled_application_source_sha256=compiled,source_sha256=sources,
        windows_execution_verified=False,physical_camera_verified=False,
        source_sha256_auditor=sha((output/'audit-source.py').read_bytes()),camera_contacted=False)
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,application_modules=len(compiled),unchanged_library_modules=len(original_modules),
        unchanged_runtime_members=len(preserved),windows_execution_verified=False)),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--assembly',type=Path,required=True);p.add_argument('--mac-bundle',type=Path,required=True)
    a=p.parse_args();audit(a.out,a.assembly,a.mac_bundle)
