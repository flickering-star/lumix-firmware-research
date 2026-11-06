# GM5 service manual: firmware-access findings

The uploaded manual gives a stronger software lead: **page 53 explicitly describes
backing up IC6003 data when the adjustment software can communicate with the
camera**. The address range and output format are omitted. It therefore supports
investigating the service software/protocol, without establishing that the
operation exports executable firmware or an encryption key.

The flash diagram also establishes a **16-bit parallel NOR interface**, making a
hardware dump a specific fallback. No debug-console entry or memory-dump command
was identified in this manual.

## Input and coverage

- Source: [GM5 service-manual record](../evidence/gm5-service-manual-source.json);
  the locally supplied PDF is excluded from the release tree.
- Panasonic order number: `DSC1411019CE`, copyright 2014; 62 pages.
- Size: 8,586,793 bytes.
- SHA-256: `8b517daaaaad766987180fc4dc8fe13e3b7a0e31cdec848a471c73f09ce3a8de`.
- Git blob SHA-1: `0d23448e51264230701e59488bd3a4ec89b54c51`, matching the
  uploaded file at repository commit `0d4474a1948c9fc2c317ccb97e5c519820962271`.

Text was extracted from all 62 pages using macOS PDFKit. Key tables and diagrams
on pages 28, 36, 38, 43, 53, 58, 60 and 62 were also inspected as rendered images.
The final seven PDF pages have rotation metadata; the inspected renders account
for this. Some tables are not captured in extracted text, so text searching alone
is insufficient. Local extraction, rendered pages and a flash-bus detail are in
`work/gm5-manual/`; the [evidence record](../evidence/gm5-service-manual-findings.json)
records hashes and the limits of each conclusion.

Page numbers below are the manual's printed numbers, which match the PDF page
indices counted from one.

## 1. Adjustment software can back up flash data — scope unresolved

**Page 53, section 10.1, note 2:** for replacement of a working main board, the
technician first uses the adjustment software's communication with the camera to
back up IC6003 data, then restores the backup and performs body adjustment.

This is the strongest documented software-access lead so far. However:

- **Page 8, section 3.3.1.2** describes the related preservation step as an
  **EEPROM data backup** before main-board or flash replacement.
- **Page 28's error table** distinguishes flash **Data Area** failures from
  **Program Area** firmware-update failures.
- Neither page 8 nor page 53 provides a byte count, memory range, file format,
  command, transport or software version for the backup.

Consequently, this may be the same limited calibration/settings data already
available through the service menu. A full executable backup has not been proven.
The subsequently supplied [GM1 service export](settings-backup-findings.md)
represents 48 KiB of update/fixed-adjustment data and supplies a concrete format
reference; it does not establish the GM5 adjustment tool's output extent.
The useful next object is a **GM5-compatible adjustment package and its driver,
model profile and bundled help**, rather than a settings file whose name contains
"ROM".

Offline analysis of such a package should determine:

1. Which device/interface it opens, including USB descriptors and any service
   initialization or access sequence.
2. Whether backup requests include addresses and lengths or select fixed
   calibration records; distinguish reads from write/erase/adjust operations.
3. Whether returned bytes cover the program region, are plaintext, or are another
   encoded container. Identify integrity checks and any included update helper.

No service software was installed or executed, and no camera request was sent.
The manual does not identify the GM5 transport, so **USB remains a candidate**,
not a confirmed implementation of this backup path.

### Historical software names and a concrete reference

Panasonic's earlier [TZ30/ZS20 service manual](https://www.csportal.panasonic-la.com/descargaspla/PLA/DIGITALES/CAMARAS/ALTO%20ZOOM/DMC-ZS20PU/DOCUMENTO/MANUAL%20DE%20SERVICIO/ZS20_Manual%20de%20Servicio.pdf)
names **DIAS — DSC Integrated Assist Software**, directs technicians to the
TSN support system (pages 11 and 49), and relates it to the earlier **TATSUJIN**
tools (page 50). This supplies search names; it does not prove the GM5 uses the
same package, command set or driver.

