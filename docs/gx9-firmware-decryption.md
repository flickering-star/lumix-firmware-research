# GX9 firmware decryption and 1.4 comparison

Both the official GX9 **1.4 and 1.5 packages now decode completely**. All **35
nonempty components** in each package match their complete plaintext SHA-256
values from the UPD directory. The directory also contains one empty record.
This supersedes the earlier four-component recovery and negative key searches.
The decoding/acquisition work performed no camera update or memory write.
A subsequent [RAM-padding write/restore experiment](gx9-ram-write.md) verified
one fixed-address writer separately.

## Key recovery from the main ARM image

The previously acquired ARM entry at USB service address `0x83e80000` begins
with `ldr pc, [pc, #0x74]`. Its literal at offset `0x7c` is `0x04327cac`.
A bounded read at candidate service alias `0x84327c00` returned ARM code at
the corresponding target. Its native branch and nearby exception-register
handling support the link between the startup entry and the larger image.

Five separately logged captures acquired `0x83e80000..0x847f0000`, exactly
**9,895,936 bytes**, the update's main-program extent. Every saved USB exchange
was independently revalidated, with known buffer and Linux-code controls before
and after each chunk. The combined RAM image SHA-256 is
`f6bbc883c4b845bbed2622aa386f09b0bc03f5ed20377851305bd0ccc56d5e07`.

The image contains the string `ThreadX SMP/Cortex-A7/RVDS Version
G5.6.1.5.1 / v2.0rel2.6`. Its scatter-loading table points to initialized data
within the main program and later postboot images. This is additional camera
runtime code alongside the previously recovered Linux system.

A raw 16-byte key at image offset **`0x8d0284`**, service address
**`0x84750284`**, passed the existing scanner's complete DTB, both rootfs and
zboot checks using **five-round AES-128-CBC**. Its SHA-256 fingerprint is
`527bb069f7940900d77f3878a71e9c8bc9a4ac39145a505a4b6fda83c331ac9b`.
The four positive checks identify one key value, not four different keys.
That key subsequently decoded every nonempty component in both update versions.
The key value and plaintext outputs remain local; the verifier can derive it
from the pinned RAM image.

## Official 1.4 package

Panasonic's former `GX9__V14.zip` download URL now returns HTTP 404. The
manufacturer release is preserved by
[TousLesDrivers' 1.4 archive listing](https://www.touslesdrivers.com/index.php?v_code=61860&v_langue=en&v_page=23).
The downloaded archive contains `GX9__V14.bin`; its ZIP CRC, MC282 model,
UPD bounds, body CRC and all decrypted component hashes pass.

| Input | Bytes | SHA-256 |
| --- | --- | --- |
| Mirrored `GX9__V14.zip` | 100,196,757 | `45274de529765e818988b598b356c49b858159328db2a32bb743c4a16b05f7a0` |
| `GX9__V14.bin` | 102,538,240 | `e26e4b422e9d46dffb7d93eaabd061bb3e49e2d84654dffc1d892f7f25126e7a` |
| Official `GX9__V15.bin` | 102,538,240 | `c08354c91d083d74b274c4884ab4f06d3f72e47ea289ea80c9685f2292f5b801` |

The 1.4 file was retrieved from an archive mirror rather than Panasonic's live
server. The independently acquired camera bytes provide additional comparison
controls. A later [authentication check](gx9-update-authentication.md) verified
both packages' P-256 signatures using the public point in the camera's 1.4
program, independently with OpenSSL and in native ARM emulation.

## Camera RAM compared with 1.4

The earlier boot-area capture also contains the complete 1.4 `loader3` at
service address `0x80000000`: all 40,960 bytes match, SHA-256
`5bb1c4d827009738eaff6067a5befc1713b22ad6da3df6047f7d0d8fcd71518f`.
The 1.5 loader differs at just one byte, offset `0x157e`.

All five postboot images were acquired from the contiguous ARM image layout:

| Component | Service start | Bytes | Entire captured image matches 1.4 | Also matches 1.5 |
| --- | --- | --- | --- | --- |
| `postboot1` | `0x847f0000` | 4,456,448 | Yes | No |
| `postboot2` | `0x84c30000` | 7,602,176 | Yes | No |
| `postboot3` | `0x85370000` | 131,072 | Yes | Yes |
| `postboot4` | `0x85390000` | 131,072 | Yes | Yes |
| `postboot5` | `0x853b0000` | 1,835,008 | Yes | No |

Together with `loader3`, `zboot`, `rootfs1`, `rootfs2` and `dtb`, there are **ten
independently captured components matching 1.4**. The filesystem comparisons
include the previously documented padding reconstruction. Only six of these
ten components are unchanged in 1.5. `postboot3` and `postboot4` each consist
of a small `LOAD` header with only 28 bytes differing from their `ff` padding;
their full hashes match, but they do not represent large additional code images.

The main RAM image is also consistent with the 1.4 program. It differs from
the decoded 1.4 image in **211,636 bytes**, all before offset `0xd0000`.
The remaining **9,043,968 bytes match exactly**. Differences include startup
bookkeeping and populated regions that were zero or `ff` in the update.
These observations do not identify the purpose of every changed byte. The raw
RAM image is preserved unchanged and is not counted as a whole-hash match.

Eight component plaintext hashes changed from 1.4 to 1.5: `loader3`, `program`,
`postboot1`, `postboot2`, `postboot5`, `eep_fix`, `osdover` and `usbcharge`.
The other 27 nonempty components were reused; the empty record is also unchanged.
This explains why Linux filesystems matched 1.5 while the camera reported 1.4.

## Reproduce offline

[The decoder](../tools/gx9_update_decode.py) uses the existing host AES codec,
checks its independent controls, preserves CBC chaining across large components,
and rejects any component whose entire plaintext hash differs. It never opens
a camera or network connection. Outputs below belong under the private work
directory:

```sh
python3 tools/gx9_update_decode.py work/gx9-official-v15/GX9__V15.bin \
  --main-ram work/gx9-protocol-analysis/gx9-arm-main-candidate.bin \
  --components work/gx9-components-v15-decoded \
  --out work/gx9-v15-decoded-check.json

python3 tools/gx9_update_decode.py work/gx9-official-v14/GX9__V14.bin \
  --main-ram work/gx9-protocol-analysis/gx9-arm-main-candidate.bin \
  --components work/gx9-components-v14-decoded \
  --out work/gx9-v14-decoded-check.json
```

[1.4 decoding evidence](../evidence/gx9-v14-decoded.json),
[1.5 decoding evidence](../evidence/gx9-v15-decoded.json) and
[runtime comparisons](../evidence/gx9-arm-recovery.json) record hashes and limits.
Raw camera captures, firmware binaries and connection material are excluded
from publication.

The remaining work is native analysis of the USB service handlers, externally
reachable command delivery, and the existing firmware installation/recovery
mechanisms. Decryption alone does not establish a working shell or an accepted
modified update.
