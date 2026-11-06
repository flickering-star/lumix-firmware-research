# GM5 flashing investigation

An accepted modified unsigned main-firmware installation path is now verified
on this GM5. Aspect-ratio work is deferred at the owner's request.

The [Japanese language unlock](gm5-region-lock.md) has now been installed in
normal mode according to the owner. English survives the reported manual off/on;
[short physical checks](../evidence/gm5-region-physical-proof.json) verify all
three patched ROM windows, English settings/UI and ROM/RAM policy zero. The
owner stopped the complete main readback; this installation has short-window
verification rather than a complete installed-image comparison.

**Pre-language baseline:** the [one-byte main policy-zero package](gm5-policy-zero-package.md)
was physically installed. Its [proof record](../evidence/gm5-policy-zero-physical-proof.json)
replays the service captures and verifies the complete 8 MiB main against the
exact candidate. Its only difference from the original main is byte
`0x406b1bdc: 1 → 0`. ROM and RAM both read zero after the owner's normal off/on
cycle, without any post-restart host policy write. Installed version words stay
`0x0111 / 0x0111`. Eight exact-package native controls and 73 repository tests
pass. Physical recovery and broader camera-function testing remain unvalidated.

The preceding unchanged-`program2` control produced owner-reported full progress
and automatic restart; its complete 3.375 MiB readback matched the backup.
That established preservation. The subsequent distinguishable policy change
provides the missing physical programming proof.

Earlier, the owner authorized the raised-version full official-payload
candidate with signature policy left at its default value, one. That attempt
showed about three seconds of progress and requested a manual off/on cycle.
The sampled main/updater windows stayed unchanged, consistent with validation
rejection. Its precise numeric camera error was not observed. That earlier
default-policy observation is distinct from the unchanged-program control.

**The complete 32 MiB mapped NOR backup is now acquired and packet-verified.**
After a battery replacement, three live anchors matched and acquisition resumed
from the saved 22,987,776-byte prefix. The [backup record](../evidence/gm5-flash-backup.json)
retains the complete hash, both capture verifications and four matching earlier
flash windows. A final read at that backup stage confirmed the RAM flag was one. The backup
sent no RAM or flash writes; the completed raw file is protected read-only.

The [offline AM33-2 emulator](gm5-emulator.md) passes 44 native controls on the
official build, including full unsigned and signed library decoding, plus three
initializer controls using this camera's installed Japanese programs. The
installed-build virtual policy patch changes only the intended initialized RAM
byte. The [virtual installation extension](gm5-virtual-installation.md) adds 23
native controls: it runs the installed decoder and post-decode job, writes all
eight components into a 32 MiB NOR model, verifies every output byte, and tests
failures/interruption and reloaded initializers. Its board/RTOS/cache assumptions
are explicit; full UI/file opening, final cleanup/restart and full boot remain
unmodeled. Language persistence is now the active follow-up; aspect-ratio work
remains deferred.

The earlier RAM experiment demonstrated **1 → 0 → 1**, including persistence of
zero across USB unplug/replug without a power cycle. It ended restored to one.
The initial physical tests stopped at the prompt; the later owner-authorized
default-policy control is recorded separately below.

**The official GM5 update is fully decoded.** All eight component SHA-256
fields match. The key was recovered from a small, live service-USB initializer
read; it is `f630c6cfad87f78031327ba55193fa4c`, at flash `0x4064b4cc`, copied
to RAM `0x70007950`. Cipher selector three is five-round AES-128-CBC, with
per-component IVs. See the [decoding report](../evidence/gm5-v11-decoded.json)
and [key-window result](../evidence/gm5-update-key-candidate.json).

The official GM5 directory's ECDSA P-256 signature also verifies with its own
public key, both independently and through LibreSSL. The
[signature evidence](../evidence/gm5-directory-signature.json) records the
signed directory and raw signature conventions. GM1's different key failed;
that historical cross-model comparison is preserved separately.

## The connected GM5

The owner connected a GM5 in service mode. Its registry identity is
`DMC-GM5`, `04da:2370`, interface `ff/a0/b0`. Sixteen framed settings replies
worked, but GM1's model-marker coordinates returned different data. That first
attempt stopped before program reads. Subsequent probes require the exact GM5
registry identity and repeat the retained thirty-two-byte control from this
body; that control is not mislabeled as a manufacturer/model marker.

