#!/bin/sh
set -eu
umask 077
if [ "$#" -ne 1 ] || [ "$1" != inspect ]; then
    echo 'usage: run_gm5_region_check.sh inspect' >&2
    exit 2
fi
probe_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
probe_run=$(mktemp -d "$probe_root/captures/gm5-region-check-XXXXXXXX")
cp "$probe_root/tools/gm5_region_check_macos.c" "$probe_run/region-source.c"
cp "$probe_root/tools/gm1_usb_probe_macos.c" "$probe_run/gm1_usb_probe_macos.c"
clang -std=c11 -Wall -Wextra -Werror -Wno-deprecated-declarations \
    "$probe_run/region-source.c" -framework IOKit -framework CoreFoundation \
    -o "$probe_run/gm5-region-check"
"$probe_run/gm5-region-check" selftest
shasum -a 256 "$probe_run/region-source.c" "$probe_run/gm1_usb_probe_macos.c" \
    "$probe_run/gm5-region-check" > "$probe_run/sha256.txt"
"$probe_run/gm5-region-check" inspect "$probe_run/result"
