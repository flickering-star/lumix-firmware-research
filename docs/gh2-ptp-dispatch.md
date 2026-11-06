# GH2 PTP dispatch compared with the measured GM5 list

The verified GH2 1.2 plaintext contains the exact sixteen-operation PictBridge
list measured from the owner's GM5. Its inspected PTP dispatch table contains
23 operations, all accounted for by two embedded operation lists. No
manufacturer-specific memory-read operation appears in that table.

This is a comparison of a traced GH2 implementation with an actual GM5 response.
It does not establish that their individual handlers are identical, or exclude
problems within ordinary file-reading handlers. The separate GH2
[binary maintenance readers](gh2-debug-tools.md) use another transport.

## Native links and operation inventory

The [evidence report](../evidence/gh2-ptp-dispatch.json) pins the GH2 decoded body,
checks 96 native instructions across seven regions and three relative calls,
and reproduces 23 successful and nine unsupported table lookups. Its normal
operation-list control is the existing, sanitized
[GM5 USB observation](../evidence/gm5-usb-pc-ptp.json); no new query was sent.

| GH2 location | Reviewed behavior |
| --- | --- |
| `0x407f2a2e` | Sixteen u16 operation codes, equal to all sixteen measured GM5 codes |
| `0x401f265f` | Copies that 32-byte list into the normal DeviceInfo builder |
| `0x401f284a` | Serializes count 16 and the 32 operation bytes |
| `0x407f2a67` | Alternate list of 21 operation codes, including standard MTP property operations |
| `0x401f2a00` | Copies the alternate list into another DeviceInfo builder |
| `0x401f1ed2` | Operation `0x1001` chooses between the builders according to state word `0x744ddf36` |
| `0x401f1e85` | Bounds the opcode to `0x1001..0x9805`, subtracts `0x1000`, then probes a 32-slot hash table |
| `0x407f2c28` | Table of 32 eight-byte key/branch pairs, with 23 nonempty entries |
| `0x401f4835` | Unsupported branch stores PTP response `0x2005` |

The normal list is:

```text
1001 1002 1003 1004 1005 1006 1007 1008
1009 100a 100c 100d 1014 1015 1016 101b
```

The union of this list and the alternate list equals the complete set of
nonempty dispatch keys. The alternate list adds `100b`, `100f`, `1010`,
`9801`, `9802`, `9803` and `9805`, and omits `100c` and `100d`. These are
standard PTP/MTP operation values, as defined in
[libgphoto2's maintained PTP header](https://github.com/gphoto/libgphoto2/blob/master/camlibs/ptp2/ptp.h).
Their presence does not authorize treating an unadvertised operation as a safe
query; some standard operations change or delete data.

The inspected table has no `9102`, `9103`, `9104` or `9703` entry. Reports about
those Panasonic vendor operations on newer cameras therefore do not identify
a handler in this GH2 dispatcher. The raw maintenance values `70` and `9b`
are outside its opcode range. The alternate-list selector is a separate state
word, not the USB descriptor-mode byte or saved maintenance mode.

## Reproduce

```sh
python3 tools/gh2_ptp_verify.py work/legacy-control/GH2__V12.body.decoded.bin --out work/gh2-ptp-dispatch-new.json
```

The [verifier](../tools/gh2_ptp_verify.py) refuses changed GH2 input, an altered
GM5 operation-list control and an existing output. It generates no USB packet
and performs no device or network operation. The table model is limited to the
reviewed lookup algorithm; it is not a full camera emulator.
