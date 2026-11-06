# GM1 service settings: what PRIVATE.zip establishes

The supplied backup is useful for mapping persistent settings and testing the
idea of a numeric diagnostic flag. **It has not identified a Wi-Fi debug console
or a flag that enables one.** A settings value needs either an observed effect
or a traced firmware consumer before it can be assigned that meaning.

The owner confirmed that the language was already edited. The original region,
installed firmware version and pre-edit file were not supplied. Findings here
describe this **GM1** sample; its coordinates are not established GM5 offsets.

## Verified archive and table format

`PRIVATE.zip` is 52,404 bytes, SHA-256
`11e597cce5687bb1de1c4b48434302d4b6a5a75259ccc9b6d5224dc09c004087`.
All ZIP member CRCs passed. The 24 members include two EEPROM exports at the
archive root and a card folder tree containing AVCHD/Lumix index files. The
folder name `PRIVATE` does not make those index files a firmware backup.

| Export | Text bytes | Header area | Data rows | 16-bit values | Represented bytes |
| --- | ---: | --- | ---: | ---: | ---: |
| `GM1U.TXT` | 44,859 | `10`, `UPDATE` | 512 | 8,192 | 16,384 |
| `GM1F.TXT` | 89,407 | `20`, `FIX ADJUST` | 1,024 | 16,384 | 32,768 |

Both say `EEPROM DATA INFORMATION`, type `00` / `ROM`, and start address zero.
They contain four metadata records, column labels `L0..Lf`, and sequential rows
`H000...`, each with sixteen four-hex-digit values. There is no separate checksum
record or footer in either supplied file. That does not establish what validation
the camera performs on import.

The declared sizes `2000` and `4000` count **16-bit values**, as verified against
all rows. Thus the two exports represent **48 KiB**, not 24 KiB, and not their
combined 134,266-byte text size. Export coordinate `Hhhh/Ll` identifies word
`0xhhhl` in a selected area; its relative binary offset is twice that word index
when the export starts at zero. It is not a CPU address or a NOR-chip offset.

Serializing each value little-endian produces the recognizable strings
`Panasonic`, `DMC-GM1` and `LUMIX` in the fixed area at relative byte offsets
`0x7f00`, `0x7f10` and `0x7f38`. Reversing bytes within each word loses those
markers. This supports that serialization for these text fields without proving
the processor's endianness or the representation of every numeric field.

The [evidence record](../evidence/gm1-settings-backup.json) contains source hashes,
counts, byte-order results and search limits. Raw identifier/string contents are
omitted; the originals and local binary serializations remain in the workspace.

## The edited language field is a useful anchor

