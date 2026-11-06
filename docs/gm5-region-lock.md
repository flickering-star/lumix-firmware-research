# GM5 Japanese language restriction and emulator work

The three-byte language patch is installed. The owner reports installing it in
normal mode, selecting English through the camera menu and retaining English
after a normal off/on. The [short physical proof](../evidence/gm5-region-physical-proof.json)
verifies all three patch windows, English settings/UI and ROM/RAM policy zero.
Its development base is the previously verified policy-zero main,
SHA-256 `c918553771018e171605ecb1f177a4d64bc94b221fe5304b8ff419f4509d208d`.
Aspect-ratio changes remain deferred. No host policy or language writes were
used during this installation's preparation or post-update measurements.

The [native lock analysis](../evidence/gm5-region-language-lock-v2.json) and
[current record](../evidence/gm5-region-research-current.json) distinguish the
candidate from intermediate artifacts. The earlier
[language record](../evidence/gm5-language-change.json) establishes that English
worked in RAM but reverted after restart. The new native tests explain that
behavior and identify a separate menu-visibility restriction.

## Native language paths

The retained settings bank has factory/operation-mode word one at offset
`0x32e` and region `0x0100` at offset `0x330`. The saved language byte is at
offset `0x1b9`, mapped to `0x7bfb01b9`; the active UI cache is `0x701af239`.
English is language ID one and Japanese ID zero.

Startup `0x40211a38` calls language normalization at `0x40211ec6`, followed by
the language-list constructor at `0x400a8427`. Both dispatch on the region.
For region `0x100`, the stock dispatch selects the Japanese-only list at
`0x40379b10`. Native membership helper `0x40126fce` requires an entry with
availability state four. A saved English value fails that stock list; the
normalizer writes Japanese to both settings and UI cache.

Normal selection stores at `0x400ea1ea..0x400ea204` write the chosen language
to both locations and set the normal language-selection flag at `0x7bfb0312`.
The native settings loader at `0x401e3051` chooses an A/B bank, and native save
at `0x401e3382` uses actual NOR erase/program helpers. The emulator now runs
those routines against disposable virtual NOR, then starts with fresh RAM and
reloads the saved settings.

That round trip reproduces the failure: the stock native save writes English
into a persistent settings bank, but the next stock normalization changes it
back to Japanese. With the dispatch candidate, the saved English value survives
reload. Stock and candidate save outputs have identical settings-bank contents;
their different startup interpretation explains the result.

## Third gate: hidden Language menu item

Expanding the language list is insufficient to expose the normal menu item.
Native function `0x400aa012` specifically checks for region `0x100` and sets
setup item **143** to state zero (hidden). The initial table at `0x70a0e898`
contains that item in state four. The setup dispatcher bounds IDs 131 through
181 and uses table `0x4039096c`; entry 143 points to `0x4010a126`, which calls
the actual language-menu entry at `0x400eb4d3`.

The current candidate changes three bytes in the installed main:

| ROM address | Before → after | Effect |
| --- | --- | --- |
| `0x40491900` | `c5` → `ab` | Japanese saved-language validation uses existing multilingual list/default |
| `0x40379bf0` | `8f` → `65` | Japanese language-list construction uses that same existing list |
| `0x400aa01d` | `c9` → `ca` | Skip the Japanese-only setup-item hiding operation |

The first two redirects select an existing list of 23 choices including English
and Japanese. They do not expose all 26 language-resource IDs. The third change
turns the branch to the function's return into an unconditional branch; regions
other than Japanese already took that return. Region identity, video rules and
calibration data are not patched. The installed policy-zero initializer and
version bytes remain unchanged.

The candidate main SHA-256 is
`5364cde77a78a40fce270bf1c24642a9fbd2e6d7d3501bb38d8b806548a48d67`.
The initial two-byte package in `work/gm5-region-package-1` is an intermediate
research artifact: it lacks the visibility fix and must not be used as the
complete region patch. The final three-byte package was copied to the identified
GM5 SD card on 2026-11-06, read back byte-for-byte and safely ejected; see the
[copy receipt](../evidence/gm5-region-sd.json). The owner then installed it in
normal mode; the bounded physical verification below confirms its patch bytes.

## Emulator coverage and ongoing checks

All **1,756 native region/language controls pass**. The matrix covers stock and
candidate behavior for every region input `0x0000..0x0121` plus `0xffff`, with
eight language inputs for Japanese and three for every other region. It checks
normalized language, complete menu lists, Language-item visibility and every
settings byte. All other tested regions behave identically with and without
the candidate. The native stock and candidate settings save/reload tests pass.

The exact encoded three-byte package passes six native controls: allowed
decoding, default-policy rejection, complete virtual programming, injected
program error, power cut and settings/language startup from the programmed
image. The full successful 32 MiB virtual output differs from the current
fixture only at the three intended main-program bytes. All non-main bytes are
unchanged by installation.

An additional sequence begins with that exact decoded/programmed image. It
loads settings through the native A/B bank selection, opens the native language
list, navigates through all 23 choices and wraps back to English, then executes
normal selection stores, native NOR-backed save and fresh startup/reload.
English remains in the settings shadow and UI cache. The pending-language word
is not written by the fixture in this sequence: native navigation selects it.

