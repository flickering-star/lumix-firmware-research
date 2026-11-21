"""Desktop entry point and a USB-free bundle self-test."""
import argparse
import json
from pathlib import Path

from . import __version__


def main():
    parser=argparse.ArgumentParser(description='Guided Lumix SD firmware preparation')
    parser.add_argument('--assets',help='Development patch-catalog directory')
    parser.add_argument('--self-test',action='store_true',help='Check bundled codec/catalog without camera access')
    parser.add_argument('--self-test-report',type=Path,help='Write the USB-free bundle check as JSON')
    parser.add_argument('--gui-smoke-report',type=Path,help='Check the desktop UI without camera access')
    args=parser.parse_args()
    if args.self_test or args.self_test_report:
        from .codec import Codec
        from .firmware import catalog,catalog_assets
        from .download import sha
        from .usb import Transport
        import certifi
        import ssl
        codec=Codec();root,manifest=catalog(args.assets)
        key=bytes(16);iv=bytes(range(16));plain=bytes(range(32))
        if codec.transform(codec.transform(plain,key,iv,encrypt=True),key,iv)!=plain:
            raise ValueError('Firmware codec round trip failed')
        # Loading and checking libusb symbols opens no device/context.
        usb=Transport()
        for symbol in ('libusb_init','libusb_get_device_list','libusb_control_transfer','libusb_bulk_transfer'):
            getattr(usb.lib,symbol)
        files,profiles=catalog_assets(root)
        patches=sum(name.endswith('.lxdp') for name in files)
        tls=ssl.create_default_context(cafile=certifi.where())
        if tls.verify_mode!=ssl.CERT_REQUIRED or not tls.check_hostname:
            raise ValueError('The bundled TLS verification is not enabled')
        report=dict(version=__version__,codec_selftest=True,usb_library_loaded=True,
            bundled_tls_roots_loaded=True,
            supported_models=list(profiles),
            supported_camera_profiles=[p for values in profiles.values() for p in values],
            patch_files_verified=patches,choices=list(manifest['choices']),camera_contacted=False)
        if args.self_test_report:
            with args.self_test_report.open('x',encoding='utf-8') as stream:
                stream.write(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
    elif args.gui_smoke_report:
        from .gui import smoke_report
        smoke_report(args.gui_smoke_report,args.assets)
    else:
        from .gui import main as gui
        gui(args.assets)


if __name__=='__main__':main()
