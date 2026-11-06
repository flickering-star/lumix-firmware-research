# Historical Panasonic service software: FZ30 static findings

A public FZ30 TATSUJIN package has now been acquired and unpacked. Its program
contains an EEPROM read routine and its documentation explicitly describes USB
maintenance mode. This provides a concrete older protocol reference, **not a
GM5-compatible memory reader**.

## Acquisition and extraction

Source: the [firsthand Lumix service-software page](https://www.inweb.ch/foto/lumixfun.html)
and its linked [FZ30 archive](https://www.inweb.ch/foto/downloads/Dmc-fz30.exe.zip).
The archive is 4,303,322 bytes, SHA-256
`a686e01733a90c43a80fa91348ec15ffa3c9fce0de620b784c19cf17ab192fc9`.
It is a third-party mirror of historical software, not an authenticated current
Panasonic service download.

The ZIP contains a 4,548,273-byte Windows installer. Static inspection found an
InstallShield overlay with three filename-encoded records. Using the format
described by [ISx](https://github.com/lifenjoiner/ISx), those records were decoded
without executing the installer. The embedded MSI and its MSZip cabinet were
then unpacked with 7-Zip. Cabinet extraction completed without errors.

The resulting 26 files include `fz30.exe`, `mkeusb01.dll`, `mkeusb01.sys`,
`mkeusb01.inf`, `howto.pdf`, `usage.pdf`, calibration PDFs and configuration files.
`sys.cfg` identifies DMC-FZ30, version 1.00, copyright 2005. All inputs and outputs
remain under ignored `work/service-software/`. The
[evidence record](../evidence/fz30-service-software.json) contains their hashes.

No installer or extracted Windows program was run, no driver was installed, and
no camera was contacted.

## Documentation narrows the backup's meaning

`howto.pdf` pages 2–4 explicitly calls the connection **service mode / USB
maintenance mode**. Its backup section saves EEPROM data, and the menu description
separates EEPROM save/restore, EEPRAM/EEPROM editing and calibration functions.
`submenu.txt` makes the same distinctions.

The actual editor resource says `Buffer / EEPROM Read / Write`, with buffer and
ROM choices and `Update` versus `Adjust / Fix` selectors. Within this tool's
context, a label containing `ROM` does not establish executable program access.
The correspondence to the GM5 update's `eep_ow_*` / `eep_adjfix` names is a lead
for comparison, not a demonstrated shared protocol.

## USB and read-path evidence

The INF binds Panasonic vendor ID `04da` with product IDs `0904` and `2370`.
These are **old driver bindings**, not IDs observed from the owner's GM5. The DLL
exports `open_dev`, `open_file`, bulk-read/write preparation and size/status
helpers. It uses Windows `DeviceIoControl`; this is not a network service.

Static disassembly of the FZ30 host program identified:

| PE virtual address | Observation |
| --- | --- |
| `0x40d110` | Read wrapper identified by its `Busy! Read EEPROM` branch |
| `0x40d173` | Builds a three-byte argument: low address byte, high address byte, selector |
| `0x40d196` | Passes type `0x08` and operation `0x38` to the request helper |
| `0x40cdbc` | Read request setup and retry/response path |
| `0x40c6e4` | Shared request-buffer builder |
| `0x40c850` | Additive byte-checksum helper |

For that path, the reconstructed host buffer is 16 bytes. Its prefix is
`08 00 ff 38`, followed by the two address bytes and selector; remaining payload
bytes are zero-filled. Byte 14 contains the modulo-256 sum of bytes 1 through 13,
and byte 15 is zero. The code subsequently passes the buffer to its USB write
path. This is static reconstruction, **not a captured/validated transaction**.
The retained disassemblies include the surrounding instructions and have hashes
in the evidence record.

The limited address field plus selector may refer to calibration records or
banked storage. Neither arbitrary CPU addresses nor the main program region has
been shown accessible. A Windows IOCTL value is a driver API, not an on-camera
opcode; the two should not be confused.

Further [named-handler tracing](offline-consumer-findings.md) connects ROM mode
to operation `0x38`, buffer mode to `0x35`, and the update/fixed selectors to
`0x10`/`0x20`. A bulk read uses `0x3e`. These are static FZ30 results; GM5 support
and arbitrary program-memory access remain unverified.

The [GH2 service-sequence comparison](gh2-service-sequence.md) now traces the
DLL's `preBulkWrite_CZ30` and `preBulkRead_CZ30` through the driver into vendor USB
request zero, using index zero/one. GH2 has corresponding camera-side preparation
branches after vendor mode is selected. No driver was installed or executed.

## What this enables next

A GM5 adjustment package or an existing trace of its backup can now be compared
against concrete names, framing and read semantics. The useful questions are
whether the newer tool retains this protocol, expands its addressing, or adds
program-area operations. Another model's packet should not be replayed merely
because the vendor or a UI label matches.

This work improves the service-software lead while reinforcing the distinction
between a calibration backup and a full executable dump. The
[GM5 manual](service-manual-findings.md) leaves that backup's extent unresolved.
