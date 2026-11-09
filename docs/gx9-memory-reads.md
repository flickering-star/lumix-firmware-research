# GX9 memory reads and firmware decoding

The owner's DC-GX7MK3 (Japanese GX9), reported firmware 1.4, supports
address-based **1 KiB reads through `0x5c`**, as well as indexed two-byte buffer
reads through `0x35`. Captures contain ARM startup code. A complete GX9 CPU
address map and a working decryption key have not been recovered.
The [wire evidence](../evidence/gx9-buffer-reads.json) records the measured
results and their limits. Raw captures remain private.

This follows the [Windows connection checks](gx9-windows-service-connection.md),
which initially established only error replies from `0x38`.

## Observed commands

| Operation | GX9 result | What it establishes |
| --- | --- | --- |
| `0x35`, selectors `0x10` and `0x20` | Checksum-valid `0x36` word replies, including stable nonzero data | Indexed data access works |
| `0x38`, selector `0x20`, indices `0` and `0x3f80` | Error-form reply, status `03` | These particular requests were rejected; the reason is unidentified |
| `0x3e`, selector `2`, frame classes `8`, `1`, `3` | Exact request echoes, including 1,030- and 8,198-byte frames | No bulk memory read demonstrated |
| `0x70`, index zero | One request timed out; owner reported a frozen camera and recovered it physically | This legacy program-reader trial failed; it has not been repeated |
| `0x5c`, class `1`, source interval exactly 1 KiB | `0x05` reply with data, ARM code, matching repeat controls | Address-based block reads work in the acquired ranges |
| `0x9b`, absolute byte address `0x80208000` | Checksum-valid `0x36` reply, data `fe 2b`, matching the block reader | Absolute two-byte reads work at this tested address |
| `0x75` | No GX9 trial in this investigation | Its presence and addressing remain unverified |

In decoded GH2 firmware, these additional operations include a 1 KiB absolute
reader, a RAM-relative word reader and an absolute word reader. Those are
concrete older-model handlers, not a GX9 capability list. The
[GH2 diagnostic verifier](../tools/gh2_debug_verify.py) and
[block-reader verifier](../tools/gh2_block_read_verify.py) preserve their native
evidence. Further review also traced GH2 `0x3e` to separate 1 KiB and 8 KiB read
handlers; selector `2` uses a cached buffer there. The GX9 echo results do not
reproduce those handlers' success replies. GX9's actual `0x5c` result is recorded
separately below.

## Address-based 1 KiB reads

GX9 accepts a 1,030-byte class-one request with operation `0x5c`. Bytes 4–7
contain the little-endian source byte address; bytes 8–11 contain the exclusive
end. A tested working request sets end to start plus 1,024. The remaining
payload is zero-filled; the checksum is at offset 1,028 and the zero terminator
at 1,029. Its reply has class one, operation byte `05`, 1,024 data bytes from
offset four, and a checked checksum/terminator. The USB preparation sequence
matches the word reader.

The exact source length matters. A zero-length request returned the proper
success header but requested no source bytes. A two-byte trial returned the
success header while preserving its entire request payload, so it is not counted
as a read. A canonical 1 KiB request at `0x80208000` replaced the payload with
ARM instructions. Offline disassembly using Cortex-A7 features resolves the
startup sequence, including the hypervisor-register instructions. Repeat reads
of this block matched exactly.

