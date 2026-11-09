# GX9 RAM write and exact restoration

The connected DC-GX7MK3 / GX9, reported firmware 1.4, accepted a **two-byte RAM
write through USB operation `0x9c`**. The test changed only unused `postboot3`
padding at service address `0x85370020`, verified the change with independent
word and block reads, and restored the complete original 1 KiB block.

This is a measured RAM writer. It does not establish a persistent flash writer,
a user-setting change or a modified firmware installation. The
[wire/readback evidence](../evidence/gx9-ram-write-restore.json) distinguishes
the three acknowledged write requests from the subsequent memory comparisons.

## Fixed experiment

The fully verified `postboot3` component is 131,072 bytes, SHA-256
`16098771484d4724dd489583aa19c08c9d624596f4369781d983ba15aef8de37`.
Its `LOAD` header describes empty initialized/uninitialized ranges and a source
extent ending at `0x0537001c`. The selected halfword lies beyond that extent
inside `ff` padding. Before writing, a fresh complete block matched the official
component, and known Linux-code and indexed-buffer controls passed.

| Stage | Target bytes | Entire 1 KiB block SHA-256 |
| --- | --- | --- |
| Before | `ff ff` | `1d9f0f5e299efe4b23c30e4316757bef6fc283acf8282dedf3acbacdf541f26f` |
| Tagged | `a5 5a` | `4ef2bbcb01aecb24037f625f4f1bec3548d608a4819d70378c121daad8159b59` |
| Restored | `ff ff` | `1d9f0f5e299efe4b23c30e4316757bef6fc283acf8282dedf3acbacdf541f26f` |

The sequence sent one same-value write, one changed-value write and one
restoration write. Each received the reviewed success ACK. `0x9b` independently
read the word after each stage; `0x5c` acquired the full before/tagged/restored
blocks. Exactly offsets `0x20` and `0x21` changed during the tagged stage.
Code and buffer controls passed again afterward. All 14 USB transactions were
revalidated offline; no flash operation or update initiation was sent.

## Frame layout

The 16-byte class-eight request contains operation `9c`, a little-endian
32-bit byte address at bytes 4–7, and the two data bytes at 8–9. Bytes 10–13
are zero; sequence complement, checksum and terminator use the established
protocol. The actual changed-value request was
`0800ff9c20003785a55a000000007600`.

The success ACK is `0800ff01000000000000000000000000`. An ACK by itself is
insufficient evidence of a write; the before/after/restore reads establish the
actual memory change. Address bounds and write access outside the fixed tested
location remain unverified.

## Reproduce the offline proof

The [verifier](../tools/gx9_ram_write_verify.py) reads saved evidence only. It
requires the exact experiment sequence, official empty-module header, original
component hash, independent word/block comparisons and complete restoration:

```sh
python3 tools/gx9_ram_write_verify.py \
  --capture PRIVATE_CAPTURE_DIRECTORY \
  --component work/gx9-components-v14-decoded/postboot3.plaintext.bin \
  --out work/gx9-ram-write-check.json
```

Negative controls independently corrupted an extra byte in the tagged block
and one byte in the restored block. Both were rejected.

The next prepared local USB tool checks the updater-policy field described in
[the authentication analysis](gx9-update-authentication.md). Its Windows-local
inspection and optional temporary round trip are separate from this completed
padding experiment.