The emulator has also gained an optional RAM change observer. It logs changed
bytes, the instruction that produced the change and the next PC. It watches
ordinary mapped RAM only, does not poll NOR or MMIO, and reports changes rather
than claiming to see stores that write the same value. Five focused tests cover
fast/single-step agreement, unchanged execution, initialization/same-value
stores, final changes at an instruction budget, invalid/device intervals and
frontend metadata/validation.
The separately named `gm5-mn103-sim-language_watch` backend preserves the prior
executable used by earlier evidence and the completed region matrix.

Observed native stock stores are `0x40211fe0` (saved English → Japanese),
`0x40211fe6` (Japanese into the UI cache) and `0x40127221` (Language-item state
four → zero). The three-byte candidate preserves saved English and menu
visibility while populating the UI cache with English. Observed/unobserved
runs have identical CPU state and outputs; the new backend's unobserved run
also matches the retained original backend, including its instruction trace.

These are bounded native startup/menu/selection/save subsequences. The full
display, scheduler, sensor and board startup are not emulated. Physical menu
selection and persistence now have the owner's camera observations and the
post-cycle read-only settings/UI measurements described below.

## Exact package and physical expectations

| Property | Candidate |
| --- | --- |
| Local file | `work/gm5-region-package-2/GM5__V11.bin` |
| File size | 8,390,144 bytes |
| Encoded file SHA-256 | `4954b517462b8ee5f900945496b882ddfa45f97b540f0d1dad6dcdf706ea50c7` |
| Main plaintext SHA-256 | `5364cde77a78a40fce270bf1c24642a9fbd2e6d7d3501bb38d8b806548a48d67` |
| Main interval | NOR offset zero, 8 MiB, 64 sectors |
| Advertising halfwords | `0x0114 / 0x0114` |
| Installed version bytes | Unchanged |
| Existing persistent unsigned policy | Retained at zero |
| EEPROM/calibration/resource payloads | Excluded |

The package is based on the exact main already read from this camera, not a
different regional download. Both the native decoder and the retained original
host decoder recover its exact expected plaintext. The existing global language
resources are reused; there is no replacement resource payload.

Japanese remains valid as the initial saved language. The Language item permits
ordinary English selection; the package does not force English as the saved value.

## Physical installation and short verification

The owner reported: “Flashed in normal mode(not service)” and “Selected English;
it stayed English after off/on”. Before installation, packet-verified service
reads found ROM policy `0x406b1bdc` and RAM policy `0x70a68490` both already zero.
Neither a temporary policy write nor a host language write was needed.

After the reported manual off/on, read-only service checks verified:

- The three 1 KiB ROM windows containing `0x400aa01d`, `0x40379bf0` and
  `0x40491900` match the exact candidate, including the surrounding bytes.
  The patched values are respectively `ca`, `65` and `ab`.
- ROM and RAM policy remain zero. Saved-language shadow `0x7bfb01b9` and active
  UI cache `0x701af239` both read English ID one.
- The live settings contain mode word two and Japanese region word `0x0100`.
  The live normal-mode list contains 26 enabled entries. The earlier offline
  mode-one fixture exercises the 23-choice Japanese dispatch path.

The full 8 MiB readback was stopped at the owner's request, after 708,608 bytes.
It was not resumed. The short proof confirms the patch locations and language/
policy state; it does not claim an entire installed-main or whole-NOR comparison.
The full candidate hash in the package table is the expected image hash.

The [physical observation](../evidence/gm5-region-physical-observation.json) and
[replayable proof](../evidence/gm5-region-physical-proof.json) retain the owner
statements, capture paths and checks. The collector rejects a checksum-valid
packet/file pair containing the original Japanese-only dispatch byte.

```sh
python3 tools/gm5_region_proof.py --observation evidence/gm5-region-physical-observation.json --out work/gm5-region-proof-recheck.json
```

The prior policy-zero package remains available locally as the pre-region
baseline. Reverting to it would need its own validated update procedure; an
external recovery writer remains untested.

## Reproduce offline

Use fresh output directories and retain the private verified images:

```sh
python3 tools/gm5_region_emulator.py --exhaustive --out work/region-matrix-new
python3 tools/gm5_region_persistence.py --persistence --out work/region-stock-save-new
python3 tools/gm5_region_persistence.py --persistence --patched --out work/region-unlocked-save-new
python3 tools/gm5_region_package.py build --out work/region-package-new
python3 tools/gm5_region_package.py test --build-dir work/region-package-new --out work/region-package-native-new
python3 tools/gm5_region_persistence.py --persistence --patched --navigate --source-nor work/region-package-native-new/region_native_install/virtual-nor.bin --out work/region-native-navigation-new
python3 tools/mn103_simulator/build.py --variant language_watch
python3 tools/gm5_region_observe.py --out work/region-store-trace-new
python3 -m unittest discover -s tests -v
```

RAM observations use scenario `memory_observations` entries with `label`,
`address` and `size`, or `MEMWATCH ADDRESS SIZE LABEL` in the backend protocol.
Each interval is 1–64 bytes inside modeled ordinary RAM, with at most 64
observations. The observer does not identify same-value stores or asynchronous
hardware writes and does not add a hardware memory-protection model.
