# GX9 service USB connection through Windows

On 2026-11-08 the owner's connected camera identified itself as **DC-GX7MK3**
(the Japanese GX9 model). Windows reported a working **WinUSB** driver,
device status `OK` and problem code zero. Raw device instance IDs stay private.

The [connection evidence](../evidence/gx9-windows-service-connection.json)
establishes that the USB service interface opens, can be claimed, accepts
transfers and returns structured service replies. At this initial milestone,
a successful settings or program-memory read had not been established.
**Later checks demonstrated indexed buffer reads through `0x35`; see the
[memory-read investigation](gx9-memory-reads.md) for current results.**

## Measured interface

| Field | Observed value |
| --- | --- |
| USB VID / PID | `04da:2370` |
| Configuration / interface / alternate | `1 / 0 / 0` |
| Interface class / subclass / protocol | `ff / a0 / b0` |
| Bulk OUT | `0x01`, maximum packet 512 bytes |
| Bulk IN | `0x82`, maximum packet 512 bytes |
| Interrupt IN | `0x83`, maximum packet 64 bytes |
| Configuration descriptor length | 39 bytes |

The existing official libusb DLL matched its pinned SHA-256,
`7cbf37e76dae9c840c7e8dbf7348ee8897dcc86c8ba45e46ada60b89411569f7`.
Opening and claiming the interface both succeeded. The inspection did not change
the driver, USB configuration or camera settings.

## Read-request results

Two separate bounded checks used the inherited operation `0x38`, candidate
fixed area `0x20`, at word indices `0x3f80` and `0`. Each run sent one request
and closed the interface after its response failed the expected word format.
The second check tested the lowest index independently of the first sample's
position near the end of the older models' area.

Both exchanges completed the transfer-preparation requests and bulk transfers.
Both returned type byte `08` and this sixteen-byte frame:

```text
08 00 ff 01 03 00 00 00 00 00 00 00 00 00 03 00
```

The frame's additive checksum is valid. It is an error-form reply with operation
byte `01` and status byte `03`, rather than the expected word reply `36`.
**The meaning of status `03` is unverified.** The identical result at the two
indices does not distinguish command support, area selection or camera-state
requirements. No returned bytes were treated as calibration or firmware data.

This resolves the previous Windows driver/access obstacle in the
[earlier GX9 report](gx9-usb-service.md). It leaves GX9-specific command
semantics and memory access unresolved. No program-relative or absolute-memory
request, camera memory write, flash operation, reset or configuration change
was performed in these checks.