The published [firsthand GM5 language-change account](https://www.microfournerds.com/blog/lumix-japanese-to-english)
describes changing the first language-pattern value from `0000` to `0100` in the
`U` export. This sample has:

- Area `10` / `UPDATE`, **row `H00e`, column `L3`**.
- Export word coordinate **`0x00e3`**, relative binary offset **`0x01c6`**.
- Value **`0100`**, followed by `0000,270f,6363,270f,6363`.

This is consistent with the owner's already-edited backup. We cannot calculate
an actual before/after diff without the original. The offset is a **GM1 language
anchor**, not a GM5 debug flag.

The same suffix occurs at words `0x07e3`, `0x08e3`, `0x09e3`, `0x0be3` and
`0x10e3`, all with leading value `0000`. Five complete nonzero 256-word blocks
starting at `0x0700`, `0x0800`, `0x0900`, `0x0b00` and `0x1000` are byte-for-byte
equal. Each differs from the first 256-word block in 40 positions. These are
repeated settings structures, with semantics unresolved: saved profiles, initial
values and redundancy are hypotheses. Their repetition is not a reason to edit
all matching fields.

## Searches and comparison with official firmware

Both byte orders were searched for ASCII and UTF-16 forms of `debug`, `telnet`,
`shell`, `console`, `mdump`, `memdump`, `readmem`, `readflash`, `bootrom`, `uart`,
`wifi` and `wlan`. No matches occurred. A smaller diagnostic-term set was also
searched across every archive member with no matches. Numeric flags can exist
without labels; this negative result neither proves nor disproves a console.

The official [GM1 1.1 page](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gm1.html)
was followed to its actual ZIP. Verified HTTPS, ZIP CRCs, model, header copy,
component boundaries and outer body CRC32 were checked. The BIN is 31,983,104
bytes, SHA-256
`3e8b4aab23f79db160cd016af0e466011f047add07bb7441c642f6b70df30d90`.

Unlike the GM5's eight entries, GM1 has six. Its single `eep` entry contains
**`0x60000` encoded bytes (384 KiB)**, with destination candidate `0x01fa0000`.
The supplied 48 KiB of settings therefore are not a complete byte-for-byte image
of that component. A mapped storage subset, records and defaults remain possible;
their correspondence has not been traced.

Selected nontrivial 32-byte windows from both byte-order reconstructions did not
occur unchanged in the encoded `eep`. Neither individual settings serialization
nor either concatenation order matched its 32-byte directory field under a
SHA-256 hypothesis. GM1/GM5 directory fields were not found verbatim in the
supplied settings. These are limited byte comparisons, not key recovery.

A further bounded check treated each EEPROM directory's exposed 32-byte field
as an AES-256 key, testing stored-IV CBC, zero-IV CBC and ECB for GM1's `eep` and
GM5's three EEPROM components. None of the twelve outputs recovered the selected
text markers or a complete supplied settings serialization. No metadata-as-key
decoder was established. Full receipts, hashes and limitations are in the
[comparison evidence](../evidence/gm1-firmware-comparison.json).

## How this helps investigate a debug flag

The demonstrated capability is persistent data editing that changes a known
firmware behavior. A similar mechanism **could** enable an existing diagnostic
feature if its firmware consumer and activation conditions are found. The backup
does not contain an inventory of the code that reads it, so a lone unexplained
bit cannot establish a listener, shell, logging switch or memory reader.

The owner cannot make new backups at present. The current work therefore
prioritizes [offline code consumers](offline-consumer-findings.md), including the
legacy GH2 exporter/importer and FZ30 service read modes. A known-setting diff
would map that setting and narrow other candidates; it would not identify a
debug flag by itself.

If settings captures become available later, **same-body GM5 snapshots with one
known normal menu change** can be useful, retaining a no-change control:

1. Export baseline A, then a second A without changing the selected setting.
2. Change one normal setting, such as 4:3 to 16:9, and export B.
3. Restore that setting through the normal menu and export A again.
4. Compare all files. Retain repeatable B-only changes while accounting for
   counters, timestamps and changes caused by exporting itself.

This can map a real selector and validate the address units. It does not itself
locate a console. A debug candidate becomes useful once a GM5 consumer is traced
or a documented diagnostic setting produces a reproducible response. Exporting
requires the existing service backup facility, so these files alone cannot give
an otherwise identical normal-mode versus service-mode memory comparison.

There is no established mapping from Olympus's CSV parameter `F971` to any
Panasonic word, area or bit. The `START ADDRESS` and `DATA SIZE` fields in an
imported text file also do not demonstrate a way to request arbitrary program
memory: they describe a selected EEPROM area, and import is a write operation.

## Reproduce offline

```sh
python3 tools/eeprom_inspect.py inspect PRIVATE.zip --out work/gm1-settings-new.json
python3 tools/eeprom_inspect.py compare captures/before/GM5U.TXT captures/after/GM5U.TXT --out work/gm5-setting-diff.json
python3 -m unittest discover -s tests -p test_eeprom_inspect.py -v
```

The tool reads TXT files or selected ZIP members without extracting archive
paths. It validates headers, area/type, row order and declared word counts,
reports both serializations and rejects cross-model comparisons. It does not
edit files, reconstruct an import file, contact a camera or open network sockets.
The six tests cover coordinate units, corruption, model boundaries and changed
word reporting. No settings were uploaded and the supplied ZIP remains intact.