| Acquired interval, end exclusive | Saved bytes | Result |
| --- | --- | --- |
| `0x80000000..0x80200000` | 2,097,152 | Combined from the partial capture and later resumed reads |
| `0x80200000..0x80400000` | 2,097,152 | Initial 96 KiB plus a complete remainder capture; code block repeats exact |
| `0x80400000..0x80600000` | 2,097,152 | Additional kernel code/data, completing the six-MiB captured prefix |
| `0x80600000..0x80800000` | 2,097,152 | Finished capture recovered after Windows woke; includes the Linux boot log |
| `0x83100000..0x83500000` | 4,194,304 | Complete mapped first SquashFS image; archive integrity passed |
| `0x83500000..0x83e00000` | 9,437,184 | Complete mapped second SquashFS image; archive integrity passed |
| `0x83e70000..0x83e84000` | 81,920 | Four early page tables and an adjacent ARM entry |
| `0x83e84000..0x83ea0000` | 114,688 | Completes the adjacent 128 KiB ARM entry region |
| `0x70001c00..0x7001a400` | 100,352 | Bootstrap-referenced control storage; known code and buffer controls passed |
| `0x822ff000..0x82300400` | 5,120 | Complete DTB and first KiB at the native boot handoff address |
| `0xb4000000..0xb4000400` | 1,024 | Image-buffer data; does not locate executable firmware |

The first larger run used a 1 ms host delay versus 10 ms in the Linux-prefix
check. Its next
request at `0x800f0c00` timed out reading the response type. This does not
establish an inaccessible boundary: transfer timing and source range both
changed. The run stopped without a retry or reset. Successful preceding blocks
were saved and checked against the transfer transcript. The partial interval
begins with ARM exception-vector branches. Neither acquisition is a simultaneous
snapshot of all its bytes.

After the owner reconnected the camera and restarted the Windows PC, the same
`0x800f0c00..0x800f1000` block was read successfully with a 100 ms host delay.
Known code and buffer controls also passed. The original timeout therefore is
not a fixed boundary at that address; its exact cause remains unestablished.
The remaining interval through `0x80200000` and the next Linux-prefix interval
through `0x80400000` then completed with 10 ms host delays.

A later acquisition at `0x80600000..0x80800000` finished on the Windows PC
in about 31 seconds. Transfer of its saved archive to the analysis machine was
interrupted and completed later. All saved USB exchanges were then validated;
the camera acquisition did not need repeating. The
[Windows-local USB capture workflow](gx9-windows-local-capture.md) saves partial
and completed data before transfer.

A single canonical block request at the legacy program-base hypothesis
`0x40000000` later timed out. Its preceding known buffer and ARM-code controls
had passed. No source bytes were saved for that address and no further live USB
request was sent after the timeout. The Windows PC still reported the camera
through cached PnP identification afterward. The owner then confirmed the camera
had frozen and reconnected it. A fresh DTB acquisition and both known
controls passed afterward. The failed program address has not been repeated;
its exact failure cause remains unidentified.

The initial address came from the public PVC Linux source's RAM base and
`TEXT_OFFSET`, then was validated on this GX9. That is evidence for these reads,
not evidence that the related model's entire RAM map applies. A command-dispatch
table identifies handlers; the UPD directory describes storage components.
Neither supplies an exhaustive list of readable CPU addresses.

## Tables recovered from the RAM captures

