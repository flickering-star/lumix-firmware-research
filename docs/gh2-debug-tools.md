# GH2 1.2: binary diagnostic readers found; text shell unconfirmed

Static review of the verified GH2 1.2 plaintext found **binary maintenance
handlers that read firmware, RAM and an explicit memory address**. An interactive
text shell, its activation sequence and equivalent GM5 handlers have not been
established. These findings provide a more concrete comparison target than an
unidentified settings flag.

The [evidence report](../evidence/gh2-debug-tools.json) includes selected native
disassembly, input hashes, command-table links and limits. The
[verifier](../tools/gh2_debug_verify.py) checks this specific GH2 sample; it does
not communicate with a camera.

## The plaintext and its second code segment

The input comes from Panasonic's
[official GH2 1.2 archive](https://av.jpn.support.panasonic.com/support/share/eww/en/dsc/fts/mac/GH2__V12.zip).
The decoded body's full MD5 is `35cb77e2ef08df9ef334ff1e496b0b02`, matching the
value stored in the package; its SHA-256 is
`7501269737da3fcba4b9483d9171b291b9c96bf08780eaa83b24128cffd512ea`.
This is the previously verified legacy Panasonic AES decode, not a new GM5 key.

The body contains at least two useful address mappings:

| Body offset | Linked/runtime address | Evidence |
| --- | --- | --- |
| `0x400` | `0x40000000` | Main reset entry and string references |
| `0x8c0400` | `0x7bbc0000` | Second reset entry, library routines and `USBMNT` reference |

The main startup calls `0x400046e7`, whose copy loop reads flash from
`0x408c0000` to `0x40ae0000` exclusive, a `0x220000`-byte span. Its destination
arithmetic produces `0xbbbc0000`; the contained code uses linked addresses
starting at `0x7bbc0000`. The hardware alias relationship has not been separately
verified. Under the second mapping, previously unresolved calls decode into
recognizable byte-copy, fill, string-copy, string-compare and string-length loops.
This locates those library calls inside the update.

`USBMNT` has actual consumers: the main handler compares that tag at
`0x400d7959`, and the second segment checks it at `0x7bcfc527`. This distinguishes
the finding from a filename or an isolated diagnostic string.

## The memory readers

The receive-state path calls the command dispatcher at `0x401ef0a5`. It reads
the selected operation from state at `0x744dcbe8`, bounds the operation to
`0..211`, then indexes the 212-entry branch table at `0x407f2064`. The verifier
checks both the selected table entries and each branch's call displacement.

| Operation | Reader address | Observed source calculation |
| --- | --- | --- |
| `0x35` | `0x401ef8af` | Bounded word index into settings buffers |
| `0x38` | `0x401ef9ae` | Bounded word index into selected EEPROM flash banks |
| `0x46` | `0x401efc76` | Register window at `0x9c000000 + 2 × index` |
| `0x70` | `0x401f01d3` | `0x40000000 + 2 × index` |
| `0x75` | `0x401f022b` | `0xb4000000 + 2 × index` |
| `0x9b` | `0x401f02cb` | Supplied absolute byte address |

The last three assemble a full 32-bit little-endian value from input bytes
four through seven. `0x70` and `0x75` double it as a word index using 32-bit
arithmetic and read two bytes. `0x9b` uses it directly for a 16-bit load. Each
passes two result bytes to the response builder at `0x401ef37c`.

No address-range comparison was identified **inside those three reader bodies**.
This is not a finding that every address is mapped/readable, or that arbitrary
requests reach them in a normal camera USB session. The surrounding USB state,
service-mode selection and complete activation conditions remain unresolved.

The older FZ30 host's `0x38` operation now has a GH2 camera-side comparison:
GH2 selects bases `0x40fa0000`, `0x40fc0000` or `0x40fe0000` according to the
settings area, with limits of `0x1000` or `0x4000` words. That reader alone does
not expose the whole firmware. The separate `0x70` and `0x9b` handlers are the
stronger leads for recovering executable bytes if a corresponding GM5 interface
can be established.

## Logging and the shell search

The whole decoded body was searched for case-insensitive ASCII and UTF-16
literals. No `debug`, `console`, `shell`, `telnet`, `uart`, `assert`, `memdump`,
`readmem`, `readflash`, `password`, `baud` or `115200` literal was found. The ASCII
`help` and `login` hits are substrings of longer printable byte runs, with no
identified shell prompt or parser context. All fourteen
ASCII `command` matches belong to SD-card driver messages. These are limited
negative results, not proof that an undocumented shell cannot exist.

`SDLOG.TXT`, `LogBuffFull` and sequence-log messages are retained in the image.
No direct four-byte pointer to `SDLOG.TXT` under the main mapping was identified;
its activation remains untraced. Merely placing that filename on a card is not
an established trigger.

Other log exports have concrete code. At `0x400f0283`, an input byte equal to
zero leads to file-write helper `0x400f010d` with:

| Destination | Source buffer | Bytes |
| --- | --- | ---: |
| `A:\develop.bin` | `0x74010b38` | 1,024 |
| `A:\histlog.bin` | `0x7400cb38` | 16,384 |
| `A:\userlog.bin` | `0x74019b3c` | 16,384 |

The user-log wrapper starts at `0x400f02c3`. Their callers include state and flag
conditions that have not been completely traced. These are bounded diagnostic
buffer exports, not demonstrated firmware dumps or a command interpreter.

## Entropy comparison

Both original updates are essentially at the maximum byte-value entropy:

| Full BIN | Bytes | Shannon entropy, bits/byte |
| --- | ---: | ---: |
| GH2 1.2 | 15,599,104 | 7.999990161 |
| GM5 1.1 | 31,901,184 | 7.999994668 |
| GH2 decrypted body | 15,598,592 | 6.869464690 |

The [full-region measurements](../evidence/gh2-gm5-entropy-comparison.json) also
cover payload-only regions. Matching high entropy does not establish the same
cipher, key or compression. The verified GH2 key has already failed the recorded
direct GM5 decoding checks.

## Reproduce the static checks

With the existing decoded GH2 body and the
[MN103 host decoder](../tools/mn103_adapter/README.md):

```sh
python3 tools/gh2_debug_verify.py work/legacy-control/GH2__V12.body.decoded.bin --out work/gh2-debug-check-new.json
```

Use a fresh output path. The verifier requires the exact plaintext hash, checks
six command-to-reader paths, and checks every instruction's raw-byte annotation
and region continuity in seventeen selected regions. It records manual semantic
interpretations separately from those mechanical checks. Firmware instructions
are neither emulated nor executed.

The [USB maintenance entry follow-up](gh2-usb-maintenance-entry.md) now traces a
settings-state gate, temporary override and internal message path into GH2's
`04da:2370` vendor interface. Its normal PC/PTP configuration descriptors match
the saved GM5 observations exactly. The remaining access questions are the
physical input mapping, complete transport conditions and GM5 equivalence.
No physical camera session, memory dump or settings change was performed during
this GH2 static study. The later [GM5 USB observation](gm5-usb-observation.md)
queried normal PictBridge information; it did not send the GH2 maintenance commands.

## How this plaintext was obtained

This investigation downloaded the official GH2 update, used the publicly
documented legacy AES-128-CBC key, and verified the complete plaintext against
the MD5 stored in the official package. The GNU MN103 decoder then produced
assembly instructions for manual control-flow review. There was no chip dump
in this acquisition, and the original source code was not recovered.

The historical project's initial access work was separate. In a
[September 2010 interview](https://www.43rumors.com/tester13-the-gh2-is-the-best-but-also-disastrous-camera-for-video-shooters/),
Vitaliy Kiselev explicitly proposed BGA desoldering and direct flash reading. In
his [January 2011 development post](https://www.dvxuser.com/threads/news-about-gh2-firmware.238364/),
he said that he already had an encrypted GH2 update and planned hardware-assisted
dumping to reach decryption. These firsthand sources document the intended
approach; the precise completed chip-read procedure, hardware and original key
recovery have not been verified here. The known-key update decode used above
does not depend on that historical detail.
