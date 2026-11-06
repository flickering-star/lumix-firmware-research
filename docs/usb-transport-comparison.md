# USB maintenance and SCSI are separate command layers

Further GH2 tracing resolves an important transport question: the firmware's
memory-read operation `0x70` is **not a direct SCSI command**. Its vendor SCSI
paths also require a saved service state. The reviewed code therefore does not
provide a normal-PC-mode firmware-dump method. Corresponding GM5 behavior remains
unverified.

Official newer source releases supply a useful comparison, but do not contain
the missing GM5 implementation or a usable remote memory reader.

## GH2's vendor SCSI gate

The source is the same verified GH2 1.2 plaintext used in the
[maintenance-interface investigation](gh2-usb-maintenance-entry.md).
The [new evidence](../evidence/gh2-scsi-transport.json) and
[offline verifier](../tools/gh2_scsi_verify.py) retain native regions, call links,
the complete SCSI dispatch table and selected table-lookup controls.

The CBW consumer at `0x401ea3ea` copies three four-byte fields, three single-byte
fields and a sixteen-byte CDB. The latter lands at `0x744dd21c`. Dispatcher
`0x401ea54b` uses the CDB's first byte, adds one and searches a 32-slot table at
`0x407f1cf0`.

| SCSI CDB opcode | Branch | Observed prerequisite / destination |
| --- | --- | --- |
| `0xe2` | `0x401ea592` | Saved mode `0x744dd1f2` must equal 2 or 4 before calling `0x401ebbbd` |
| `0xe4` | `0x401ea592` | Same branch and prerequisite |
| `0xe5` | `0x401ea5ed` | Saved mode must equal 2 before calling `0x401f0741` |
| `0x70`, `0x9b` | No entry | These values belong to the separate raw maintenance dispatcher |

The failed vendor gates reach `0x401ea61d`, which sets sense fields
`5 / 0x20 / 0`: a command-rejection path. In the `0xe5` helper, CDB byte two
selects suboperations `0x3e` or `0x3d`. This is another protocol layer, not an
alias that makes every raw maintenance operation available as a CDB.

### The saved state is not an unlock supplied by the host

At `0x401e764d`, the bulk-OUT path first requires descriptor mode two. It then
copies that mode into `0x744dd1f2` at `0x401e76b4`, saves the previous phase and
temporarily selects storage framing. The restore helpers at `0x401e6b40` and
`0x401f8f1a` use the saved state to return to maintenance phase three.

The verifier inventories all eight occurrences of the four reviewed absolute
byte-store encodings targeting `0x744dd1f2` in the main program range. The
inspected nonzero store is this already-service-mode save; the other inspected
stores clear the value during setup or restoration. Other instruction forms,
computed destinations and aliases are not excluded. This is a bounded static
inventory, not a whole-program proof that no other transition exists.

The result explains why mass-storage framing appears inside the service code.
It does not establish that sending vendor CDBs to an ordinary PC-mode camera
enables its maintenance readers. No CDB or maintenance packet was generated or
sent during this investigation.

## Comparison with actual Panasonic source releases

Both packages were acquired from Panasonic over certificate-verified HTTPS and
inspected as data. No kernel or driver was built, loaded or executed.
The [source evidence](../evidence/panasonic-usb-source-comparison.json) records
archive hashes, complete regular-file manifests, selected member hashes and
source-line anchors.

| Official package | Bytes | SHA-256 |
| --- | ---: | --- |
| [GH5 Linux 3.18.18](https://ospo.panasonic.com/oss/dsc/DC-GH5.html) | 127,563,916 | `f206feb1fb21a23a36a71e1fe0fb4aa5544cfce04fffeaebcf571db23d9aa494` |
| [S5M2 Ver1 Linux 4.19.124](https://ospo.panasonic.com/oss/dsc/DC-S5M2.html) | 165,739,116 | `617c2712db38aed13cd5b6e96890d759d1b215ad20768dddd716b8ceaebc7811` |

The complete GH5 archive has no `pvc_mass_storage.c` or matching header member.
Its inspected `f_mass_storage.c` implements ordinary storage commands. This
does not establish the behavior of proprietary code outside that release.

The S5M2 archive includes Panasonic's custom `pvc_mass_storage.c` and header.
That driver copies a received 31-byte CBW, including its sixteen-byte CDB, into
a structure delivered to local userspace through `PVCUSB_GET_DATA`. Other
ioctls provide data and status replies. Its local transfer-address fields are
not demonstrated remote memory-read commands. The userspace command consumer
is absent from this inspected driver.

`CurrentSerialNumber` increments per CBW and is checked against local ioctl
replies. It is a transfer-sequence counter, not a demonstrated camera-pairing
credential. Product-descriptor fields can be supplied through another ioctl;
source defaults do not prove a connected model's identity. The build option's
presence likewise does not prove runtime activation.

The public source mirror found under an S5 research folder is also a different
revision: its `pvc_mass_storage.c` is 82,835 bytes, while this official S5M2 copy
is 86,224 bytes, with different SHA-256 hashes. The mirror's README describes
S1R II source. Folder labels are therefore insufficient provenance for treating
that code as S5, GM5, or a common implementation.

## Consequence for GM5

The known GM5 PC connection is still an observed `08/06/50` storage interface;
PictBridge is an observed standard PTP interface. Neither observation establishes
the separate `ff/a0/b0` service interface or the raw maintenance readers found
in GH2. The first missing hardware observation remains GM5's descriptors in its
own documented temporary service state.

The source comparison also narrows the next offline target: a camera-side
command consumer or GM5-compatible adjustment executable/profile, rather than
generic USB host drivers or the newer kernel's CBW-forwarding code.

Reproduce the GH2 native checks using a fresh output path:

```sh
python3 tools/gh2_scsi_verify.py work/legacy-control/GH2__V12.body.decoded.bin --out work/gh2-scsi-check-new.json
```