A [firsthand account of older FZ-series Tatsujin software](https://www.inweb.ch/foto/lumixfun.html)
identifies model-specific executables, bundled `HowTo.pdf` / `Usage.Pdf`, and
`Mkeusb01.inf` / `Mkeusb01.sys` for a PV-DC3000 USB driver. That site links older
FZ4/FZ5 and FZ30 archives. The FZ30 package has now been
[acquired and statically inspected](service-software-findings.md), including its
USB maintenance-mode instructions and EEPROM-read framing. It is an **older
protocol reference**, not established GM5-compatible software.
A model-specific GM5 tool/help file is preferable to transferring an older
camera's commands or driver binding to this body.

## 2. IC6003: 32 MiB parallel NOR, with a documented bus

**Pages 56 and 58** identify IC6003 as 256-Mbit NOR flash: 33,554,432 bytes.
**Page 58** explicitly shows `DQ0..DQ15`, `A0..A23`, `WE#`, `OE#`, `CE#` and
`RST#`. The sixteen data lines and twenty-four word-address lines are consistent
with 16,777,216 words of two bytes each. The address interpretation is an inference
from that bus and capacity; no CPU memory-map base is supplied.

The following endpoint labels and control connections were checked visually in
the diagram. Endpoint rows summarize bus ranges, not the intervening ball map.

| IC6003 signal | Flash ball shown | IC6001/Venus signal | Venus ball shown |
| --- | --- | --- | --- |
| `DQ0` | `G2` | `CPUD16` | `R1` |
| `DQ7` | `G7` | `CPUD23` | `P4` |
| `DQ8` | `H2` | `GPIO63` | `N3` |
| `DQ15` | `F7` | `GPIO70` | `K2` |
| `WE#` | `A5` | `CPUWE2B` | `T3` |
| `OE#` | `F2` | `CPUREB` | `T2` |
| `CE#` | `F1` | `FROM CS` | `T1` |
| `A0` | `E1` | `GPIO71` | `K3` |
| `A23` | `B5` | `GPIO94` | `C1` |

`RST#` is marked at flash ball `B4`. These are package-coordinate labels, not a
ready-to-use connector pinout. The PDF does not give the flash's manufacturer,
part number, full ball map or supply-voltage specification. It also does not
document a CPU reset/bus-isolation arrangement for an external reader.

This changes the hardware plan: investigate a **parallel-NOR read**, with the
actual chip identified first. A standard SPI-flash clip or eMMC reader is not a
match for the shown bus. The actual part marking or a component-level schematic
and parts list would resolve the next questions. Readback would still have to
establish which regions are plaintext; no at-rest encryption conclusion follows
from the drawing.

## 3. The TXD/RXD labels are part of the flash accessory interface

**Page 62** lists `TXD` on FP9009 pin 14 and `RXD` on pin 13. Following those
signals into **page 60, Lens/Hot Shoe Block Diagram**, leads to the hot-shoe pin
base (`STTXD` and `STRXD`, with `RL7955` and `RL7956`) and external-strobe
circuitry. `STX`, `TTL(CNDS)` and external-flash power share this assembly.

These labels do not identify an engineering UART. No console protocol, baud
rate, voltage specification or console routing is documented for them. They should
not be selected as a debug-port connection on the strength of their names.
The hot-shoe drawing is useful for eliminating that false lead; any reassignment
of these GPIOs for diagnostics would need separate firmware or hardware evidence.

## 4. Service mode and other interfaces

- **Pages 27–29:** the documented service function is error history and camera
  information. This does not establish a second engineering GUI or a memory reader.
  The PDF does not document `ROM BACKUP` as a full-image export or an SD script
  loader. That omission does not establish absence of undocumented functions.
- **Page 35:** the Wi-Fi service section concerns settings reset and fault
  isolation, not a shell or additional command API.
- **Pages 59 and 62:** `JK2001` carries normal USB `D+`, `D-`, cable detection
  and AV signals. This is a physical transport candidate; no vendor request,
  service endpoint or memory-read protocol is specified.
- **Pages 56 and 8:** Venus IC6001 uses package-on-package construction and
  includes 2-Gbit LP-DDR2 RAM (256 MiB). Neither processor ISA nor runtime
  memory-map base is identified.
- **Pages 59 and 62:** the Wi-Fi module is connected over SDIO. This does not
  establish whether camera HTTP handlers run on the module or Venus, or whether
  control of the module would provide access to the main processor's memory.
- **Pages 36 and 38:** the listed fixtures are optical/mechanical aids and flex
  extension cables. They do not supply a named flash programmer or console adapter.
- **Pages 43 and 62:** board removal and connector positions are documented,
  but there is no component-level main-board schematic, full parts list or
  verified JTAG/debug-pad map in this PDF.

## What to pursue next

1. **Service software:** obtain the GM5 adjustment package/help or an existing
   capture of its backup operation. Resolve whether it can read program addresses.
2. **Wi-Fi:** keep the Android Image App capture plan; it provides independent
   evidence of actual GM5 commands and menus, without assuming diagnostic access.
3. **Firmware sample:** the official update is now acquired and its
   [container verified](gm5-v11-analysis.md). Compare recovered data against its
   encoded components and trace the payload-decoding consumer.
4. **Hardware fallback:** identify IC6003 by marking/parts data, then establish a
   suitable parallel-NOR acquisition setup. Unlabeled debug pads remain a separate
   board-level investigation.

The manual has narrowed the search; it has not produced a plaintext image,
decryption key, debug-console activation sequence or flashable modification.
