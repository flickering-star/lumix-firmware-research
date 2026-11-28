# Experimental GM1 real-time LUT patch

**All original project code was written by a chatbot. Flashing Panasonic
cameras is risky because independent recovery options are unproven. A bad
update can leave the camera unusable. Stock restore requires a working
ordinary updater and is not independent recovery.**

The reviewed DMC-GM1 firmware 1.1/internal 0110 port adds ten saved LUT cells,
Setup → LUT Library, native Photo Style/Quick Menu selection and row touch.
Version0.2.14 restores Opacity control using the209-byte blend cache by
[ShawnMayer](https://github.com/ShawnMayer/gm1-lut-opacity-cache).
The owner reports responsive controls with slight overhead versus the fixed-
strength patch. Brief colored vertical lines after Import/No LUT remain unresolved.
Complete recording-format, long-session and all-body coverage is not established.

Earlier0.2.4 Opacity recalculated blends on every frame and had severe reported
menu/control delays. Versions0.2.5–0.2.13 removed GM1 Opacity. This release restores
the0.2.4 controls with ShawnMayer's per-job cache: cell, percentage, generation and
two source sums identify an unchanged2188-byte blend in existing scratch memory.
A hit reuses that output; a miss executes the original blender. The33-byte hook
at407f434a and176-byte routine at40740000 add no allocation or startup hook.
See [credits and the upstream usage notice](../CREDITS.md) and the preserved
[add-on sources](../research/gm1-luts/opacity-cache).

The integrated pre-language program SHA256 is
`a2543e4171aa1afc22e375d8fdce13a45d0c29f3830cee5b6be763f7e106a5d9`;
the app's complete26-language program is
`66d9bf3d7d29b985335d390f48ab015f83be3594848d144ba6950075df834427`.
Serialized native original/cache controls preserve complete output tables,
registers and job retirement. These controls are not physical timing or complete
recording-transition proofs. The GM5 cache experiment is excluded after the
owner reported recording/menu failure; the released GM5 patch is unchanged.

Use a FAT32 card and short ASCII 8.3 filenames in its root. The importer accepts
compatible VLT/CUBE files and resamples them to a 9×9×9 hardware table with 6-bit
values. The exFAT importer is withdrawn. There is no separate EIR style or
65:24 feature in this package. The native image processor consumes the table;
this is not a software RGB pixel filter.

Saved LUTs and their Opacity settings restore from internal banks at startup. Existing cells need no migration or clearing for this cache update.
No LUT files are scanned from SD at boot or on card insertion. The GM1 programming prefix
ends at 0x880000, before the two saved-bank sectors. Updates made by the app
preserve those sectors. Settings, calibration and ARM components are excluded.

## Memory and queue corrections

The GM1 port reuses GM5 conversion, storage and native list behavior with explicit
GM1 addresses and calling conventions. GM5 retains its existing opacity control;
GM1 uses the new blend cache. Retained tables, controller and frame
copies use an actual 128 KiB child of native pool10, whose 13000000..13200000
arena is separate from native movie pool1 at 13200000..18600000. Original
allocator, SD worker, reset and video-buffer sizing instructions are unchanged.
Transient import workspaces still use the original image-pool APIs.

Two authored wrappers previously kept metadata below the live stack pointer.
An emulated interrupt could overwrite a request token or controller pointer,
leaving stale processing jobs or a busy bank after native Post. The current
dispatcher and producer keep all bookkeeping allocated until the native call
returns. Native interrupted preview/capture checks now unlock both banks and
preserve the original output registers. These bounded native checks and the
owner's camera report are separate evidence; they do not model all DMA or
physical timing.

## Reproduction and installation

The desktop source in `apps/lumix_updater` supports the reviewed
GM1 and GM5 profiles. Read`apps/README.md` for dependencies and launching from
source. Connect the awake camera through service USB and choose Experimental
LUTs. The app validates the exact model, revision, code pages, key and policy;
it downloads the hash-pinned official 1.1 firmware or accepts the matching
local BIN/ZIP. Its deltas reconstruct all three reviewed program components.
No firmware image or encryption key is bundled in the repository.

For independent component reproduction, decode your own official GM1 update
using the model's research instructions, then run:

```sh
python3 tools/lumix_lut_components.py --recipe recipes/gm1-v11-luts.json --program /path/to/program.bin --guires /path/to/guires.bin --program2 /path/to/program2.bin --out work/gm1-lut-components
```

This refuses unknown input hashes, checks every bounded replacement and every
complete output hash, and writes components only after all checks succeed.
It does not make an SD update or contact the camera. The desktop app handles
container encoding and preparation. The recipe is authoritative for the exact
bytes; the assembly files in `research/gm1-luts` are selected review sources.

Copy the prepared `GM1__V11.bin ` to a camera-formatted card. Confirm Standard,
switch the camera off, insert the card, and use a fully charged battery. A stock
camera needs the app's checked temporary service-USB policy change. Unplug USB
without switching off, press Playback and confirm the update on the camera.
Follow its restart instruction and keep power stable throughout programming.

Before installing Stock Program Restore, reset camera settings while the
patched firmware is still running. Keep the app's matching stock-restore file.
The stock restore returns the original language lock and signed-update policy
and clears saved LUTs.

The [v0.2.14 desktop apps and checksums](https://github.com/flickering-star/lumix-firmware-research/releases/tag/updater-v0.2.14)
support the guarded GM1/GM5 builds. GM1S is not supported.
This remains an unmaintained reference archive; contributions, pull requests
and support requests are not accepted.
