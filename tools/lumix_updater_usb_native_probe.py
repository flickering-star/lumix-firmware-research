#!/usr/bin/env python3
"""Exercise the actual ctypes USB adapter with a compiled native test library.

No operating-system USB context is opened. The replacement library has the
public descriptor ABI and explicit wire replies/faults; it is not a camera.
"""
import argparse
import ctypes as C
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from apps.lumix_updater.protocol import Service
from apps.lumix_updater.usb import Transport,USBError


def sha(raw):return hashlib.sha256(raw).hexdigest()


def proof(output,compiler=None):
    output=Path(output).absolute();output.mkdir(mode=0o700,parents=True,exist_ok=False)
    source=REPO/'tests/lumix_fake_usb.c';library=output/('fake-usb.dll' if sys.platform=='win32' else 'fake-usb.dylib')
    cc=compiler or shutil.which('cl' if sys.platform=='win32' else 'cc')
    if not cc:raise ValueError('A native C compiler is required')
    if sys.platform=='win32':
        command=[cc,'/nologo','/O2','/LD','/MT',str(source),'/Fo'+str(output/'fake-usb.obj'),'/link','/OUT:'+str(library)]
    else:
        command=[cc,'-std=c11','-Wall','-Wextra','-Werror','-dynamiclib','-O2',str(source),'-o',str(library)]
    built=subprocess.run(command,capture_output=True,text=True)
    (output/'compiler.stdout').write_text(built.stdout);(output/'compiler.stderr').write_text(built.stderr)
    if built.returncode:raise ValueError('Native USB test library compilation failed')
    native=C.CDLL(str(library))
    native.lumix_fake_case.argtypes=[C.c_int];native.lumix_fake_case.restype=None
    native.lumix_fake_count.argtypes=[C.c_int];native.lumix_fake_count.restype=C.c_uint
    native.lumix_fake_layout.argtypes=[C.c_int];native.lumix_fake_layout.restype=C.c_size_t
    layout=[native.lumix_fake_layout(i) for i in range(8)]
    if layout!=[18,32,40,16,40,16,16,16]:raise ValueError('Native compiler descriptor ABI differs')
    names=('init','list','descriptor','config','free_config','open','claim','control','bulk','release','close','free_list','exit','invalid')
    cases=[]
    for mode,label in ((0,'read_and_fixed_policy_write'),(1,'two_matching_devices'),(2,'other_camera_model'),
                       (3,'wrong_endpoint'),(4,'interface_busy'),(5,'short_payload'),(6,'bulk_timeout'),
                       (7,'wrong_reply_kind'),(8,'disconnect_during_control'),(9,'no_camera'),
                       (10,'inactive_configuration'),(11,'missing_driver')):
        native.lumix_fake_case(mode);refused=None
        transport=Transport(library)
        try:
            with transport:
                if transport.identity!=dict(model='DMC-GM5',serial='fixture-camera',usb_release=0x100):
                    raise ValueError('Native descriptor/string identity differs')
                service=Service(transport,{0x40000400})
                data=service.read(0x40000400)
                if data!=bytes(i&255 for i in range(1024)):raise ValueError('Native reply copy differs')
                if mode==0:service.set_policy(0)
        except USBError as error:refused=str(error)
        if bool(refused)!=(mode!=0):raise ValueError('Native USB fault was not correctly handled: '+label)
        counts={name:native.lumix_fake_count(i) for i,name in enumerate(names)}
        if (counts['invalid'] or counts['init']!=1 or counts['list']!=1
                or counts['free_list']!=1 or counts['exit']!=1):raise ValueError('Native ABI/cleanup mismatch: '+label)
        if counts['open']!=counts['close']:raise ValueError('Native USB handle leaked: '+label)
        if counts['config']!=counts['free_config']:raise ValueError('Native configuration descriptor leaked: '+label)
        expected_bulk={0:6,5:3,6:1,7:2,8:0}.get(mode,0)
        expected_control={0:6,5:3,6:1,7:2,8:1}.get(mode,0)
        expected_release=1 if mode in (0,5,6,7,8) else 0
        if (counts['bulk']!=expected_bulk or counts['control']!=expected_control
                or counts['release']!=expected_release):raise ValueError('Unexpected transfer/retry/release: '+label)
        if transport.claimed or transport.handle or transport.context or transport.devices:
            raise ValueError('Transport retained closed native objects: '+label)
        transport.close()
        if counts!={name:native.lumix_fake_count(i) for i,name in enumerate(names)}:
            raise ValueError('Repeated close touched an already closed object')
        cases.append(dict(name=label,mode=mode,refused=refused,calls=counts))
    result=dict(time_utc=datetime.now(timezone.utc).isoformat(),passed=True,platform=sys.platform,
        architecture=platform.machine(),python=sys.version,native_layout=layout,cases=cases,
        source_sha256=sha(source.read_bytes()),transport_sha256=sha((REPO/'apps/lumix_updater/usb.py').read_bytes()),
        native_library_sha256=sha(library.read_bytes()),native_library_is_explicit_test_peer=True,
        real_libusb_driver_or_camera_workflow_verified=False,camera_contacted=False)
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,platform=sys.platform,cases=len(cases),camera_contacted=False)))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cc');args=p.parse_args();proof(args.out,args.cc)
