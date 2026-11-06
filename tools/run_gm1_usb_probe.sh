#!/bin/sh
# Run from the owner's ordinary Terminal when this session cannot open USB.
# Default is the bounded settings-marker probe; flash must be selected explicitly.
set -eu
umask 077
probe_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ "${1:-}" = resume ]; then
    if [ "$#" -ne 2 ]; then echo 'usage: run_gm1_usb_probe.sh resume PREVIOUS_CAPTURE_DIRECTORY' >&2; exit 2; fi
    exec python3 "$probe_root/tools/gm1_program_resume.py" "$2"
fi
case "${1:-settings}" in
    inspect|access|settings|flash|block|window|program|initializer|secondary-window|secondary|secondary-data) probe_mode="${1:-settings}" ;;
    *) echo 'usage: run_gm1_usb_probe.sh [inspect|access|settings|flash|block|window|program|initializer|secondary-window|secondary|secondary-data]' >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then echo 'Only one mode argument is accepted.' >&2; exit 2; fi
probe_run=$(mktemp -d "$probe_root/captures/gm1-usb-$probe_mode-XXXXXXXX")
clang -std=c11 -Wall -Wextra -Werror -Wno-deprecated-declarations \
    "$probe_root/tools/gm1_usb_probe_macos.c" -framework IOKit -framework CoreFoundation \
    -o "$probe_run/gm1-usb-probe"
"$probe_run/gm1-usb-probe" selftest
cp "$probe_root/tools/gm1_usb_probe_macos.c" "$probe_run/probe-source.c"
shasum -a 256 "$probe_run/probe-source.c" "$probe_run/gm1-usb-probe" > "$probe_run/sha256.txt"
"$probe_run/gm1-usb-probe" "$probe_mode" "$probe_run/result"
