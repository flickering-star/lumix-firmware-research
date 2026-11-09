# GX9 native USB service dispatcher

The decoded **1.4 `postboot5`** image contains the maintenance interface and its
command dispatcher. Native ARM execution now reproduces the measured USB
profile and **all 14 complete replies** in the owner's saved policy experiment,
including the two RAM writes and exact restoration. This work is offline; it
does not open the camera or send new requests.

The [verifier](../tools/gx9_usb_native_verify.py) pins the main program,
`postboot1` and `postboot5` hashes. Its
[results](../evidence/gx9-usb-native-controls.json) include the first dispatch
destination for every opcode `0x00..0xff`, additional scratch-RAM controls, and
the route used by several queued commands.

Reproduce with Unicorn 2.1.4, the decoded 1.4 directory, and the saved owner-run
policy capture:

```sh
python tools/gx9_usb_native_verify.py \
  --components work/gx9-components-v14-decoded \
  --capture work/gx9-ssh/20261109T142756Z-gx9-owner-policy-archive \
  --observed-profile evidence/gx9-windows-service-connection.json \
  --out work/gx9-usb-native-controls.json
```

## Interface and measured wire replay

Descriptor builder `0x054015a0` produces the same high-speed device descriptor,
39-byte configuration, interface `ff/a0/b0`, and endpoints observed on Windows:

| Endpoint | Type | Maximum packet | Interval |
| --- | --- | --- | --- |
| `0x01` | Bulk OUT | 512 bytes | 0 |
| `0x82` | Bulk IN | 512 bytes | 0 |
| `0x83` | Interrupt IN | 64 bytes | 16 |

The native full-speed variant uses 64-byte bulk packets. That variant has not
been measured physically. The vendor/product IDs are `04da:2370`.

The first command dispatcher is `0x053fbd16`. The replay executes its handlers
and reply/checksum code; none of the word/block handlers is replaced. Initial
data comes from the acquired Linux, updater and policy blocks, plus the acquired
A-bank control word. C copy/zero helpers are modeled. The test compares each
entire generated response with the capture and checks the restored block.
USB controller timing and MMU/cache behavior are outside this test.

## Fixed-settings bank selection

| Operation | GX9 handler | Native behavior |
| --- | --- | --- |
| `0x34` | `0x053fbaf4` | Write one bounded word in a settings RAM shadow |
| `0x35` | `0x053fb9b6` | Read one bounded word from a settings RAM shadow |
| `0x38` | `0x053fba3e` | Load a selected stored bank, then return one bounded word |
| `0x3a` | `0x053fa8d0` | Report area identifiers and capacities; reply opcode `0x3b` |
| `0x9b` | `0x053fb4e0` | Absolute halfword read |
| `0x9c` | `0x053fb4ae` | Absolute halfword write and acknowledgement |

The metadata query identifies `0x10`, `0x11`, `0x21`, `0x22`, and `0x30`.
The first four have 65,536 words; `0x30` has 3,072 words. Other returned rows
contain `0xff` area placeholders and do not establish additional readable banks.

**The fixed bank is area `0x22`.** The policy is its word index `0xc00d`, which
corresponds to byte offset `0x1801a` and linked RAM address `0x03f1801a`.
Native `0x34`/`0x35` controls change this simulated word `0 → 1 → 0`.
This is a RAM-shadow edit; a persistent commit is not established.

For `0x38`, area `0x22` requests a complete 128 KiB bank from flash-driver
address `0x40e00000` into service buffer `0x193d6800`, then returns the requested
word. The full-bank byte reader is modeled in this control; the area selection,
size lookup, bounds and response execute natively. This request has not been
sent to the camera.

The previous physical `0x38`, area `0x20`, index `0x3f80` error is reproduced
exactly: `0800ff01030000000000000000000300`. That selector produces a zero
capacity, a zero-length read request, and a bounds rejection. The zero-length
wrapper itself executes natively with modeled locks and reaches no sector
operation. This explains why repeating indices within the old selector did not
recover the fixed bank.

In the shadow reader, `0x10` and `0x11` both select the A shadow. In the stored
reader, they select separate A/B driver addresses. Their identical shadow
pointer does not imply that the stored banks are the same.

## Additional memory and framing controls

Native opcode `0x48` supports halfword/word access to a supplied address and
returns opcode `0x49`; its fields include read/write and width selectors.
Opcode `0x4a` has a related write-and-acknowledge path. Scratch-RAM tests verify
16/32-bit reads, a 32-bit write with returned data, a 16-bit write with an ACK,
and a nonzero service flag blocking `0x48` without changing RAM. Neither variant
has been tried physically. These tests do not establish new physical address
ranges or persistent flash access.

Native size lookup `0x053fbf22` maps frame classes as follows:

| Class | Complete frame bytes |
| --- | --- |
| `0x08` | 16 |
| `0x01` | 1,030 |
| `0x02` | 32,774 |
| `0x03` | 8,198 |
| `0x04` | 4,102 |
| `0x05` | 106 |
| `0x10` | 262 |

The lookup alone does not prove which commands accept each class. Previous
physical larger-frame attempts failed; no such requests were repeated here.

## Commands queued to another task

The receive wrapper `0x053f8076` routes several commands through a `USBMNT`
message. Native callback registration at `0x042606ae` installs callback
`0x0425ffcc`; the callback then queues event **`0x000e8202`** to task `0xc1`,
from task `0x76`, source module `0x6b`.

Native controls trace opcodes `0x28`, `0x2b`, `0x30`, `0x31`, `0x32`, `0x33`,
and `0x37` through that route. The message class is two for `0x30`, `0x32` and
`0x33`, and one for the others. Allocation, the registration-state query, and
the final queue send are modeled; packet copying, message construction,
registration, dispatch and callback translation execute natively.

The queue consumer remains to be traced. These routes therefore do not yet
identify a USB persistent-save or updater-activation command. First-dispatch
mapping is not a reason to send arbitrary opcodes to hardware.
