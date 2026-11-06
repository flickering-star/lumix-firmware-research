# A positive control for the UPD v2 component fields

The official TZ30 1.2 update supplies a useful new control: **all eight entries
with flags `2` have a 32-byte field equal to SHA-256 of their exact stored
component bytes**. This includes an empty component, zero-filled components,
packed resources, a Windows executable and readable camera-side map code.
All eight also have a zero sixteen-byte field.

This establishes the field's behavior for those TZ30 entries. It supports a
plaintext-digest interpretation for the structurally matching GM5 fields, while
GM5's encoded components still need a genuine decode or memory read to verify
that interpretation. No GM5 plaintext or key was recovered.

## Official acquisition and integrity

The source is Panasonic's [TZ30/31/ZS20 download page](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/TZ30_31_ZS20/index2.html)
and its linked [TZ30 1.2 ZIP](https://av.jpn.support.panasonic.com/support/share/eww/en/dsc/tz30_tz31_zs20/TZ30_V12.zip).

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| `TZ30_V12.zip` | 24,874,020 | `352b3ab6607b72a1985feb36ae9ef9751b7717d04f5f5a8f2740019aa83de37f` |
| `TZ30_V12.bin` | 37,639,168 | `fbc51b27e38008b9aef0146b55d1683035c86c076d1890ed44af232c70309cb2` |

The ZIP has one member and passes its CRC check. In the BIN, the declared body
length, repeated header and outer body CRC32 `0xe8f5d1d7` all agree with the
actual bytes. Local inputs remain under `work/transition-tz30/`.
The [reproducible control report](../evidence/tz30-v2-controls.json) records the
directory, hashes, packed-file bounds and selected native bytes.

## Clear components provide actual digest checks

The directory uses the same `0x5c`-byte record shape and header locations
observed in GM5. These complete stored components match their directory SHA-256:

| TZ30 component | Bytes | Observed content |
| --- | ---: | --- |
| `storage` | 0 | Empty component; field equals SHA-256 of empty bytes |
| `history` | 131,072 | Zero-filled |
| `packfile` | 5,767,168 | `PACK` archive of demonstration resources |
| `web_uploade` | 6,946,816 | `PACK` archive containing `LUMIXUP.EXE` and seven PDF guides |
| `avchd_info` | 16,384 | Zero-filled |
| `map` | 4,849,664 | `PACK` archive of map data |
| `map_prog` | 524,288 | Readable map-library code and data |
| `gps_assist` | 2,621,440 | `PACK` archive |

The digest covers each entire component, including padding after a packed
archive's used data. It is not merely the digest of the first embedded file.
The other fifteen TZ30 entries have flags `3`; none of their stored-byte
SHA-256 values matches its 32-byte field. Their main program remains encoded.

The flags correlate with the observed clear/encoded distinction in this sample.
The actual updater's flag handling and acceptance rules have not been traced.
Changing a flag in an update is not an established decoding or installation
method. The outer fields at `0x2c` and `0x34` both contain `3`, as in GM5;
these observations do not by themselves name the cipher behind selector `3`.

### Readable code is present, with a limited role

`map_prog` contains a `LOAD` header and map-library diagnostics. A file-zero
mapping of `0x79600000` is supported by three instructions loading addresses of
their matching initializer strings. Forty instructions have continuous native
byte annotations matching the unchanged extracted component.

This is actual readable auxiliary camera code from a format-`0x200` package.
It is not a recovered main updater, a GM5 memory map or a GM5 code sample.
The inspected module has no literal standard AES S-box or known GH2 key.

### The bundled Windows program is an uploader

The clear `web_uploade` archive contains a 3,297,664-byte `LUMIXUP.EXE`, SHA-256
`7eaf2842ff5bf01e4c95fd77cc7637d88ba0b929c155aace0d7ab3373a5be223`.
Static PE review found one direct absolute imported call to `DeviceIoControl`.
At `0x433a3f`, it passes `0x70024` with null input/output buffers: the Windows
[disk-writability query](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-ioctl_disk_is_writable).
Microsoft's header definitions reproduce that value. This inspected call does
not send a Panasonic maintenance command.

The [uploader evidence](../evidence/tz30-uploader-triage.json) retains import
references and 29 instructions checked against the PE's bytes. The review is
limited to those imports, literal searches and the selected call; dynamically
resolved functions and the whole executable were not exhaustively analyzed.
No downloaded Windows program was executed or installed.

## What this changes for GM5

The 32-byte GM5 fields can now be investigated against a concrete same-format
digest control, rather than assigning meaning from their lengths alone. A
future camera-memory read matching a component's expected digest would provide
a strong validation of both the bytes and their placement.

One additional hypothesis was checked directly: use each GM5 record's 32-byte
field as an AES-256-CBC key and its sixteen-byte field as IV. **None of the eight
candidate outputs has SHA-256 equal to the corresponding 32-byte field.**
This rejects that precise combination under the supported plaintext-digest
interpretation. It does not identify the cipher or exhaust other mechanisms.
No candidate plaintext was saved as a firmware image.

## Bounded survey of nearby releases

Thirteen official ZIPs were sampled using verified HTTP ranges of exactly
65,536 bytes each: GH3, G5, G6, GF6, GX7, GM1, FT5, LF1, SZ5, SZ7, TZ27, TZ30
and TZ40. Every available header has format `0x200` and value `3` at `0x2c` and
`0x34`; every listed main `program` entry has flags `3`.

The [survey receipt](../evidence/upd-v2-transition-prefixes.json) preserves URLs,
range hashes, ZIP-local metadata, decompressed prefixes and directory fields.
These are **partial inputs**, without complete ZIP/body integrity verification.
For TZ30, the range and decompressed prefix were subsequently checked against
the complete CRC-verified download. No older plaintext main updater was found
in this bounded survey. A complete follow-up of the official SZ5 image verified
four more clear-component SHA-256 matches. Its ten-MiB `wifi_data` component is
entirely zero-filled; the separate `wifi_prog` remains encoded. The
[SZ5 receipt](../evidence/sz5-wifi-data-control.json) records both observations.
The [related Leica prefix survey](../evidence/leica-upd-prefix-survey.json) also
found format `0x200` and flagged encoded main programs in D-Lux 7/8 samples,
with the stated partial-input and mirror-provenance limits.

With the recorded intact BINs and extracted `map_prog` control, reproduce the
checks using a fresh output path:

```sh
python3 tools/tz30_control_verify.py work/transition-tz30/TZ30_V12.bin --out work/tz30-v2-controls-new.json
```
