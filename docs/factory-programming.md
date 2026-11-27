# Manufacturing, factory loaders and first programming

The exact initial programming method used on Panasonic's GM1/GM5 assembly line
is **not established**. Generic production methods must be kept separate from
the software paths found in these particular cameras.

## What a manufacturer can do

| Method | How code reaches the board | What must already work |
| --- | --- | --- |
| Program the flash before soldering | A programming house or factory loads the loose memory chip in a socket | No camera firmware is needed |
| Program after soldering through a fixture | Spring contacts touch board test pads; a programmer accesses the memory or runs a flash loader through the processor's debug interface | Suitable wiring and access to the chip or processor |
| Use a processor ROM loader | A mode strap/pad selects code built into the processor, which receives a RAM flash loader over a supported interface such as USB/UART | The processor's built-in loader and its documented protocol |
| Run an existing updater or factory loader | Existing camera code reads an image from a card or communication interface and writes flash | Enough valid firmware to start and reach that loader |

These are general mechanisms, not four demonstrated GM1/GM5 features. Production
can combine them: load a small bootstrap first, then program a complete image and
perform adjustments after assembly. We have not established that particular
sequence for Panasonic.

[SEGGER's programming documentation](https://kb.segger.com/In-system_programming)
describes programming before assembly and programming soldered devices through
the processor, including parallel NOR. [Microchip's memory programming overview](https://www.microchip.com/en-us/about/media-center/videos/2jVX-Gy5E9g)
independently describes supplying preprogrammed memory. These are vendor
references for general methods; neither identifies the Panasonic production line.
For a concrete example of the ROM/USB/serial approach on a different processor
family, see [Microchip's SAM-BA programmer](https://www.microchip.com/en-us/development-tool/sam-ba-in-system-programmer).

A completely blank external flash cannot execute its own normal updater.
Executable code must come from preprogrammed memory, processor ROM, or a
programmer/debugger first. This is why identifying a camera's running service
interface does not establish a blank-board recovery interface.

## New GM1 evidence: an AHX loader reaches NOR programming code

The complete physical GM1 main program contains `A:\GM1.AHX` at `0x403945dc`
and `A:\GM1E.AHX` at `0x403945e7`. These are used by native code, rather than
being isolated filename strings. The [reproducible evidence](../evidence/gm1-factory-programming.json)
pins both complete program hashes, nine instruction regions and ten call links.

- Startup calls job `0x40158fe8` through `0x4005000a` and `0x40050026` with
  different mode values and predicates. This does not supply a verified physical
  button/pad procedure.
- The AHX branch tries `GM1.AHX`, then `GM1E.AHX`, using reader `0x4024f40f`
  and RAM staging base `0xb3000000`. The successful fallback selects mode three.
- The reader requires at least `0x600010` file bytes. It consumes 48-character
  text records and advances sixteen decoded bytes per data record.
- Parser `0x4024f63f` recognizes `S3`, decodes the address, checks it against
  the expected sequential offset, writes data to the staging buffer and checks
  the additive one's-complement checksum and CRLF. Complete termination and
  image-acceptance conditions remain unresolved.
- Call `0x40159204` reaches secondary routine `0x7bd23171`, then programming
  core `0x7bd235f9`. A hardware-dependent branch calls erase helper
  `0x7bd1b0b0` and program helper `0x7bd1b116`. These issue sixteen-bit NOR
  command/data writes and poll status. Command addresses include `0x80000aaa`
  and `0x80000554`; a core branch programs from staging `0xb3000000` toward
  `0x80000000`. Its relationship to the USB read alias has not been measured.

This establishes an additional **factory/recovery-style SD image programming
path in GM1 software**. It does not establish that this was used for the first
programming step in manufacturing or that it accepts an arbitrary image.
This path itself lives in the existing flash firmware, so it requires enough
working code to reach it. That initial GM1 investigation generated no AHX file
and attempted no physical activation or flash write.

The later [GM1S AHX experiment](gm1s-ahx-policy.md) is a separate physical
result: the owner activated its SD updater and installed a full same-body
image with one policy byte changed. Before/after read-only USB inspection
confirms flash and RAM policy `1 → 0`, with only that byte changed in the
complete flash policy page. The owner reports LED activity followed by an
automatic restart. A complete post-update flash readback and recovery from
damaged startup firmware have not been demonstrated.

The owner subsequently [restored a bricked GM5 using AHX](gm5-ahx-recovery.md)
from a complete same-body backup with one policy byte changed. The input file
and completed SD copy were verified; the successful restoration is owner-reported.
No post-recovery GM5 policy/calibration or full-flash readback has been performed.

**Make and verify a complete same-body backup before any firmware modification.**
The GM1/GM5 full backup is 32 MiB and includes identity, settings and calibration
that an official update BIN cannot replace. Keep an untouched copy off the SD card.
Stock `GM5.AHX` selects full-image mode 0 and rewrites the final data sectors.
Mode 1 skips the final 384 KiB; mode 2 writes only that tail. These are internal
writer choices, not modes selected by shortening or editing the AHX file.
`GM5E.AHX` uses extended fallback mode 3 and does not exclude calibration.
The linked recovery guide explains the caller/core distinction and live-settings
preservation. AHX is a firmware-resident recovery path, not processor-ROM recovery.

The earlier [GH2 AHX investigation](gh2-sd-factory-inputs.md) established a
similar separate image-input path. The GM1 finding above comes from GM1 bytes,
not an assumption of compatibility with GH2.

Reproduce the offline checks with intact local captures and a fresh output:

```sh
python3 tools/gm1_factory_verify.py captures/gm1-usb-resume-3atwz8co/result/program-main.bin captures/gm1-usb-resume-fveg1az5/result/program2.bin --out work/gm1-factory-recheck.json
```

The verifier checks source identity, disassembly annotations, instruction
continuity, relative calls and filenames. The behavioral interpretation is
manual analysis; this is not emulation or hardware validation of the writer.

## What remains unknown for blank-board recovery and USB

The [GM5 service manual](service-manual-findings.md) identifies IC6003 as
32 MiB of parallel NOR with a sixteen-bit data bus. It does not identify a
factory programming connector, processor ROM protocol, debug-pad map, or the
method used to load blank boards. Its TXD/RXD hot-shoe labels are not a verified
debug UART.

The [live GM1 USB work](gm1-usb-service.md) has demonstrated program-memory
**reads**, including complete main and secondary programs. It has not
demonstrated a USB flash writer or a processor-ROM USB boot mode. Similarity to
GH2's service protocol alone cannot establish either.

Panasonic's [consumer update instructions](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/step2.html)
describe an SD-card update on an already functioning camera. That documents the
user process, not the factory's first programming method. Finding a separate
loader gives another installation route. One same-body GM5 AHX recovery is now
owner-confirmed; manufacturing methods, recovery with an unusable AHX entry and
independent processor-ROM recovery remain unestablished.
