#!/usr/bin/env python3
"""Build a standalone desktop app on its target OS, without camera access."""
import argparse
from datetime import datetime,timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from apps.lumix_updater.download import sha
from apps.lumix_updater.firmware import catalog,catalog_assets


def run(args,log,*,env=None):
    with log.open('ab') as stream:
        subprocess.run([str(arg) for arg in args],check=True,stdout=stream,stderr=subprocess.STDOUT,env=env)


def bundle(output,assets,*,architecture=None,cc=None,skip_checks=False):
    if sys.platform not in ('darwin','win32'):
        raise ValueError('Build the Mac app on macOS or the Windows app on Windows')
    if sys.version_info<(3,11):raise ValueError('Use a supported Python 3.11 or newer build environment')
    import libusb_package
    import certifi
    import tkinter
    import PyInstaller
    assets=assets.resolve();_,manifest=catalog(assets)
    allowed_files,profiles=catalog_assets(assets)
    usb=Path(libusb_package.find_library('libusb-1.0')).resolve()
    if not usb.is_file():raise ValueError('Install the native libusb-package for this architecture')
    output=output.absolute();output.mkdir(mode=0o700,parents=True,exist_ok=False)
    (output/'builder-source.py').write_bytes(Path(__file__).read_bytes())
    log=output/'build.log';native=output/'native';native.mkdir()
    source=REPO/'apps/lumix_updater/codec_bridge.c'
    if sys.platform=='darwin':
        target=architecture or platform.machine()
        if target not in ('arm64','x86_64','universal2'):raise ValueError('Unsupported macOS architecture')
        codec=native/'liblumix-codec.dylib';compiler=cc or shutil.which('clang')
        if not compiler:raise ValueError('Install the macOS command-line compiler')
        slices=['arm64','x86_64'] if target=='universal2' else [target]
        run([compiler,'-dynamiclib','-O2','-fvisibility=hidden',
             *[value for arch in slices for value in ('-arch',arch)],source,'-o',codec],log)
    else:
        target=architecture or 'x86_64'
        if target!='x86_64' or platform.machine().lower() not in ('amd64','x86_64'):
            raise ValueError('The initial Windows bundle requires 64-bit x86 Python')
        codec=native/'lumix-codec.dll';compiler=cc or shutil.which('cl') or shutil.which('gcc')
        if not compiler:raise ValueError('Use the Visual Studio x64 Native Tools prompt or a 64-bit MinGW compiler')
        if Path(compiler).name.lower() in ('cl','cl.exe'):
            run([compiler,'/nologo','/O2','/LD','/MT',source,'/Fo'+str(native/'codec.obj'),
                 '/link','/OUT:'+str(codec)],log)
        else:
            run([compiler,'-shared','-O2','-static-libgcc',source,'-o',codec],log)
    name='Lumix Firmware Updater'
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
        '--name',name,'--distpath',output/'dist','--workpath',output/'work','--specpath',output,
        '--paths',REPO,'--add-data',str(assets)+':apps/lumix_updater/patches',
        '--add-binary',str(codec)+':apps/lumix_updater/native',
        '--add-binary',str(usb)+':apps/lumix_updater/native',
        '--collect-data','certifi','--exclude-module','libusb_package',
        '--exclude-module','pytest']
    if sys.platform=='darwin':command+=['--target-arch',target,
        '--osx-bundle-identifier','research.lumix.firmware-updater']
    command+=[REPO/'apps/lumix_updater_launcher.py'];run(command,log)
    app=output/'dist'/(name+'.app' if sys.platform=='darwin' else name)
    executable=app/('Contents/MacOS/'+name if sys.platform=='darwin' else name+'.exe')
    checked=None;gui=None
    if not skip_checks:
        report=output/'bundle-selftest.json'
        # Tests must work without the private build interpreter or its library paths.
        clean_env={key:value for key,value in os.environ.items() if key not in
            ('PYTHONHOME','PYTHONPATH','DYLD_FRAMEWORK_PATH','DYLD_LIBRARY_PATH','SSL_CERT_FILE','SSL_CERT_DIR')}
        run([executable,'--self-test-report',report],log,env=clean_env)
        checked=json.loads(report.read_text())
        if (not checked['codec_selftest'] or not checked['usb_library_loaded']
                or not checked['bundled_tls_roots_loaded'] or checked['camera_contacted']):
            raise ValueError('Frozen application self-test failed')
        gui_report=output/'gui-smoke.json'
        run([executable,'--gui-smoke-report',gui_report],log,env=clean_env)
        gui=json.loads(gui_report.read_text())
        if not gui['passed'] or gui['camera_contacted']:raise ValueError('Frozen desktop UI check failed')
    # Preserve a relocatable archive with application symlinks intact.
    archive=output/(name.replace(' ','-')+'-'+sys.platform+'-'+target+'.zip')
    if sys.platform=='darwin':
        run(['/usr/bin/ditto','-c','-k','--sequesterRsrc','--keepParent',app,archive],log)
    else:shutil.make_archive(str(archive.with_suffix('')),'zip',root_dir=app.parent,base_dir=app.name)
    result=dict(schema=1,time_utc=datetime.now(timezone.utc).isoformat(),
        status='experimental-desktop-test',platform=sys.platform,architecture=target,
        supported_models=list(profiles),
        python=sys.version,pyinstaller=PyInstaller.__version__,app=str(app),executable=str(executable),
        archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=sha(archive.read_bytes())),
        source_sha256={p.name:sha(p.read_bytes()) for p in (REPO/'apps/lumix_updater').glob('*.py')},
        patch_catalog_sha256=sha((assets/'catalog.json').read_bytes()),
        dependencies={name:importlib.metadata.version(name) for name in
                      ('certifi','libusb-package','pyinstaller')},selftest=checked,gui_smoke=gui,
        runtime_checks_skipped=skip_checks,
        firmware_binaries_or_camera_keys_bundled=False,camera_contacted=False,
        actual_camera_usb_workflow_verified=False,published=False)
    (output/'bundle.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(result['archive']['sha256']+'  '+archive.name+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--arch',choices=('arm64','x86_64','universal2'))
    parser.add_argument('--cc',help='C compiler executable')
    parser.add_argument('--skip-checks',action='store_true',help='Package without running the app self-test or GUI check')
    args=parser.parse_args();result=bundle(args.out,args.assets,architecture=args.arch,cc=args.cc,skip_checks=args.skip_checks)
    print(json.dumps(dict(status=result['status'],archive=result['archive'],selftest=result['selftest'])))
