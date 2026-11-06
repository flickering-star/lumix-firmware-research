# GM5: reproduce the tested language/policy patch

This procedure describes the exact Japanese DMC-GM5 1.1 code build used in the
research. It does not support every regional/version variant. The offline
recipes refuse an unknown full input hash, incorrect original bytes, overlapping
edits or an unexpected full output hash. They perform no camera operation.

## Inputs and exact recipe

Use your own verified **8 MiB main program**, excluding the rest of NOR. The
two accepted baselines are:

| Baseline | Main SHA-256 |
| --- | --- |
| Original installed Japanese main | `5316a6ff14152126a88ce02125e85d713e710c8dd1159dee2ab890e4ff345966` |
| Same main with persistent policy zero | `c918553771018e171605ecb1f177a4d64bc94b221fe5304b8ff419f4509d208d` |

The [language recipe](../recipes/gm5-v11-jp-language.json) produces the same
reviewed main from either baseline. Its changes are:

| Main offset / mapped address | Change | Purpose |
| --- | --- | --- |
| `0x6b1bdc` / `0x406b1bdc` | `01 → 00`, only on the original baseline | Retain unsigned-input policy zero at startup |
| `0x0aa01d` / `0x400aa01d` | `c9 → ca` | Preserve the Language setup-menu item |
| `0x379bf0` / `0x40379bf0` | `8f → 65` | Redirect Japanese language-list construction |
| `0x491900` / `0x40491900` | `c5 → ab` | Redirect Japanese saved-language normalization |

The language change reuses existing resources and multilingual paths. It does
not force English, rewrite region identity or change video modes. Actual
installed-version bytes remain unchanged. Detailed native evidence is in
[language-lock findings](gm5-region-lock.md).

```sh
python3 tools/lumix_patch.py --recipe recipes/gm5-v11-jp-language.json --input captures/YOUR-MAIN-CAPTURE/result/program-main.bin --out work/gm5-language-main
```

The exact output SHA-256 must be
`5364cde77a78a40fce270bf1c24642a9fbd2e6d7d3501bb38d8b806548a48d67`.
The separate [policy-only recipe](../recipes/gm5-v11-jp-policy-zero.json)
reproduces the previously tested one-byte baseline if that intermediate control
is wanted. No firmware bytes beyond the small patch preimages/replacements are
distributed in either recipe.

## Recreate the exact update file locally

Obtain official `GM5__V11.bin` yourself, with SHA-256
`d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243`.
The public reproducer needs that template, your recipe output and the locally
compiled codec; it does not need the original researcher's captures, NOR backup,
historical output paths or card UUID.

```sh
mkdir -p work
cc -O2 -std=c11 -Wall -Wextra -Werror tools/panasonic_aes5.c -o work/panasonic-aes5
python3 tools/gm5_public_package.py --template firmware/official-gm5-v11/GM5__V11.bin --main work/gm5-language-main/program.patched.bin --codec work/panasonic-aes5 --out work/gm5-language-package
```

The resulting `GM5__V11.bin` is **8,390,144 bytes**, SHA-256
`4954b517462b8ee5f900945496b882ddfa45f97b540f0d1dad6dcdf706ea50c7`.
The reproducer requires this exact digest and a decode/encode round trip. Its
output was also compared byte-for-byte with the physically installed test file.

It contains only the 8 MiB main at NOR offset zero. Settings, calibration,
resource and secondary-program payloads are excluded. It has an explicit zero
unsigned marker and zero signature field. Correct CRC/component hashes do not
make it a signed update. Header advertisement `0x0114` triggers eligibility while
actual main version words stay `0x0111`; changing advertised version alone does
not bypass authentication.

## Physical procedure and bootstrap boundary

First obtain and packet-verify a backup of your own camera's mapped NOR and
establish its model, installed build and policy state. Preserve calibration and
settings from that body; another camera's backup is not a substitute. The
research used `gm5_flash_backup.py --component nor`; `--component program` reads
only the main. Recovery with an external programmer was not validated.

The unsigned package needs the updater's unsigned-input allowance. A camera
already running persistent policy zero needs no RAM manipulation. A stock
policy-one camera does not acquire that allowance merely because the new file
contains zero: its currently running updater decides whether to accept it.
The [guarded RAM control](../tools/gm5_ram_control_macos.c) and
[policy lifetime findings](gm5-flashing.md) document the tested bootstrap. Read
and validate the exact code/address/original-value guards before using it on
another body. All hardware wrappers here are GM5-specific, not other-model
write tools.

Place the locally verified file in the root of a GM5-formatted SD card, verify
the copied hash and eject it. Insert the card with the camera switched off,
then turn it on with a charged battery. Verify the running policy if needed,
disconnect USB without restarting and press Playback. Let an accepted update
finish without interrupting power. A higher-version prompt by itself is not
proof of installation. A preceding default-policy attempt showed brief progress
but sampled code remained unchanged.

The final research installation was performed in **normal mode**, per the owner.
After installing, select English through the normal Language menu and perform a
normal off/on. No host language write should precede that persistence check.

The final [physical proof](../evidence/gm5-region-physical-proof.json) verifies
three complete 1 KiB windows containing the edits, saved/UI language one and
ROM/RAM policy zero after the owner's manual off/on. The owner stopped a full
main readback, so no complete post-language main comparison is claimed. The
earlier policy-only installation did have a complete 8 MiB comparison.

`run_gm5_region_check.sh inspect` reads only those three fixed ROM windows.
`run_gm5_usb_probe.sh security-flag`, `runtime-control`, and
`run_gm5_language.sh inspect` are read-only checks. The original evidence
collector replays the retained private capture paths; another experiment should
record its own observation and paths rather than relabel the original proof.
