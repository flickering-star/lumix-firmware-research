#!/bin/sh
set -eu
umask 077
probe_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$#" -ne 1 ]; then echo 'usage: run_gm5_language.sh {inspect|english}' >&2; exit 2; fi
case "$1" in inspect|english) ;; *) exit 2 ;; esac
probe_run=$(mktemp -d "$probe_root/captures/gm5-language-$1-XXXXXXXX")
clang -std=c11 -Wall -Wextra -Werror -Wno-deprecated-declarations \
    "$probe_root/tools/gm5_language_macos.c" -framework IOKit -framework CoreFoundation \
    -o "$probe_run/gm5-language"
"$probe_run/gm5-language" selftest
cp "$probe_root/tools/gm5_language_macos.c" "$probe_run/language-source.c"
cp "$probe_root/tools/gm1_usb_probe_macos.c" "$probe_run/shared-read-source.c"
shasum -a 256 "$probe_run/language-source.c" "$probe_run/shared-read-source.c" "$probe_run/gm5-language" > "$probe_run/sha256.txt"
"$probe_run/gm5-language" "$1" "$probe_run/result"
