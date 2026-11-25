#!/usr/bin/env python3
"""Audit both native source-built updater ZIPs and their shipped Python code."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import types
import zipfile

from PyInstaller.archive.readers import CArchiveReader
from lumix_updater_release_check import archive_catalog


def sha(raw): return hashlib.sha256(raw).hexdigest()
def require(ok, why):
    if not ok: raise ValueError(why)


def audit(source, mac_file, windows_file, output):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    current = {p.name: sha(p.read_bytes()) for p in (source/'apps/lumix_updater').glob('*.py')}
    catalog = sha((source/'apps/lumix_updater/patches/catalog.json').read_bytes())
    packages = []
    with tempfile.TemporaryDirectory(prefix='updater-code-audit-', dir=output) as temporary:
        for platform, receipt_file, library_hash in (
            ('macOS Apple Silicon', mac_file, '84d8fb6c55b3c4ed821c751fa5b90bd1bdbbbe0cb58fcde563dc6d829cfb3cf5'),
            ('Windows x64', windows_file, '698752cd7f4634c36a7e5dd18006ef27b839fd851db571b3991c750351d8bf55')):
            mac = platform.startswith('macOS'); receipt = json.loads(receipt_file.read_text(encoding='utf-8-sig'))
            expected = current if mac else {p.name: sha(p.read_bytes().replace(b'\n', b'\r\n'))
                for p in (source/'apps/lumix_updater').glob('*.py')}
            require(receipt['source_sha256'] == expected and receipt['patch_catalog_sha256'] == catalog,
                    'Compiled-source/catalog receipt differs')
            require(not receipt['camera_contacted'] and not receipt['firmware_binaries_or_camera_keys_bundled'], 'Build scope')
            if mac:
                require(not receipt['runtime_checks_skipped'] and receipt['gui_smoke']['passed']
                        and all(receipt['selftest'][key] for key in ('codec_selftest','usb_library_loaded','bundled_tls_roots_loaded')),
                        'Mac frozen runtime and real GUI checks')
            archive = receipt_file.parent/('Lumix-Firmware-Updater-darwin-arm64.zip' if mac else 'Lumix-Firmware-Updater-win32-x86_64.zip')
            require(archive.stat().st_size == receipt['archive']['bytes']
                    and sha(archive.read_bytes()) == receipt['archive']['sha256'], 'Actual ZIP bytes differ')
            shipped = archive_catalog(archive, catalog)
            with zipfile.ZipFile(archive) as z:
                names = z.namelist(); suffix = '.dylib' if mac else '.dll'
                match = [name for name in names if name.endswith('/apps/lumix_updater/native/libusb-1.0'+suffix)]
                require(len(match) == 1 and sha(z.read(match[0])) == library_hash, 'Exact previously tested USB library')
                require(any(name.endswith('/_tcl_data/init.tcl') for name in names)
                        and any(name.endswith('/_tk_data/tk.tcl') for name in names), 'Missing Tcl/Tk runtime')
                executable = Path(receipt['executable'])
                if not mac:
                    exes = [name for name in names if name.endswith('/Lumix Firmware Updater.exe')]
                    require(len(exes) == 1, 'One Windows application executable')
                    executable = Path(temporary)/'windows.exe'; executable.write_bytes(z.read(exes[0]))
                pyz = CArchiveReader(str(executable)).open_embedded_archive('PYZ.pyz')
                require('tkinter' in pyz.toc, 'Missing GUI Python code')
                compiled = []
                for path in sorted((source/'apps/lumix_updater').glob('*.py')):
                    module = 'apps.lumix_updater'+('' if path.stem == '__init__' else '.'+path.stem)
                    require(module in pyz.toc, 'Missing shipped application module '+module)
                    actual = pyz.extract(module)
                    require(isinstance(actual, types.CodeType) and actual == compile(path.read_bytes(), actual.co_filename,
                            'exec', dont_inherit=True, optimize=0), 'Shipped bytecode differs from source '+module)
                    compiled.append(module)
                require('apps.lumix_updater.backup' in compiled and 'apps.lumix_updater.layout' not in pyz.toc,
                        'New backup / removed override module inventory')
            packages.append(dict(platform=platform, archive=archive.name, path=str(archive),
                bytes=archive.stat().st_size, sha256=sha(archive.read_bytes()), shipped=shipped,
                source_sha256=current, compiled_application_modules=compiled, application_code_matches_source=True,
                GUI_runtime_present=True, frozen_runtime_and_GUI_executed=mac,
                usb_library_sha256=library_hash, build_receipt_sha256=sha(receipt_file.read_bytes())))
    result = dict(schema=1, time_utc=datetime.now(timezone.utc).isoformat(), passed=True, packages=packages,
        source_sha256=current, catalog_sha256=catalog, camera_contacted=False,
        source_sha256_auditor=sha(Path(__file__).read_bytes()), physical_backup_workflow_verified=False)
    (output/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(passed=True, packages=2, compiled_modules_per_app=len(compiled), camera_contacted=False)))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--source',type=Path,required=True)
    p.add_argument('--mac-bundle',type=Path,required=True); p.add_argument('--windows-bundle',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True); a=p.parse_args(); audit(a.source,a.mac_bundle,a.windows_bundle,a.out)
