#!/bin/sh
# Fixed-address, reversible RAM 1 -> 0 -> 1 test; no flash/settings write.
set -eu
umask 077
probe_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$#" -ne 1 ]; then
    echo 'usage: run_gm5_ram_control.sh {toggle-test|enable-unsigned|restore-signed}' >&2
    exit 2
fi
case "$1" in toggle-test|enable-unsigned|restore-signed) ;; *) exit 2 ;; esac
probe_run=$(mktemp -d "$probe_root/captures/gm5-ram-$1-XXXXXXXX")
clang -std=c11 -Wall -Wextra -Werror -Wno-deprecated-declarations \
    "$probe_root/tools/gm5_ram_control_macos.c" -framework IOKit -framework CoreFoundation \
    -o "$probe_run/gm5-ram-control"
"$probe_run/gm5-ram-control" selftest
cp "$probe_root/tools/gm5_ram_control_macos.c" "$probe_run/ram-control-source.c"
cp "$probe_root/tools/gm1_usb_probe_macos.c" "$probe_run/shared-read-source.c"
shasum -a 256 "$probe_run/ram-control-source.c" "$probe_run/shared-read-source.c" "$probe_run/gm5-ram-control" > "$probe_run/sha256.txt"
"$probe_run/gm5-ram-control" "$1" "$probe_run/result"
