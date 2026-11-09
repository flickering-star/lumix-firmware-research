# GX9 components recovered from RAM

Four plaintext components now match the **complete expected SHA-256 values**
in the official GX9 1.5 package: `zboot`, `dtb`, `rootfs1` and `rootfs2`.
The source camera still reports firmware 1.4 according to its owner. These
matches mean those particular components were reused in 1.5; they do not mean
the camera was upgraded or that its main camera program has been recovered.

The UPD directory contains 36 records, including one empty record. The
[official-package evidence](../evidence/gx9-v15-official.json) describes the
container and the [recovery evidence](../evidence/gx9-recovered-components.json)
records the full component comparisons. The encryption key remains unknown.

| Component | USB service address | Captured bytes used | Official component bytes | Comparison |
| --- | --- | --- | --- | --- |
| `zboot` | `0x80120000` | 2,048 | 2,048 | Exact, unchanged RAM slice |
| `dtb` | `0x822ff000` | 4,096 | 4,096 | Exact, unchanged RAM slice |
| `rootfs1` | `0x83100000` | 4,194,304 | 4,194,304 | Restore unused padding; full digest matches |
| `rootfs2` | `0x83500000` | 9,437,184 | 12,582,912 | Restore unused padding and append 3 MiB of `ff`; full digest matches |

## Filesystem padding

Both SquashFS images were acquired completely through the end of their
RAM-backed mappings. Each mapping's final four bytes are `40 01 00 00`, where
the official update's plaintext has `ff ff ff ff`. Their role is not yet
established. No other captured byte differs from the reconstructed update
component. The second update record also has 3 MiB of erased-fill padding
beyond its nine-MiB RAM mapping.

The reconstruction preserves the filesystem through its next 4 KiB boundary
and fills the remaining update extent with `ff`. Both entire component hashes
then match the original update directory. This verifies the filesystem contents
and padding reconstruction; the original RAM files remain unchanged.

All **538 regular files** have also been extracted, totaling **26,068,454
decompressed bytes**. The full images have 947 entries including directories,
symbolic links and device nodes. Extraction created only ordinary files.
Linux filenames that collide on a case-insensitive Mac filesystem have distinct
output names, recorded in the private extraction manifest.

Private artifacts are under `work/gx9-filesystems/rootfs1-files/`,
`rootfs2-files/` and `all-regular-files-manifest.json`. Verified update component
copies are under `work/gx9-components/`. Their contents are not committed.

## Boot handoff and complete device tree

The captured `zboot` is ARM code. Its core-three path loads `r2` with
`0x922ff000` and branches to `0x92300000`. The corresponding candidate service
addresses were then tested. The first contains the complete DTB, whose
4,096-byte hash matches the official component. The first KiB at the entry
address does not contain the standard ARM zImage magic, so preservation of the
original compressed Linux boot image there has not been established.

The DTB parses completely: **18 nodes and 81 properties**. It identifies
`panasonic,pvc02v-brb`, exposes CPU 3 to Linux, and describes a 47 MiB Linux
RAM region beginning at physical `0x90200000`. Its root-filesystem command line
agrees with the recovered runtime log.

| Hardware node | DTB status |
| --- | --- |
| PL011 UART at `0x7f050000` | `disabled` |
| PL011 UART at `0x7f051000` | `disabled` |
| PL011 UART at `0x7f052000` | `disabled` |
| PL011 UART at `0x7f053000` | `okay` |
| SDIO at `0x7c320000` | `okay` |
| Other three listed SDIO controllers | `disabled` |

A node marked `okay` does not establish that a usable Linux driver, routed
connector or console exists. No UART/PL011/8250 names were found in the recovered
core kernel symbols or a corresponding serial-driver filename in either
filesystem inventory. The serial getty's live open error remains consistent
with an unavailable console. No pin, driver, DTB or startup setting was changed.

## Reproduce the offline checks

The [component verifier](../tools/gx9_component_ram_verify.py) checks pinned
capture hashes and the official binary's identity, parses its directory and
CRC, reconstructs only the defined padding, compares complete plaintext hashes,
and checks the native boot handoff instructions. It performs no device or
network access:

```sh
python3 tools/gx9_component_ram_verify.py \
  --firmware work/gx9-official-v15/GX9__V15.bin \
  --prelinux work/gx9-protocol-analysis/gx9-prelinux-2m.combined.bin \
  --rootfs1 work/gx9-filesystems/rootfs1.squashfs \
  --rootfs2 work/gx9-filesystems/rootfs2.squashfs \
  --handoff-heads work/private-captures/20261109T012731Z-gx9-linux-boot-handoff-heads/memory.bin \
  --out work/gx9-component-check.json \
  --components work/gx9-components
```

These are selected component recoveries. The complete flash, main camera
program, firmware key, working shell and alternate boot path remain unresolved.
