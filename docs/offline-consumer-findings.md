# Offline settings-consumer investigation

The owner cannot make new backups at present. Work therefore proceeds through
code already available offline. Changing a known setting can map that setting,
but does not identify a debug flag by itself. The current priority is a traced
consumer, a documented diagnostic mechanism or a way to recover GM5 code.

Two older artifacts now provide concrete consumers: the FZ30 service executable
and the independently decoded official GH2 1.2 firmware. **Neither establishes a
GM5 console, GM5 memory reader or GM5 vulnerability.** They make particular paths
available for comparison without requiring a new camera capture.

## FZ30: the buffer/ROM distinction is an actual read-mode selection

Further static analysis of the [FZ30 package](service-software-findings.md)
recovered self-consistent compiler method records that associate UI event names
with native PE code addresses. The relevant handlers and their downstream calls
show:

| UI/control | Host PE address | Observed consequence |
| --- | --- | --- |
| `RomRadioButtonClick` | `0x402908` | Sets a host object mode byte to zero |
| `BufferRadioButtonClick` | `0x402978` | Sets the same byte to one |
| Shared read dispatcher | `0x402a90` | Mode one calls `0x40d030`, operation `0x35`; mode zero calls `0x40d10c`, operation `0x38` |
| `UpdateRadioButtonClick` | `0x404f24` | Selects area `0x10` |
| `AdjustRadioButtonClick` | `0x404f2c` | Selects area `0x20` |
| Response-word helper | `0x40d390` | Combines two response bytes little-endian |

The shared dispatcher compares positive addresses against `0x0fff` for the update
area and `0x3fff` for the other area before dispatch. These are host-side checks,
not proof of camera-side access enforcement. Both operations send a two-byte
address and the selected area through the previously traced packet builder.
The returned word is read at response offset four.

There is also a bulk EEPROM read: `ReadButtonClick` calls `0x40df7c`, which selects
area `0x10` or `0x20`, requests operation `0x3e` through `0x40e2b0`, and receives
`0x2000` bytes. The framing is an older USB service protocol; no packet was sent.

This ties the area values in settings exports to an older real service API.
It does not turn the host's local mode byte into an on-camera debug-enable flag.
The buffer mode uses the same selected EEPROM areas; arbitrary main-processor
RAM access has not been established. Updated hashes, named method records and
disassemblies are in [the service evidence](../evidence/fz30-service-software.json).

## GH2: actual firmware writes the same text-export format

The official GH2 1.2 package was previously used as a positive control for the
legacy Panasonic AES implementation. The complete decrypted body's MD5 matches
the value stored in that official package. Its SHA-256 is
`7501269737da3fcba4b9483d9171b291b9c96bf08780eaa83b24128cffd512ea`.
This is a GH2 plaintext input, not a decoded GM5 image.

The inner directory places `program` at body offset `0x400` and `eep` at
`0x00e80400`. The reset entry loads `0x40000018` and jumps there. Together with
the inspected string-immediate references, this supports mapping the program
start to `0x40000000`, or body byte zero to `0x3ffffc00`.

A small [host adapter](../tools/mn103_adapter/README.md) builds the unmodified
GNU binutils 2.42 MN103 decoder. Its three downloaded source hashes are fixed;
seven known instruction controls passed, and raw-byte annotations of nine
selected regions were checked against the unchanged input. This is static
disassembly, not execution or emulation of camera instructions. It establishes
no ISA or load address for GM5.

The traced export formatter starts at GH2 candidate address `0x401df73f`:

| Selector | Header area | Buffer candidate | Exported words |
| --- | --- | --- | ---: |
| zero | `10`, `UPDATE` | `0x74001b38` | `0x1000` |
| one | `20`, `FIX ADJUST` | `0x74003b38` | `0x4000` |
| other paths | `30`, `SUB EEP`, or `40`, `UNKNOWN` | `0x7401133c` | `0x2000` |

At `0x401df9c9`, the formatter loads a 16-bit word, advances its source by two
bytes and emits four hexadecimal digits followed by a comma. It generates the
`H` row labels and CRLF every sixteen words. This is an actual code consumer of
the format found in the supplied GM1 files. GH2's update area is 8 KiB, while
the supplied GM1 update export represents 16 KiB: the layout varies by model.
The additional GH2 area labels do not prove that GM5 can export them.

The filename builder at `0x400fa8d7` selects between `EEPROM00.txt` /
`EEPROM01.txt`, `FACT_U.TXT` / `FACT_F.TXT`, and model-named `U.TXT` / `F.TXT`
paths according to its caller's mode and area. Their complete activation
conditions have not been traced; these names are comparison targets, not
instructions to place files on a GM5 card.

## An import-parser lead, with strict limits on the conclusion

The reviewed GH2 import job at `0x40026010` checks text lengths before calling
the row parser: **89,407 bytes** for the fixed file and **22,587 bytes** for the
update file. It uses fixed staging destinations and ultimately returns fixed
area extents of 32 KiB and 8 KiB.

The row parser at `0x401dfa87`:

1. Scans for the first `H000` marker.
2. Skips row labels and separators, converts four-character groups through
   `0x401dfa3b`, and writes two bytes per parsed value.
3. Advances the output pointer sequentially. The text's address/size header
   records are not used to choose that destination.
4. Stops according to remaining source characters or a NUL. No destination-
   capacity argument or output-size comparison was identified inside this loop.

Consequently, editing `START ADDRESS` does not redirect this GH2 consumer to
arbitrary program memory. Separately, the file-length check alone does not
guarantee that the number of decoded values fits the nominal settings area.

An [offline behavioral model](../evidence/gh2-row-parser-model.py) reproduces the
normal word serialization of both supplied GM1 exports. Synthetic strings held
only in host memory then exercise the GH2 caller's two exact text lengths:

| Text length accepted by the modeled size condition | Modeled decoded bytes | Nominal area bytes |
| ---: | ---: | ---: |
| 22,587 | 11,290 | 8,192 |
| 89,407 | 44,700 | 32,768 |

This is a **static/model candidate concerning decoded size**. It has not been
executed on a GH2, and the surrounding allocation boundaries and impact remain
unknown. It does not establish an exploitable overflow, code execution, a memory
reader, or equivalence in GM1/GM5. No altered settings file for restore was saved
or sent to a camera. The useful next static target is the corresponding GM5
import consumer, including any added bounds or validation.

## Another filename does not establish a loader

GH2 also references `ship.txt`. Its inspected consumer at `0x400f02ef` converts
numeric fields and returns them through caller-supplied pointers. No instruction
execution or console activation was found in that consumer. A filename alone
therefore does not identify an SD script loader.

All source hashes, selected native regions, decoder controls and model results
are retained in [the GH2 evidence](../evidence/gh2-settings-consumers.json).
The work has moved beyond searching anonymous settings words, while GM5's
payload decoding and a diagnostic entry remain unresolved.

The subsequent [GH2 diagnostic investigation](gh2-debug-tools.md) resolves a
second code segment and traces binary maintenance readers for firmware, RAM and
an explicit memory address. It supplies a stronger access lead than the import
parser. An interactive shell, physical USB reachability and GM5 equivalence are
still unconfirmed; the report also contains the GH2/GM5 entropy comparison.

The [factory SD investigation](gh2-sd-factory-inputs.md) follows additional
filename consumers through their native code: AHX files supply programming
input, while a separate BIN marker sets a RAM flag used in lens validation.
Neither is an established firmware export or GM5 diagnostic flag.
