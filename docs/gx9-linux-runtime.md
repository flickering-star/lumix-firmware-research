# GX9 Linux runtime recovered through USB reads

RAM from the owner's DC-GX7MK3/GX9, reported firmware 1.4, contains a Linux boot
log and readable filesystem images. The running kernel is **Linux 3.18.18**,
built **2018-02-21 11:12:43 JST**, using GCC 4.8.5 from the
Buildroot 2017.02-svn196358 toolchain. These are captured runtime strings,
independent of the downloaded GX9 1.5 package. The
[runtime evidence](../evidence/gx9-linux-runtime.json) records addresses and hashes.

Panasonic's [official source listing](https://ospo.panasonic.com/oss/dsc/DC-GX9.html)
also lists Linux 3.18.18, Bash, glibc and other GNU userspace packages for GX9,
GX7MK3 and the associated model group. Its live download page currently requires
sign-in; the source listing alone was not treated as the running kernel version.

## Recovered architecture

The captured log identifies `panasonic,pvc02v-brb` and a 47 MiB Linux allocation
(`47104K`), with `41876K` available after the reported reservations. This
allocation does not establish the camera's total RAM capacity. The manufacturer
manual lists 8 Gbit of LP-DDR2 RAM, equivalent to 1 GiB.

The kernel command line uses two RAM-backed MTD regions:

| Region | Linux physical address | Length | USB service address validated at its header |
| --- | --- | --- | --- |
| `slram0`, root filesystem | `0x93100000` | 4 MiB | `0x83100000` |
| `slram1`, second filesystem | `0x93500000` | 9 MiB | `0x83500000` |

The log reports that the root is mounted read-only as SquashFS. Both headers
identify SquashFS 4.0 with LZO compression. These correspondences establish the
address relationship for the observed regions; they do not establish a universal
translation for every camera address.

Both complete mapped images have been acquired: 4 MiB and 9 MiB, with **947
entries** in total. Both passed their archive integrity tests. The inventory
includes directories, symbolic links and device nodes as well as 538 regular
files; all regular files have been extracted to their listed lengths.
The images and extracted files remain under `work/gx9-filesystems/`, with a
readable list in `gx9-file-list.txt`. The
[public inventory](../evidence/gx9-filesystem-inventory.json) records names,
types, sizes and acquisition hashes without redistributing file contents.

The first image contains Bash, glibc 2.23, SysV init scripts, Panasonic libraries and the
`iccdrv.ko` / `icsmdrv.ko` kernel modules. Its binaries are little-endian ARM
EABI5; the sampled userspace ELFs have flags `0x05000200` and use interpreter
`/lib/ld-linux.so.3`, indicating the
[soft-float calling ABI](https://github.com/ARM-software/abi-aa/blob/main/aaelf32/aaelf32.rst).
This is not a claim
that the ARM hardware lacks floating-point instructions.

## What replacing the Linux environment would require

Recovering the existing filesystems provides actual libraries and executables
for compatibility work. It does not demonstrate that a general distribution
will boot or preserve camera functions. The recovered proprietary kernel
modules have version magic `3.18.18 SMP mod_unload ARMv7`; existing libraries also
call custom character-device interfaces. The sampled `libicc.so` exports
`icc_open`, `icc_read` and `icc_write`; `libicsm.so` exports shared-memory
allocation and address helpers. Their code is available for offline analysis.

A useful first experiment would retain the existing kernel, modules, loader
and camera processes while testing a compatible shell or additional userspace.
An ARM distribution with a different calling ABI or C runtime cannot simply
replace those dependencies. A new kernel would also require compatible custom
driver interfaces and a verified boot method. No alternate userspace has been
executed and no firmware, filesystem or camera memory has been modified.

## Shell evidence

The recovered root contains `/bin/bash`. Its `inittab` starts a serial getty for
`ttyAMA`, and the live log reports that this device could not be opened.
This connects an actual startup setting to an observed failure; it does not
establish an available UART console or a network shell. No shell service has
been enabled. Neither inventory contains a standalone `sshd`, `dropbear`,
`telnetd` or `inetd` filename. That does not exclude shell functionality inside
another program. The second image contains Panasonic's `psm`, `net`, `nws`,
`ptpip`, `picm`, `link` and other programs. These are available for static
analysis alongside their supporting libraries.

Static analysis and bounded native-code emulation subsequently identified an
internal `NET_EVT_LINUX_CMD` dispatcher and command-output path in `psm`.
See the [command-handler report](gx9-linux-command.md). Its external entry is
unresolved; the emulator mocked `system`, files and IPC, and did not execute
commands on the camera.

The recovered complete DTB lists four PL011 UARTs, with the fourth marked
`okay`. No corresponding UART/PL011/8250 names appear in the recovered core
kernel symbol table, and no serial-driver filename was found in either
filesystem inventory. A DTB status alone therefore does not establish a usable
console. See the [component recovery report](gx9-recovered-components.md).

## Kernel symbols

The six-MiB captured interval `0x80200000..0x80800000` contains the kernel's
compressed symbol tables. Its native lookup-function literals locate those
tables. Offline expansion recovered **26,938 core kernel symbols**, with all
106 stream markers matching the saved marker table. Of 4,585 separate exported
symbols, 4,357 have matching names and addresses in the compressed tables; the
remaining 228 exports address writable data outside that table's text/rodata
scope. There are no address disagreements.

The [symbol decoder](../tools/gx9_kernel_symbols.py) and
[evidence](../evidence/gx9-kernel-symbols.json) preserve these checks. The full
private listing is `work/gx9-protocol-analysis/gx9-kallsyms-verified.txt`.
It names `slram_read`, MTD interfaces, AES routines and other actual kernel
functions. Their presence is not proof that they were invoked for firmware
updates or that physical flash is registered with Linux. Separately loaded
modules require their own symbol analysis, and boot-time init code may already
have been freed or reused even though its symbol names remain.

The [USB read report](gx9-memory-reads.md) describes the acquisition method.
Raw images, extracted proprietary files, device identifiers and complete
transfer captures remain under ignored `work/` directories.