Program-relative word reads recovered a sixty-four-byte native startup sample.
A separate 1 KiB block matched it, and a forward/reverse 8 KiB window matched
byte for byte. Startup identifies the main initializer
`0x40643b7c..0x4064b5b8 → 0x70000000`. The enclosing 32 KiB window supplied
one key among 32,753 byte-aligned candidates that reproduced all sixty-four
known program bytes. Full decoding then verified every official component.

The installed program differs from the official plaintext: twenty-five bytes
in the first 8 KiB, and 143 bytes in the 32 KiB initializer window. The key and
first sixty-four bytes agree. Two words at `0x400006a0/0x400006a2` are `0x0111`
on the camera and `0x0110` in the official payload; their complete meaning is
not yet assigned. Build-like metadata differs as well. The owner suggested the
Japanese locked-language variant as an explanation. That is plausible but is
not proven by these differences alone.

Panasonic's [Japanese download page](https://av.jpn.support.panasonic.com/support/dsc/download/fts/dl/gm5.html)
and [global page](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gm5.html)
both list `GM5__V11.zip` with the same archive byte count. This does not establish
that every installed regional build is byte-identical. Installation decisions
must use the connected body's native code and settings, not a blanket shift
from official addresses.

## Signed and unsigned updater branches

The official consumer has an unsigned-input branch: a zero first byte in the
inner marker skips signature/component-SHA verification when context offset
112 allows it. The job sets that allowance only when runtime byte
**`0x70a68490` is zero**. The official flash initializer stores one, disabling
that branch.

The installed updater window was acquired separately from flash
`0x4154e000..0x41552000`, linked as `0x7bd4e000..0x7bd52000`.
Its job starts at **`0x7bd4fb93`**, four bytes later than the official job,
and explicitly reads the same runtime address at `0x7bd4fb97`. It copies the
key through `0x7bd4fc97` and uses a different public-key-profile address,
`0x7be2a770`. A physical profile read locates its public key at `0x7be2a714`;
all sixty-four key bytes equal the official update verifier's key. Regional
build differences therefore do not supply a different signing key.

A separate physical startup-data read establishes that installed flash
`0x4064b5b8..0x406dd76c` is copied to RAM `0x70a01e6c`. This maps the flag's
source to **flash `0x406b1bdc`**. Its physical source byte and the initial live
RAM byte were both one. The RAM experiment below does not change that flash
initializer; a restart requires setting the volatile flag again.

## Demonstrated RAM control and USB transition

The installed USB dispatcher contains operation **`0x9c`**, table
`0x4061e494`, branch `0x4036ce71`, and handler `0x4036e086`. The handler assembles
an absolute address from request bytes 4–7 and a halfword from bytes 8–9.
Live USB state byte `0x702ff85d` was zero, selecting the direct halfword store.
The tool checks these native bytes, the exact device identity, mode and initial
word before writing only `0x70a68490`, with values zero or one.

The first [packet-verified experiment](../evidence/gm5-ram-signature-control.json)
read **1 → 0 → 1**. Only byte `0x90` in the 1 KiB control block changed, and
the restored block equaled the original in full. In a separate experiment,
[enable](../evidence/gm5-ram-enable-unsigned.json) read **1 → 0**; after the owner
unplugged/replugged USB while keeping the camera on, a new independent read
still returned zero. [Restore](../evidence/gm5-ram-restore-signed.json) then read
**0 → 1**. The [combined transition record](../evidence/gm5-usb-disconnect-test.json)
retains the captures and distinguishes the owner's physical action from the
measured memory values. The owner also reports that camera controls remain
usable while service USB is connected.

This establishes reversible control and continuity across that USB transition.
It does not yet establish acceptance of an unsigned SD image.

## When verification samples the flag

The installed main bridge calls updater `0x7bd4fb93` directly at `0x4023c19a`.
The job loads RAM flag `0x70a68490` at `0x7bd4fb97`, saves it on its stack at
`0x7bd4fba0`, and later initializes context+112 from that saved value at
`0x7bd4fc22..0x7bd4fc30`. The full decoder call at `0x7bd4fcd1` performs package
validation before the reviewed post-decode programming path. The package ECDSA
call is at `0x7bd4f1bb`, reached only on the signature-required branch.

