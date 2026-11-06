# GH2: documented service buttons and USB transfer preparation

The startup predicate previously traced into GH2's vendor USB mode now agrees
with the **documented temporary service entry**. The USB path also has a concrete
transfer-preparation request, independently matched to the older Panasonic host
driver. These results strengthen the service-USB route for investigation; GM5's
service identity and memory readers still require direct evidence.

The [new evidence](../evidence/gh2-usb-service-sequence.json) contains selected
native instructions, initialized key-map bytes and source hashes. Its
[offline verifier](../tools/gh2_usb_service_verify.py) repeats the earlier entry
checks and adds 735 MN103 instructions in sixteen regions, fifteen call links,
and 263 x86 instructions in seven historical host regions. Neither camera
instructions nor Windows programs/drivers were executed.

## The startup buttons can be named

Panasonic's GH2 service manual `DSC1011058CE`, pages 14 and 21, describes
temporary service entry using the drive lever at **SINGLE**, holding **DISPLAY
and AF/AE LOCK** during power-on. Both the initial-settings procedure and the
error/camera-information procedure use that entry. The downloaded
[manufacturer-authored PDF](https://www.partstown.com/modelManual/PAN-DMCGH2_sm.pdf?v=1670948469862)
has 85 pages, 8,343,062 bytes and SHA-256
`e885754a31db62848ddace241f27995f6b0e62bd06e199baeb373d4d39430f8c`.

PDF page 60, printed `S-5`, shows the rear-button resistor ladders. DISPLAY and
AF/AE LOCK each occupy the 2.4-kilohm position on different input lines. DELETE
occupies the 13.8-kilohm position on AF/AE LOCK's line. Those distinct inputs
agree with the firmware's ADC tests:

| Physical key | ADC decoder | Raw key bit | UI key bit |
| --- | --- | --- | --- |
| DISPLAY | `0x7bccaa02` | `0x800` | `0x40` |
| AF/AE LOCK | `0x7bcca999` | `0x400` | `0x400` |
| DELETE | `0x7bcca999` | `0x80` | `0x80` |

These labels combine the circuit drawing, decoded routines and the manual's
startup procedure. They are static interpretations, with no live GH2 input
capture. They do not supply a GM5 button sequence.

### Native evidence behind the mapping

The decoders compare the absolute difference from calibration references against
59. GH2's fixed flash bank has default key centers `0`, `198`, `395`, `593`;
the same second center produces AF/AE LOCK's raw `0x400` and DISPLAY's raw
`0x800`. The helper at `0x7bccb358` specifically tests the latter. Startup
predicate `0x7bccb3b7` requires both keys, drive-decoder result two, and settings
state one. Caller `0x40003891` then writes two to settings RAM at `0x74001e30`.
The drive label is corroborated by the documented procedure; it has not been
independently measured on hardware.

The raw/UI translation table is now located, rather than guessed from bit values.
Startup loop `0x40002016` copies initialized data from
`0x407f6384..0x4080cff8` to RAM at `0x743551f4`. A 160-byte table at body offset
`0x80bfcc` consequently maps to **`0x7436aa3c`**, the address consumed at
`0x7bccafe7`. Its twenty input-bit/output-bit pairs include all three rows above.
The verifier checks the copy constants, resulting address and selected mappings.

This also narrows the separate RAM-override lead: the UI event bit `0x80` tested
at `0x400d6475` corresponds to **DELETE**, while DISPLAY is `0x40`. The event
builder maintains held, newly pressed, repeat and release fields. Complete
timing, connection-state and subsequent-selection conditions remain untraced,
so this does not establish an additional standalone button recipe.

## A vendor control request prepares the binary transfer

Setup-packet decoder `0x401e966d` copies the USB setup fields into state:

| Field | GH2 state address |
| --- | --- |
| `bmRequestType` | `0x744dd1f8` |
| `bRequest` | `0x744dd1f9` |
| `wValue` | `0x744dd1fa` |
| `wIndex` | `0x744dd1fc` |
| `wLength` | `0x744dd1fe` |

Request-type helper `0x401e96eb` extracts bits `0x60`. Dispatcher `0x401e7549`
calls the vendor handler **only when the already selected descriptor mode is
two**. That handler, `0x401eed80`, accepts request zero and branches on `wIndex`:

| Request zero branch | Observed effects |
| --- | --- |
| Index zero, `0x401eedad` | Clears maintenance state, selects bulk phase three and receive state five, prepares an endpoint and control status |
| Index nonzero, `0x401eedef` | Restores bulk phase three, readies a pending transfer and resets its cursor |

Neither branch reads `wValue`. The reviewed path writes USB registers and RAM;
no flash-programming routine was identified in it. This is transfer preparation
after service-mode selection. It does not establish a transition into service
mode from normal PC/PTP USB.

With receive state five, `0x401eee32`'s receive path reaches the bulk-header
decoder at `0x401ef4b2`. That decoder takes the operation from byte three and
sets a sixteen-byte total for type `0x08`. Once the expected bytes accumulate,
the receive path changes to command-dispatch state. This agrees with the older
FZ30 host's sixteen-byte `08 00 ff 38 ...` request layout. Full validation of
all header, checksum and USB status conditions remains incomplete.

## The older host provides an independent comparison

The pinned FZ30 `mkeusb01.dll` exports **`preBulkWrite_CZ30`** through thunk
`0x10001032`, whose target `0x10001a50` issues Windows IOCTL `0x230034`.
The pinned `mkeusb01.sys` dispatches it to `0x10d3a`, which constructs:

| Host URB / USB field | Reconstructed value |
| --- | --- |
| URB function | `0x17`, vendor request to device |
| Transfer direction / length | OUT / zero bytes |
| USB `bmRequestType` / `bRequest` | `0x40` / zero |
| `wValue` | Caller-supplied 16-bit value |
| `wIndex` | Zero |

The interpretation uses Microsoft's
[URB structure documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usb/ns-usb-_urb_control_vendor_or_class_request)
and [USB header definitions](https://raw.githubusercontent.com/microsoft/win32metadata/main/generation/WinSDK/RecompiledIdlHeaders/shared/usb.h).
The byte stores, branch/call links and instruction continuity are checked against
the unchanged host binaries. The corresponding `preBulkRead_CZ30` path uses
IOCTL `0x230030`, request zero and index one.

The host names and field values agree with GH2's camera-side preparation branches.
This is evidence from two independently inspected implementations. The
reconstruction remains untested on camera hardware, including GM5.
The [historical package analysis](service-software-findings.md) records where the
host binaries came from and how they were extracted without installation.

The subsequent [transport comparison](usb-transport-comparison.md) traces GH2's
vendor SCSI paths. They check a saved service state; the raw memory-reader
operations are not direct SCSI CDB opcodes. Mass-storage framing inside the
service code therefore does not establish entry from ordinary PC mode.

## Passive observation is ready for a later GM5 connection

The [macOS cached-descriptor reader](../tools/gm5_usb_descriptors_macos.c) now has
two additional filters:

- `service`: Panasonic VID `04da`, historical service candidate PID `2370`.
- `panasonic`: VID `04da` with any PID, requiring exactly one matching device.
  This can reveal a different service identity without assuming the GH2 PID.

Both use the same cached-descriptor API as the previous observations. They do
not open the device exclusively, detach its driver, send control/bulk requests
or change modes. The output explicitly leaves model identity unconfirmed; USB
IDs alone cannot establish the model.

```sh
clang -Wall -Wextra -Werror -Wno-deprecated-declarations tools/gm5_usb_descriptors_macos.c -framework IOKit -framework CoreFoundation -o work/gm5-usb-descriptors-service
work/gm5-usb-descriptors-service panasonic
```

The updated reader compiled with warnings treated as errors. Only its invalid-
argument path was run during verification; no new device enumeration or camera
request was needed. The camera remained unavailable during this study.

Reproduce the offline native checks with the retained firmware, manual and FZ30
inputs, using a fresh output path:

```sh
python3 tools/gh2_usb_service_verify.py work/legacy-control/GH2__V12.body.decoded.bin --out work/gh2-service-sequence-new.json
```

The immediate missing evidence is **GM5's USB identity/configuration while in
its own documented service state**. The traced GH2 memory readers remain useful
comparison targets; no GM5 plaintext, decryption key or native crop patch has
been obtained.
