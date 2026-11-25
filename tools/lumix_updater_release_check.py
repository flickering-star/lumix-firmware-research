#!/usr/bin/env python3
"""Check local desktop archives against their source and build receipts.

This is read-only validation, not publication or approval of camera behavior.
It opens no camera and performs no network or GitHub operations.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def sha(raw):return hashlib.sha256(raw).hexdigest()


def archive_catalog(path,expected_digest):
    """Check the actual shipped catalog and every declared delta inside the ZIP."""
    with zipfile.ZipFile(path) as archive:
        # On Windows ZipInfo.filename has already normalized backslashes.
        # Validate the original central-directory names before that rewrite.
        names=[entry.orig_filename for entry in archive.infolist()]
        if len(names)!=len(set(names)):
            raise ValueError('Duplicate archive entry')
        for entry,name in zip(archive.infolist(),names):
            p=PurePosixPath(name)
            if (name!=entry.filename or p.is_absolute() or '..' in p.parts
                    or '\\' in name or '\0' in name):
                raise ValueError('Unsafe archive path')
        if archive.testzip():raise ValueError('Desktop archive CRC differs')
        catalogs=[n for n in names if n.endswith('/apps/lumix_updater/patches/catalog.json')]
        if len(catalogs)!=1:raise ValueError('Expected one shipped patch catalog')
        raw=archive.read(catalogs[0])
        if sha(raw)!=expected_digest:raise ValueError('Shipped catalog differs from its build receipt')
        catalog=json.loads(raw)
        if catalog.get('schema')!=1 or catalog.get('model')!='DMC-GM5' or set(catalog['choices'])!={'stable','luts','restore'}:
            raise ValueError('Unexpected shipped patch catalog')
        parent=PurePosixPath(catalogs[0]).parent
        expected={'catalog.json'};patches={}
        models=catalog.get('models',{'DMC-GM5':'.'})
        if not models or any(m not in ('DMC-GM1','DMC-GM5') for m in models):
            raise ValueError('Unexpected shipped model inventory')
        for model,directory in models.items():
            current=catalog;prefix=PurePosixPath('.')
            if model!='DMC-GM5':
                if not isinstance(directory,str) or PurePosixPath(directory).name!=directory or directory in ('.','..'):
                    raise ValueError('Invalid model patch directory')
                prefix=PurePosixPath(directory);relative=str(prefix/'catalog.json');expected.add(relative)
                child=archive.read(str(parent/relative))
                if sha(child)!=catalog.get('model_catalog_sha256',{}).get(model):
                    raise ValueError('Shipped model catalog differs')
                current=json.loads(child)
            elif directory!='.':raise ValueError('GM5 patch directory must remain the catalog root')
            if current.get('schema')!=1 or current.get('model')!=model or set(current['choices'])!={'stable','luts','restore'}:
                raise ValueError('Unexpected shipped model catalog')
            component_sets=[choice['components'] for choice in current['choices'].values()]
            component_sets.extend(current.get('restore_components_by_profile',{}).values())
            for components in component_sets:
                for part in components.values():
                    name=part['file']
                    if not name:continue
                    if PurePosixPath(name).name!=name or not name.endswith('.lxdp'):
                        raise ValueError('Invalid patch filename')
                    relative=str(prefix/name);shipped=str(parent/relative)
                    if shipped not in names or sha(archive.read(shipped))!=part['patch_sha256']:
                        raise ValueError('Shipped delta differs: '+relative)
                    expected.add(relative);patches[relative]=part['patch_sha256']
        actual={str(PurePosixPath(n).relative_to(parent)) for n in names
                if n.startswith(str(parent)+'/') and not n.endswith('/')}
        if actual!=expected:raise ValueError('Undeclared data in shipped patch directory')
        if any(n.lower().endswith(('.bin','.fw','.ahx')) for n in names):
            raise ValueError('Firmware-like binary found in desktop archive')
        return dict(catalog_sha256=sha(raw),patch_files=patches,archive_entries=len(names))


def check(ready,source):
    ready=Path(ready);source=Path(source)
    release=json.loads((ready/'release.json').read_text())
    if release.get('status')!='local-owner-test-pending' or release.get('published'):
        raise ValueError('Expected the local test package, not a publication claim')
    checks=[];common_catalog=None;common_sources=None
    for item in release['packages']:
        archive=ready/Path(item['path']).name
        if archive.stat().st_size!=item['bytes'] or sha(archive.read_bytes())!=item['sha256']:
            raise ValueError('Desktop package differs from the delivered test copy')
        receipt_name='mac-bundle.json' if item['platform']=='macOS Apple Silicon' else 'windows-bundle.json'
        receipt=json.loads((ready/'validation'/receipt_name).read_text(encoding='utf-8-sig'))
        if (receipt['archive']['sha256']!=item['sha256'] or receipt['archive']['bytes']!=item['bytes']
                or not receipt['gui_smoke']['passed'] or receipt['gui_smoke']['camera_contacted']
                or not all(receipt['selftest'][k] for k in ('codec_selftest','usb_library_loaded','bundled_tls_roots_loaded'))):
            raise ValueError('Frozen build checks are missing or refer to another archive')
        sources=receipt['source_sha256']
        current={p.name:sha(p.read_bytes()) for p in (source/'apps/lumix_updater').glob('*.py')}
        if current!=sources:raise ValueError('Working application source differs from the delivered executable')
        shipped=archive_catalog(archive,receipt['patch_catalog_sha256'])
        if common_catalog is not None and shipped['catalog_sha256']!=common_catalog:
            raise ValueError('The two desktop builds offer different firmware targets')
        if common_sources is not None and sources!=common_sources:
            raise ValueError('The two desktop builds use different application source')
        common_catalog,common_sources=shipped['catalog_sha256'],sources
        checks.append(dict(platform=item['platform'],archive=archive.name,bytes=item['bytes'],
                           sha256=item['sha256'],shipped=shipped))
    if {p['platform'] for p in checks}!={'macOS Apple Silicon','Windows x64'} or len(checks)!=2:
        raise ValueError('Both intended desktop builds are required')
    return dict(schema=1,time_utc=datetime.now(timezone.utc).isoformat(),passed=True,
        source_sha256=common_sources,catalog_sha256=common_catalog,packages=checks,
        owner_test_still_required=True,actual_camera_usb_workflow_proven=False,
        publication_performed=False,camera_contacted=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ready',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    result=check(args.ready,args.source)
    with args.report.open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,packages=len(result['packages']),publication_performed=False)))