Four additional [installed-build native controls](../evidence/gm5-update-policy-lifetime.json)
execute the actual sampling and allowance snippets. They show both initial
values saved correctly, then demonstrate that changing the global byte virtually
after sampling does not change the allowance computed from the saved value.
These controls do not simulate a CPU reset.

A real reset before a new update job would discard that stack/context and reload
the stock flag as one; an unsigned candidate would then be rejected unless the
flag were cleared again. The reviewed installation bridge invokes an ordinary
function call, not a separate rebooted verifier, but the complete physical
UI-to-installation transition has not yet been observed with allowance enabled.

A restart after successful programming is a separate boundary. It initializes
RAM from the installed image; the virtual one-byte ROM patch already demonstrates
initializing the policy to zero instead of one. This does not prove the new image
would boot. No separate boot-time authentication mechanism has been established
or ruled out, including possible checks outside the dumped NOR. Package-level
ECDSA validation must not be presented as proof that no other writing or boot
integrity check exists.

## Locally validated prompt-test packages

The [package report](../evidence/gm5-updater-prompt-package.json) pins the source,
builder, decoder, candidate hashes and every changed byte. Both variants retain
all eight encrypted payloads byte for byte, including the settings/calibration
components. Each actual candidate was decoded again with the recovered key;
all eight plaintext SHA-256 values match the unchanged directory. Outer CRC32,
duplicated header, component ranges and directory identity also pass.

| Variant | Container edits | Purpose |
| --- | --- | --- |
| `standard-version` | Inner marker byte `0x200` becomes zero; outer CRC32 recomputed: five changed bytes total | First, minimal unsigned-path eligibility test |
| `relaxed-version` | Same marker/CRC change, plus header flags at `0x20` and duplicate `0x2c0` change from four to zero: seven changed bytes total | Fallback for version/type eligibility checks |
| `advertised-0112` | Marker/CRC change, plus both advertised version halfwords at `0x1c` and duplicate `0x2bc` become `0x0112` | Test higher advertised version without changing program or other payload bytes |

The initial two variants leave version fields unchanged. The third changes only
container version fields; its program's built-in version remains stock. The inspected
header validator skips its version/type comparisons when the flags' low nibble
is zero; other eligibility checks remain possible. All signature bytes are
retained. A correction to the original report is material: the minimal
marker-only edits are outside the signed directory, so its directory signature
still verifies. Editing duplicated header flags or versions changes signed
input and invalidates that signature. Independent ECDSA and LibreSSL checks
confirm all three cases in the
[candidate signature record](../evidence/gm5-prompt-candidate-signatures.json).
Every candidate nevertheless selects the native zero-marker unsigned branch,
which requires RAM flag zero even when the retained signature is mathematically
valid.

Build fresh copies with:

```sh
python3 tools/gm5_prompt_package.py firmware/official-gm5-v11/GM5__V11.bin --out work/gm5-prompt-new
python3 tools/gm5_prompt_package.py firmware/official-gm5-v11/GM5__V11.bin --advertised-version 0x0112 --out work/gm5-prompt-version-new
```

The minimal candidate was written as the only root firmware file on the owner's
card, read back byte-identically, and the card ejected. The
[SD preparation record](../evidence/gm5-prompt-sd-preparation.json) records its
SHA-256 and volume identity. Existing card files were preserved.
The [second copy](../evidence/gm5-prompt-sd-preparation-2.json) followed a format
in the GM5, also with an identical readback. Both attempts inserted the card
while the camera remained on; startup with the card present is a distinct
procedure still to check. Neither attempt displayed an update prompt.

For the physical test, insert the card while the camera is off, start the
camera, then use `sh tools/run_gm5_ram_control.sh enable-unsigned` after service
USB reconnects. Verify its capture, unplug USB **without switching off**, and
enter Playback. Panasonic's [update procedure](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/step2.html)
specifies a charged battery, Playback entry and no USB/HDMI connection. Record
any rejection or confirmation screen. **Stop before selecting Yes or confirming
installation.** After canceling, reconnect and restore with
`sh tools/run_gm5_ram_control.sh restore-signed`, verifying the capture.

