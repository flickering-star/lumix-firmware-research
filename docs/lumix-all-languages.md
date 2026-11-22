# Complete GM1 and GM5 language catalogs

The 0.2.6 updater source exposes all 26 native language choices on both reviewed
models. The standalone **Language unlock + update access** option and the
experimental LUT option both apply this change. The released 0.2.5 applications
retain their previous regional language restrictions. Camera testing of the
new packages is pending.

The previous GM1 Japanese unlock selected an existing 16-language regional
list. It excluded Korean even though the firmware contains Korean text and
supports language ID13 on its Korean-region path. The GM5 patch selected a
23-language list only for the Japanese region. Other regional lists could
still expose different subsets, including Middle East languages.

Both firmwares already have a complete catalog in their original UI-data
initializer. It contains 26 enabled rows and a sentinel. The original RAM
language buffer has the same 216-byte size. The patch redirects the existing
regional list operands in menu construction and saved-language validation to
that catalog. It preserves the native language IDs and ordering.

| Model | Complete catalog in ROM | Existing language buffer | Regional list operands |
| --- | --- | --- | --- |
| GM1 1.1/internal0110 |405b7ba4|708f5878|16 validation and16 menu operands|
| GM5 internal0110/0111 |4065889c|70a0f150|20 validation and20 menu operands|

The implementation reads the native catalog and regional lists from the input
program. It verifies their row layout, sentinel, ID union and matching menu
and validation inventories. There is no authored list of selected language
IDs. It also restores the original Japanese dispatch entries, which the older
patch redirected, and keeps the existing Language item visible.

The app applies this operation after verifying the bundled component delta
and any optional recording-duration change. Stock Program Restore uses the
original component path. The generated update report includes the selected
catalog and its edits.

## Source and reproduction

The shared implementation is in
[languages.py](../apps/lumix_updater/languages.py). Its integration in
[firmware.py](../apps/lumix_updater/firmware.py) covers the standalone unlock
and LUT options. The portable controls in
[test_lumix_languages.py](../tests/test_lumix_languages.py) deliberately use
different catalog IDs to check that the firmware data drives the patch.

For a decrypted program that you obtained yourself, the research command can
inspect or apply the language operation without contacting a camera.

```sh
python3 tools/lumix_language_catalog.py --model DMC-GM1 --input work/program.bin
python3 tools/lumix_language_catalog.py --model DMC-GM1 --input work/program.bin --out work/gm1-all-languages
```

Use DMC-GM5 for the reviewed GM5 program. This command produces a program
component and edit report. The desktop updater handles the separate update
policy, official input checks, encryption and SD package construction.
Firmware components belong in an ignored local directory.

For another camera model, identify its native language menu and normalizer,
their region-specific list operands, the complete UI initializer and the
destination buffer size. Confirm that the same language rows are supported
by its GUI and font resources, and execute its native menu and validation
paths before preparing a device update. GM1S has a different layout and is
unsupported.

## Validation and camera test

The generated standalone and LUT packages pass 3,060 native language cases
across their regional dispatch inputs, supported language IDs, invalid values
and operation modes. The checks run the original menu copy, saved-language
validator and visibility helper from independently decoded package bytes.
They check the complete menu, UI cache, caller state, region/mode fields,
existing buffer bounds and adjacent bytes.

All 15 supported app workflow variants pass complete independent package
decoding, including duration and restore choices. Thirty-nine host tests pass.
The summarized evidence is in
[lumix-all-languages.json](../evidence/lumix-all-languages.json).

On a test body, confirm that Korean and Arabic or Persian appear in the same
Language list. Select each through the menu and check persistence after a
normal off/on. Test the standalone and LUT options on the appropriate model.
Physical selection, font rendering and reboot behavior remain pending for
these candidates.
