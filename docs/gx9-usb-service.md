# GX9 service USB research

The owner's Japanese DC-GX7MK3/GX9, reported firmware 1.4, has a measured
Windows WinUSB service interface. It supports indexed buffer reads, 1 KiB
address-based reads and a tested absolute two-byte read. Around 48.6 MiB of
distinct address ranges have been acquired. No GX9 write was sent during this
published investigation.

The work progressed from registry/interface inspection, through rejected
fixed-area reads, to verified RAM acquisition. These reports separate those
milestones and preserve their measured limits:

- [Windows connection and initial service replies](gx9-windows-service-connection.md)
- [Memory reads, acquired ranges and failed legacy address](gx9-memory-reads.md)
- [Full 1.4/1.5 decryption, key recovery and ARM component comparisons](gx9-firmware-decryption.md)
- [Initial four-component recovery and complete filesystem contents](gx9-recovered-components.md)
- [Linux runtime and 26,938 recovered kernel symbols](gx9-linux-runtime.md)
- [Internal Linux command runner, verified with mocked native emulation](gx9-linux-command.md)
- [Windows-local USB capture](gx9-windows-local-capture.md)

## Entry and primary references

Panasonic service manual DSC1803005CE, section 6.1 (page 33), describes temporary
service entry with the camera set to P, a charged battery and a card inserted:
hold Playback, AF/AE LOCK and Right while switching it on. MENU/SET, AF/AE LOCK
and Left cycles diagnostics. Power-off exits the temporary state.
[Manufacturer manual, hosted copy](https://www.scribd.com/document/609396269/panasonic-service-manual-gx9).

The separate region/Initial Settings procedure was not performed in these
checks. The manual lists 8 Gbit of LP-DDR2 RAM, equivalent to 1 GiB. Its overall
diagram labels IP6001 a 1 Gbit NOR device, while its detailed video/audio diagram
labels it NAND. Both flash labels imply 128 MiB; the type conflict remains
unresolved and does not supply a CPU address map.

The [official GX9 1.5 archive](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gx9.html)
was downloaded and inventoried. The package has 36 component records, 35
nonempty. All 35 now decode with complete expected-hash matches, using the
key found in captured ARM memory. An archived official 1.4 package also decodes
fully. Five additional RAM-captured postboot images match 1.4 exactly; the
main image's code after offset `0xd0000` also matches 1.4 exactly. The camera
continues to report 1.4. The Linux components reused in 1.5 explain the earlier
matches without an update.

## Current boundary

An externally reachable shell and an alternate firmware-installation path
remain unverified. Native-code analysis identified an internal
`NET_EVT_LINUX_CMD` command/output path and its ICC-to-local-socket event route,
but no external USB or Wi-Fi request has reached it. The reversible RAM-padding
write control was interrupted before a write was sent. Complete decoded
firmware now enables direct analysis of the remaining USB and update handlers.

The old-model program address `0x40000000` froze this GX9 when tested through
the block reader. The owner reconnected it, and known RAM controls passed
again. The failed address has not been repeated. Related-model addresses and
write handlers are not established GX9 targets.

The release contains source, documentation and summarized evidence. Raw dumps,
extracted executables, compiled tools and private connection material remain
outside the published repository.
