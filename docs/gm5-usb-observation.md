# GM5 USB observation — 2026-11-05

The owner's camera was observed through its real USB connection in both **PC**
and **PictBridge (PTP)** modes. The standard PTP `GetDeviceInfo` operation
succeeded and identified **Panasonic DMC-GM5, device version 1.1**.
No firmware or CPU-memory dump has been obtained.

The [sanitized evidence](../evidence/gm5-usb-pc-ptp.json) contains configuration
descriptor bytes, supported operations, response status and hashes. Original
captures remain under the ignored `captures/` directory; their device identifiers
are omitted from the public report.

## PC mode: SD-card storage

The connected device enumerated as **VID `04da`, PID `2372`**, USB 2.0, with
`bcdDevice=0x0110`. macOS attached its mass-storage driver and mounted the
15,931,539,456-byte card, whose partition uses FAT32.

Its sole advertised configuration has one interface and one alternate setting:

| Descriptor | Observed value |
| --- | --- |
| Interface number / alternate | `0` / `0` |
| Class / subclass / protocol | `08` / `06` / `50`: mass storage, SCSI transparent, bulk-only |
| Bulk OUT | Endpoint `0x01`, 512-byte maximum packet |
| Bulk IN | Endpoint `0x82`, 512-byte maximum packet |

No additional vendor interface or alternate interface setting is advertised in
this configuration. The mounted storage is the card; it is not a view of the
camera's internal NOR firmware.

The initial inspection used macOS's registry and cached configuration descriptor
API. It did not open the USB device exclusively, detach its driver, reset the
camera or send a bulk/maintenance packet. Directory entries on the card were
inspected; no photograph download was invoked by the tools. Before the owner
changed USB modes, the mounted camera disk was identified again and safely
ejected with `diskutil`.

## PictBridge: an actual standard camera query

After the owner reconnected and selected PictBridge, the GM5 enumerated as
**VID `04da`, PID `2374`**. Its single interface changes to class/subclass/protocol
`06` / `01` / `01`, with the same two 512-byte bulk endpoints and an additional
interrupt IN endpoint `0x83`, maximum packet eight bytes.

The probe used Apple's
[ImageCaptureCore PTP pass-through API](https://developer.apple.com/documentation/imagecapturecore/iccameradevice/requestsendptpcommand(_:outdata:sendcommanddelegate:didsendcommand:contextinfo:)).
Its device browser was explicitly restricted to **local cameras**, and the probe
accepted only USB VID/PID `04da:2374` with the GM5 name. No LAN discovery was
requested. The framework managed the normal device/session traffic; the only
explicit pass-through operation was **`0x1001 GetDeviceInfo`**.

The camera returned a 199-byte DeviceInfo dataset and a 12-byte response with
status **`0x2001` (OK)**. All dataset fields were consumed exactly. The response
transaction ID was 13, assigned through the framework's session rather than
matching the initial command buffer's ID. The framework session closed after
the query.

The result advertises these sixteen standard operation codes:

```text
1001 1002 1003 1004 1005 1006 1007 1008
1009 100a 100c 100d 1014 1015 1016 101b
```

They cover device/session information, media transfer and device-property
operations. The returned list contains **no vendor operation code** and no
advertised firmware-memory reader. It lists device properties `0xd406` and
`0xd407`, four event codes, six image/object formats and no capture formats.
The meanings of standard codes can be checked against
[libgphoto2's PTP definitions](https://github.com/gphoto/libgphoto2/blob/master/camlibs/ptp2/ptp.h).
Advertised write operations were not invoked.

This is a limited negative finding for the normal PictBridge interface. It
does not rule out unadvertised operations or a separate service mode. In
particular, the [GH2 binary readers](gh2-debug-tools.md) are not established as
PTP operations or GM5-compatible commands; none was sent to this camera.

## Reproduce the observations

The macOS descriptor reader has explicit PC and PTP targets and uses cached
descriptors without claiming the storage interface:

```sh
clang -Wall -Wextra -Wno-deprecated-declarations tools/gm5_usb_descriptors_macos.c -framework IOKit -framework CoreFoundation -o work/gm5-usb-descriptors
work/gm5-usb-descriptors
work/gm5-usb-descriptors ptp
```

Run the matching command for the camera's current mode. The standard query
requires a connected GM5 in PictBridge mode and a fresh, empty output directory:

```sh
clang -fobjc-arc -Wall -Wextra tools/gm5_ptp_info_macos.m -framework Foundation -framework ImageCaptureCore -o work/gm5-ptp-info
mkdir captures/gm5-ptp-info-new
work/gm5-ptp-info captures/gm5-ptp-info-new
```

The [offline parser](../tools/ptp_device_info.py) needs no connected camera:

```sh
python3 tools/ptp_device_info.py captures/gm5-usb-ptp-20261105T050236Z/device-info/get-device-info-data.bin --response captures/gm5-usb-ptp-20261105T050236Z/device-info/get-device-info-response.bin --out work/gm5-device-info-new.json
python3 -m unittest discover -s tests -p test_ptp_device_info.py -v
```

Six socket-free tests cover wire decoding, serial omission, every truncation
boundary, invalid strings, excessive counts, trailing bytes and response errors.
The native probes compiled without warnings under the installed SDK. The
post-capture response-validation addition was compiled and checked against the
saved response; it did not require another camera query.

The next access question is how GM5 enters its maintenance protocol, including
whether a different USB identity/interface appears. The normal PC/PTP baseline
is now measured; the service transition remains unverified.
The subsequent [offline GH2 service-entry trace](gh2-usb-maintenance-entry.md)
reproduces both measured configuration descriptors and identifies a distinct
GH2 vendor descriptor for comparison. No additional live GM5 query was needed.
The [service-sequence follow-up](gh2-service-sequence.md) adds passive `service`
and `panasonic` filters to the descriptor reader. The tool hashes in the original
observation record describe the earlier source revision; the retained capture
source files preserve that revision. No new enumeration is recorded here.
The [PTP dispatch follow-up](gh2-ptp-dispatch.md) also finds the complete measured
sixteen-operation list in GH2's plaintext and traces its table consumer. This
does not establish identical GM5 handlers or rule out flaws inside file readers.
