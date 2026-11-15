#!/usr/bin/env python3
"""Package the minimal Windows build inputs without firmware or camera keys."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

REPO=Path(__file__).resolve().parents[1]

BUILD_SCRIPT=r'''param(
    [string]$Python = "py",
    [string]$Compiler = "",
    [string]$BundleOutput = ""
)
$ErrorActionPreference = "Stop"
function Invoke-LumixChecked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Executable (exit $LASTEXITCODE)" }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    $lumixCommand = Get-Command $Python -ErrorAction Stop
    $lumixLauncher = $lumixCommand.Source
    $lumixLauncherArgs = @()
    if ([IO.Path]::GetFileNameWithoutExtension($lumixLauncher) -eq "py") {
        $lumixLauncherArgs = @("-3")
    }
    $lumixCheck = "import sys,struct; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required'; assert struct.calcsize('P') == 8, '64-bit Python is required'"
    Invoke-LumixChecked $lumixLauncher ($lumixLauncherArgs + @("-c", $lumixCheck))
    $lumixEnvironment = Join-Path $PSScriptRoot ".build\venv"
    if (-not (Test-Path -LiteralPath (Join-Path $lumixEnvironment "Scripts\python.exe"))) {
        Invoke-LumixChecked $lumixLauncher ($lumixLauncherArgs + @("-m", "venv", $lumixEnvironment))
    }
    $lumixPython = Join-Path $lumixEnvironment "Scripts\python.exe"
    Invoke-LumixChecked $lumixPython @("-m", "pip", "install", "-r", "apps\requirements-updater.txt")
    Invoke-LumixChecked $lumixPython @("-m", "unittest", "discover", "-s", "tests", "-p", "test_lumix_updater.py")
    if (-not $BundleOutput) {
        $BundleOutput = Join-Path $PSScriptRoot ("dist\windows-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    }
    $lumixBuildArgs = @("tools\lumix_updater_bundle.py", "--assets", "patches", "--out", $BundleOutput, "--arch", "x86_64")
    if ($Compiler) { $lumixBuildArgs += @("--cc", $Compiler) }
    Invoke-LumixChecked $lumixPython $lumixBuildArgs
    Write-Host "Standalone Windows app and ZIP saved in: $BundleOutput"
} finally {
    Pop-Location
}
'''


def sha(raw):return hashlib.sha256(raw).hexdigest()


def pack(output,assets):
    import sys
    sys.path.insert(0,str(REPO))
    from apps.lumix_updater.firmware import catalog
    assets=assets.resolve();_,manifest=catalog(assets)
    expected={'catalog.json'}
    for choice in manifest['choices'].values():
        for part in choice['components'].values():
            name=part['file']
            if name:
                if Path(name).name!=name or sha((assets/name).read_bytes())!=part['patch_sha256']:
                    raise ValueError('Patch file is missing or changed')
                expected.add(name)
    if {p.name for p in assets.iterdir()}!=expected:
        raise ValueError('Undeclared files in patch directory')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    kit=output/'Lumix-Updater-Windows-Build'
    files=[Path('apps/__init__.py'),Path('apps/lumix_updater_launcher.py'),
           Path('apps/requirements-updater.txt'),Path('apps/README.md'),
           Path('tools/panasonic_aes5.c'),Path('tools/lumix_updater_bundle.py'),
           Path('tests/test_lumix_updater.py')]
    files+=sorted(p.relative_to(REPO) for p in (REPO/'apps/lumix_updater').glob('*.py'))
    files.append(Path('apps/lumix_updater/codec_bridge.c'))
    for relative in files:
        source=REPO/relative;target=kit/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    for name in sorted(expected):
        target=kit/'patches'/name;target.parent.mkdir(exist_ok=True)
        shutil.copyfile(assets/name,target)
    (kit/'BUILD-WINDOWS.ps1').write_text(BUILD_SCRIPT,encoding='utf-8')
    (kit/'README.txt').write_text(
        'Windows build inputs, not a prebuilt Windows application.\n\n'
        'Use 64-bit Python 3.11+ with Tk. Open the Visual Studio x64 Native Tools '
        'prompt (or put a 64-bit MinGW gcc on PATH), then run:\n\n'
        'powershell -NoProfile -ExecutionPolicy Bypass -File .\\BUILD-WINDOWS.ps1\n\n'
        'The script creates a private build environment, installs its Python '
        'dependencies, runs the host tests, builds the EXE folder and ZIP, then '
        'runs frozen self-tests and the GUI smoke check. It does not open USB, '
        'change drivers/firewall, or contact a camera. See apps/README.md for '
        'supported cameras, installation workflow and limitations.\n',encoding='utf-8')
    checks={str(p.relative_to(kit)):sha(p.read_bytes()) for p in sorted(kit.rglob('*')) if p.is_file()}
    (kit/'SHA256SUMS').write_text(''.join(h+'  '+n+'\n' for n,h in checks.items()),encoding='utf-8')
    archive=output/'Lumix-Updater-Windows-Build.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(kit.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(output))
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('Build-kit ZIP failed integrity check')
        for p in kit.rglob('*'):
            if p.is_file() and z.read(str(p.relative_to(output)))!=p.read_bytes():
                raise ValueError('Archived build input changed')
    result=dict(time_utc=datetime.now(timezone.utc).isoformat(),status='windows-build-inputs-not-executable',
        archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=sha(archive.read_bytes())),
        source_sha256=checks,patch_catalog_sha256=sha((assets/'catalog.json').read_bytes()),
        full_firmware_or_camera_key_included=False,windows_build_executed=False,camera_contacted=False)
    (output/'kit.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();print(json.dumps(pack(args.out,args.assets)['archive']))