The saved block at service address `0x80204000` has a 16 KiB structure consistent
with an ARM first-level translation table. Its 47 section entries describe
Linux virtual `0xc0000000..0xc2f00000` mapping to physical
`0x90200000..0x93100000`; 24 other entries point to smaller page tables.
The 1 MiB section format follows the
[ARMv7 architecture reference, short-descriptor translation tables](https://documentation-service.arm.com/static/5f8daeb7f86e16515cdb8c4e).
This table was decoded offline. No live TTBR register has been read, and the
translation between these physical addresses and USB service addresses has not
been verified. It is a Linux-map candidate, not the complete camera map.

The prefix at service address `0x80000000` also contains actual ARM instructions
that build four identity maps. Their table-address literals are `0x83e70000`,
`0x83e74000`, `0x83e78000` and `0x83e7c000`. Each builder fills section
descriptors across the entire 32-bit address space with different attributes.
The startup code passes the first address to a TTBR0 store. The four tables were
then acquired through USB: all 16,384 entries match the native builders exactly.
Mapping all 4 GiB in software does not establish that memory or a readable
device exists behind each address. The manual lists 8 Gbit of LP-DDR2 RAM,
equivalent to 1 GiB; 4 GiB is the address-space extent, not the installed RAM.

The [map verifier](../tools/gx9_memory_map_verify.py) checks the two exact input
hashes, every native instruction in the 64 descriptor-store loops, the TTBR0
instruction and literals, and the Linux candidate's section geometry. Its
[map evidence](../evidence/gx9-memory-maps.json) preserves the recovered ranges
and distinguishes them from measured USB-readable intervals.

## Working buffer path

The observed request is 16 bytes: class `08`, sequence `00/ff`, operation `35`,
little-endian 16-bit word index in bytes 4–5 and selector in byte 6. Byte 14 is
the sum of bytes 1–13 modulo 256; byte 15 is zero. Successful replies have
operation byte `36`, two data bytes at offsets 4–5 and a valid checksum.

Transfer preparation uses vendor request zero with index zero before bulk OUT,
then index one before each IN phase. A one-byte type read precedes the full
response. The interface and endpoints are the observed Windows profile in the
connection report.

For selector `0x20`, every word from zero through `0xbff` was subsequently
acquired, totaling 6,144 bytes. Word `0xc00` and sampled larger indices were
rejected. Index zero
changes between reads; a changing word is not a failed checksum or transport
error. Its function, including whether it is a timer, remains unidentified.

Selector `0x10` was acquired from zero through `0x4000`, totaling 32,770 bytes;
no upper boundary has been established. A 128-byte sample starting at word `0x2000` contains a
nonzero numeric table and was read twice with identical bytes. Its SHA-256 is
`41cba333d92521d01a80faf0e700d8cc1084921b95d6794b218494a74e30bc0a`.
The roles and physical addresses of both GX9 banks are unknown. Calling them
fixed EEPROM or executable RAM would go beyond the observations.

A short forward/reverse control read 16 known words with a 10 ms host delay in
0.195 seconds, approximately 82 words/second. This measures a short successful
control, not sustained firmware-dump speed. A full firmware acquisition is not
required if a small accessible key and the decoding procedure can be recovered.
The later complete buffer acquisitions took 270 seconds and 19,529 requests,
including exact repeat controls. The address-based block reader removes the
need to dump executable RAM word by word.

Fresh standard USB descriptor reads later failed even though the camera still
responded normally to its buttons. An attempted acquisition stopped before any
service command at that guard. Moving the string read after interface claim did
not fix it. Current Windows PnP properties still matched the pinned private USB
instance, bus-reported DC-GX7MK3 model, working WinUSB driver and endpoint layout.
Using those checks for model identification allowed another exact known-word
read. No driver change, USB reset or camera configuration change was used.

## Official firmware and key target

The [official GX9 1.5 archive](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gx9.html)
has been downloaded and checked offline. Its ZIP CRC passes; the binary is
102,538,240 bytes, SHA-256
`c08354c91d083d74b274c4884ab4f06d3f72e47ea289ea80c9685f2292f5b801`.
Its UPD model ID is `MC282`. The
[firmware inventory](../evidence/gx9-v15-official.json) records the source,
archive hash, component sizes and negative decoding controls.

The clear records contain empty or constant-fill data. They do not supply the
USB command table or executable loader. The known GM1 and GM5 keys, tested with
five-round AES-128-CBC against GX9 `loader1`, did not reproduce its expected
digest. These tests do not identify GX9's cipher or establish that its key is
present in either readable buffer. An exhaustive contiguous-candidate check of
the two captured buffers tested 2,389 distinct 16-byte values using both
five-round and standard ten-round AES-128-CBC. A second check of the captured
RAM plus known GM1/GM5 comparison keys tested 944,701 distinct candidates.
Neither check matched the full `loader1` SHA-256. These results do not exclude a
derived key, an expanded schedule, another cipher or a different RAM region.

A subsequent native scanner tests captured RAM and selected extracted binaries
against the first blocks of the official `dtb`, `rootfs1` and `rootfs2`
components, plus the independently recovered `zboot` prefix, assuming five- or
ten-round AES-128-CBC. It examined 9,865,358 candidate positions, including the
six-MiB kernel prefix and bootstrap control-storage capture, with no matching
four-byte prefix. A prefix match would still require
the complete component's expected digest before accepting a key. The
[structured-search evidence](../evidence/gx9-structured-key-search.json) records
the exact input hashes and assumptions. The result does not establish GX9's
cipher or rule out other key representations and memory locations.

Four complete plaintext components now match the official update hashes through
RAM recovery and verified padding reconstruction. See the
[component recovery report](gx9-recovered-components.md). This does not recover
the encryption key or the main camera program.

If GX9 shares the AES-128 design, the key is only 16 bytes: eight word reads
once accessible. The unresolved steps are locating the key, establishing access
to that address and validating the decoding procedure against component hashes.
Reading an arbitrary 16-byte candidate without a successful decode is not key
recovery. No update to the owner's camera has been performed.

## Absolute two-byte read

A later `0x9b` trial read the first word of the established ARM code block at
`0x80208000`. The result `fe 2b` matches the canonical `0x5c` capture, and buffer
controls before and afterward also passed. The request is a 16-byte class-eight
frame with the little-endian byte address in bytes 4–7. The reply uses operation
`0x36` and returns two bytes at offsets 4–5. The
[word-read evidence](../evidence/gx9-absolute-word.json) preserves the actual
request and response bytes and capture hash.

This establishes a second address-based reader; it does not find new mapped
ranges. The corresponding legacy writer remains untested on GX9. The planned
RAM-padding write control was interrupted before any write request was sent.

## Platform sources and the flash-label conflict

Panasonic's GX9 service manual DSC1803005CE labels IP6001 **NOR FLASH ROM/1G-bit**
in its overall diagram (page 66), but **NAND FLASH ROM/1G-bit** in the detailed
video/audio diagram (page 68).
[Manufacturer manual, hosted copy](https://www.manualslib.com/manual/3469825/Panasonic-Lumix-Dc-Gx9p.html).
Both labels imply 128 MiB capacity. The contradictory names do not establish a
CPU mapping or explain the failed program read. The previous report's NOR label
and an intermediate NAND-only interpretation were each too definite.

The [public GH5 Linux 3.18.18 source](https://ospo.panasonic.com/oss/source/dsc/DC-GH5/linux-3.18.18.tar.gz)
contains Panasonic PVC platform code. Its
DSC device tree declares Linux RAM at `0x80200000`, but it is a GH5 build and
does not establish the address space used by GX9 service commands. Referenced
platform include files are absent from the supplied archive. The official
GX9 source page currently redirects to a sign-in page, so that specific source
has not been obtained. [Leica D-Lux 8's public source archive](https://leica-camera.com/sites/default/files/pm-14937-Leica-DLUX_8-OSS-SourceCode.zip)
contains a Linux 3.18.48 comparison archive that
does not contain the Panasonic PVC platform files. The PVC Linux RAM candidate
was later tested successfully with a full 1 KiB GX9 request, as described above.

## Offline capture verification

`tools/gx9_capture_verify.py` checks saved request/response lengths, sequence
complements, checksums, type-byte/full-frame agreement, errors and transport
failures. It identifies exact request echoes, zero-length copies and unchanged
source bytes separately from successful reads.
It has no USB or network access:

```sh
python3 tools/gx9_capture_verify.py --selftest
python3 tools/gx9_capture_verify.py work/private-captures/CAPTURE --out work/verified.json
```

`tools/panasonic_buffer_key_check.py` checks raw 16-byte candidates against a
complete expected component digest without saving candidate plaintexts. Its
controls include a NIST CBC vector and an unaligned independently recovered GM1
key. It compiles only the repository's host AES implementation and has no
camera/network access.

Only the command-specific observations above are GX9 results. The working
reader still needs a model-specific address map; a related-model address is a
hypothesis until checked against actual GX9 data.
