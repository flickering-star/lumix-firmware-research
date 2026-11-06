#!/bin/sh
# Bounded GM5 service validation with exact registry/settings model checks.
set -eu
umask 077
probe_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
case "${1:-settings}" in
    inspect|access|settings|flash|block|window|initializer|startup-data|security-flag|updater-window|runtime-control|update-profile|usb-handler|usb-state|language-head|update-settings|update-ui-state|update-entry) probe_mode="${1:-settings}" ;;
    *) echo 'usage: run_gm5_usb_probe.sh [inspect|access|settings|flash|block|window|initializer]' >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then echo 'Only one mode argument is accepted.' >&2; exit 2; fi
probe_run=$(mktemp -d "$probe_root/captures/gm5-usb-$probe_mode-XXXXXXXX")
clang -std=c11 -Wall -Wextra -Werror -Wno-deprecated-declarations -DPROBE_GM5 \
    "$probe_root/tools/gm1_usb_probe_macos.c" -framework IOKit -framework CoreFoundation \
    -o "$probe_run/gm5-usb-probe"
"$probe_run/gm5-usb-probe" selftest
cp "$probe_root/tools/gm1_usb_probe_macos.c" "$probe_run/probe-source.c"
echo 'PROBE_GM5: model DMC-GM5; main 8 MiB; bounded modes only' > "$probe_run/build-target.txt"
shasum -a 256 "$probe_run/probe-source.c" "$probe_run/gm5-usb-probe" "$probe_run/build-target.txt" > "$probe_run/sha256.txt"
"$probe_run/gm5-usb-probe" "$probe_mode" "$probe_run/result"