The [native path verifier](../tools/gm5_updater_verify.py) and
[installed path evidence](../evidence/gm5-updater-paths-installed.json) pin
twenty-two native regions and twenty-six relative call edges, including the
installed main entry and secondary code.
The official preflight request handler calls main `0x4023c0ac`, which uses the
outer-header probe at `0x7bd4fad3`. That probe reads the 512-byte `UPD` header
and checks the model, followed by separate version/build checks in main. It
does not call full decoding or ECDSA verification. A separate installation
handler calls bridge `0x4023c141` and then the full update job. The latter sets
the key, verification profile and unsigned allowance before invoking the full
decoder at `0x7bd4ee4a`. These secondary entry points are four bytes later in
the captured installed window; the reviewed calls are checked individually.

Therefore a confirmation prompt alone **does not prove unsigned acceptance**
or successful payload validation. It is an eligibility milestone. The complete
UI state machine has not been fully traced. A 3 KiB physical main read confirms
the reviewed preflight and installation bridges at their original main addresses;
their calls into the installed secondary job/probe are individually checked.
The [physical test log](../evidence/gm5-prompt-tests.json) records
observations separately from these static findings.

## Untouched signed control

To separate update discovery/eligibility from our container changes, the owner
requested the regular signed firmware. The
[control SD receipt](../evidence/gm5-signed-control-sd.json) records the original
31,901,184-byte official file, with SHA-256
`d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243`.
Its independent ECDSA and LibreSSL checks passed again; the SD readback equals
the original byte for byte. Only our known previous test file was replaced,
and the card was ejected. The
[flag restore capture](../evidence/gm5-signed-control-flag.json) independently
verifies **0 → 1** before this control.

The official main preflight also compares the candidate header's version/build
fields with installed program words. The compared halfword at physical
`0x400006a2` is `0x0111`, while the official candidate's corresponding field is
`0x0110`. The exact version encoding and result-to-UI policy remain unresolved.
This is a concrete reason to check eligibility separately; clearing the
container flags only affects the later job's header validator, and does not
remove every preflight comparison. Service-mode gating and card discovery
are still possible explanations, rather than established causes.

The signed control did not display a prompt in either service or normal mode.
The owner also reported “card is full” at startup. A subsequent
[read-only inspection](../evidence/gm5-card-readonly-check.json) found the
official file intact, about 15.9 GB free, and `fsck_msdos -n` exit zero. The
checker noted an unset FSInfo free-space cache; no repair was performed and
its connection to the camera message is unproven. This warning must not be
recast as a measured unsigned-image rejection.

## Advertised and built-in versions

The [higher-version candidate](../evidence/gm5-updater-prompt-0112.json) changes
both header version halfwords to `0x0112` and preserves all payload bytes. The
[card receipt](../evidence/gm5-prompt-0112-sd.json) records SHA-256
`45a7da844d497f9c52d90a1a7db73e2b54fb18a38d3a639b602320a7df269ce3` and an
identical SD readback. Its signature fails independent ECDSA and LibreSSL checks
as expected for changed signed metadata; native unsigned allowance is needed.

With that card present at startup, the owner reported no card-full message.
The [new arm capture](../evidence/gm5-prompt-0112-arm.json) verifies **1 → 0**,
and temporary English was set in both settings shadow and active UI cache.
After USB unplug without poweroff and Playback, the owner reported
**“Firmware update confirmation appears.”** The
[test log](../evidence/gm5-prompt-tests.json) records that observation. This
establishes a confirmation-screen path for the higher advertised-version
candidate, while leaving payload bytes stock. Version and startup/card state
were not fully isolated, so the result alone does not assign the earlier
failure to one cause. It also does not prove the later unsigned decoder or
programming job succeeds.

The owner subsequently reported that the prompt displayed **1.1**, then
powered off and reconnected in service mode. The
[final guarded capture](../evidence/gm5-prompt-0112-final-flag.json) verifies
that the flag reset to **one**; it sent zero RAM writes. The candidate file
remains on the card for research. No installation was confirmed and no
firmware programming was performed in this test.

The official identity/version getter at `0x402779c5` reads the program's own
words at `0x400006a0`, `0x400006a2`, `0x400006a4`, `0x400006a6`, and build data
at `0x400006ac`. Merely raising container metadata does not change those words
in the payload. Installing unchanged stock payloads would therefore be expected
to retain their stock reported version; whether the updater separately saves
the advertised value in service history or other settings has not been ruled
out. The candidate contains the official downloaded build, not a byte-for-byte
copy of the different installed Japanese program. No successful installation has been established.

## Owner-authorized control with the default flag

After the prompt-only milestone, the owner explicitly requested confirming the
raised-version unsigned candidate without changing the RAM flag. The earlier
stop-before-Yes instruction applied to the initial tests; this new request
authorizes an installation attempt for this control.

A [fresh read-only capture](../evidence/gm5-unsigned-default-pretest.json)
verified flag **one**. The owner then requested temporary English before
confirmation. The language settings shadow and active UI cache were changed,
followed by a [separate read-only flag capture](../evidence/gm5-unsigned-default-post-english-flag.json)
which again verified **one**. No host write to `0x70a68490` was sent during this
follow-up. Those two requested language RAM writes must be distinguished from
an update-policy change. No explicit EEPROM commit was sent.

The [installed rejection-path record](../evidence/gm5-default-flag-rejection-path.json)
pins seven native regions and exact branch bytes. The context initializer
zeroes 124 bytes; the job sets context+112 only when the runtime flag is zero.
With flag one, a zero inner marker takes the error return at `0x7bd4f160`,
**`0x80000065`**. That status propagates through decoder cleanup and the job's
error branch to `0x7bd50093`, bypassing the later programming path. This predicts
rejection; it is static review rather than target execution or a proof of every
callee side effect.

The existing card file remains the same candidate whose eight official payloads
are unchanged, SHA-256
`45a7da844d497f9c52d90a1a7db73e2b54fb18a38d3a639b602320a7df269ce3`.
The owner was asked to keep power on, unplug USB, enter Playback and confirm
Yes, then report the English result. If actual update progress starts, it is to
finish without power interruption. The owner reported a progress bar for about
three seconds, followed by an instruction to switch off and on. The camera
restarted and operated normally. The [post-test readbacks](../evidence/gm5-unsigned-default-posttest.json)
verified 24 KiB of installed firmware unchanged: 8 KiB at `0x40000000` and
16 KiB at `0x4154e000`. A final read verified flag one. The checked regions still
differ from the official candidate payload, ruling out its installation there.

The updater's CRC validation can display progress before the marker/signature
check; a brief bar therefore does not establish that programming started. The
measured result agrees with the predicted default-policy rejection. It does not
prove every flash byte was unchanged: there was no complete pre-test dump or
flash-bus instrumentation, and no numeric error was captured from the display.

## Candidate installation routes

| Route | Established | Still needed |
| --- | --- | --- |
| Normal signed SD update | Official decoding and GM5 signature verify | A changed signed image needs a valid signature, or an accepted alternate mode |
| Unsigned SD update after a temporary RAM change | Modified main physically installed; complete 8 MiB matches the candidate; policy zero persists through normal off/on | Other variants/patches and external recovery are not validated |
| Factory AHX image | GM5 has consumed `GM5.AHX` / `GM5E.AHX` strings, an image reader and calls toward flash code | Complete parser/writer/entry tracing, physical hardware gate and image layout |
| External programmer | Manual identifies sixteen-bit parallel NOR | Chip identification, board access and a concrete programming/recovery setup |

No successful modified firmware installation or explicit EEPROM commit has been
established. The owner-confirmed default-policy attempt above is distinct from
our host commands: none issued direct NOR programming. RAM-control,
temporary language-buffer writes and the SD test-file copy are recorded. The
language setting and active UI cache both accepted English in RAM; the owner
observed English temporarily, followed by Japanese again after restart. Its
[record](../evidence/gm5-language-change.json) is retained for the later
language/region firmware patch; persistence remains unresolved.

Captures remain local under `captures/`; tools preserve exact source/executable
hashes and stop on unexpected responses. The complete physical backup and
native-code controls are recorded in [backup and emulator usage](gm5-emulator.md).
A backup is not a tested recovery method: no hardware programmer or recovery
writer has been validated.

## Prepared unchanged-program control

The [minimal installed-program control](gm5-minimal-reflash-control.md) now
contains only unchanged installed Japanese `program2`: 3,538,944 plaintext
bytes at NOR offset `0x1400000`, covering 27 sectors. Its encoded file is
3,540,480 bytes, SHA-256
`f978123c4eafb4a8bd0961c46ee013eb161babda6020eb1e3cbd0c68833dc4c8`.
Main/boot code, resources and all settings/calibration payloads are excluded.
The header advertises `0x0112` while installed code/version bytes stay unchanged.

All eight official ciphertexts are reproduced byte for byte by the new encoder;
the retained original decoder independently recovers this exact installed
payload. Seven controls execute the installed native startup-copy, decoder and
post-decode writer instructions. Default policy rejects the package; allowance
one permits decoding and virtual programming. The successful complete 32 MiB
output equals the backup. Program-error and power-cut controls detect partial
images, with no changes outside `program2`. All 68 repository tests pass.
The [evidence](../evidence/gm5-minimal-reflash-control.json) retains hashes and
the complete operation plan.

No card copy, new camera RAM change or physical install occurred during the
offline preparation. Physical board entry/handshake, cleanup/restart and recovery remain
unproven. Because payload bytes are unchanged, matching physical readback would
not distinguish identical programming from rejection/no write. This control
can establish preservation and observe the physical sequence; final proof of a
flashing route still needs a separately reviewed distinguishable modification
or direct programming evidence. The prepared procedure makes that limitation
explicit before any actual erase/write attempt.

The owner subsequently reconnected both the GM5 and original LUMIX card. The
exact minimal control is now copied, byte-verified and safely ejected, with
the previous candidate preserved locally. A fresh read-only camera capture
verified policy one initially. After the owner returned the card and confirmed
the GM5 awake, a fresh installed-updater window matched the backup. English and
temporary policy zero were then written and verified. The
[live preparation record](gm5-minimal-reflash-control.md#live-preparation) links
all four receipts. The owner reported complete progress and automatic restart
without a message. The [post-test record](../evidence/gm5-minimal-reflash-posttest.json)
verifies a fresh full 3.375 MiB target readback identical to the backup, policy
one after restart, and unchanged version fields `0x0111 / 0x0111`. The complete
32 MiB was not reread. Identical bytes do not prove erase/program execution.

## Verified distinguishable policy change

At the owner's request, the [next package](gm5-policy-zero-package.md) changes
only the installed main's ROM policy byte at `0x406b1bdc` from one to zero.
The main payload is otherwise byte-identical to the backup. Its encoded file
SHA-256 is `86832e6eafa90b453894237805dafe128f61d346066f73a3752a8071d8286f16`.
It excludes all other components and calibrations, preserves installed version
bytes, and advertises header words `0x0113`. This first installation required
one temporary RAM policy change on the then-stock camera.

Eight exact-package native controls pass. The native virtual writer erases 64
sectors and programs 8,192 buffers; the complete NOR differs by exactly the
intended byte. Native initializer loops reloaded from that programmed image
preserve the cipher key and initialize RAM `0x70a68490` to zero. All 71
repository tests pass. The [readiness record](../evidence/gm5-policy-zero-readiness.json)
contains the exact hash, expected main readback and proof criteria.

The exact policy-zero file has since been copied, verified and safely ejected.
After the owner returned the card, a fresh ROM read confirmed policy one and
the guarded RAM preparation verified one → zero. The owner was instructed to
perform the agreed update. The owner reported longer progress and thought the
camera restarted before the bar reached its end, then confirmed a normal off/on
cycle before reconnecting. Read-only captures found ROM and RAM policy zero;
the surrounding ROM window differed by exactly the intended byte. A fresh
8 MiB main acquisition then matched the candidate byte for byte, SHA-256
`c918553771018e171605ecb1f177a4d64bc94b221fe5304b8ff419f4509d208d`.
The [physical proof](../evidence/gm5-policy-zero-physical-proof.json) establishes
modified unsigned installation and persistence on this camera/build. No host
RAM or NOR write was sent during the post-restart measurements. Other storage
was not reread and physical recovery remains unvalidated.
