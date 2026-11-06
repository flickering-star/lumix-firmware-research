# GH2 USB maintenance selection: offline findings

GH2 1.2 contains a separate USB vendor-service mode with **VID/PID
`04da:2370` and interface class/subclass/protocol `ff/a0/b0`**. Its descriptor
builder also reproduces **every configuration-descriptor byte** captured from
the owner's GM5 in normal PC and PictBridge modes. GM5 service-mode support and
its entry sequence remain unverified.

The [evidence report](../evidence/gh2-usb-maintenance-entry.json) preserves the
reviewed native instructions. The [offline verifier](../tools/gh2_usb_entry_verify.py)
checks the pinned plaintext, fifteen relative calls, the mode-message table,
and 943 instructions in twenty-one regions. Manual interpretation and mechanical
checks are recorded separately. No camera was contacted for this study.

## USB identities and the measured controls

Device-descriptor dispatcher `0x401e8db3` selects these builders:

| GH2 descriptor mode | Builder | USB product ID | Interface |
| --- | --- | --- | --- |
| `1` | `0x401e8ee3` | `2372`, or `2373` for one settings variant | `08/06/50`, mass storage |
| `2` | `0x401e8de9` | `2370` | `ff/a0/b0`, vendor service |
| `3` | `0x401e8e5c` | `2374`, or `2375` for one settings variant | `06/01/01`, PTP |

All use Panasonic VID `04da`. The service builder emits `bcdDevice=0x0100`.
Normal builders obtain their version bytes through another helper; the actual
GM5 reports `0x0110`. The fixed settings word at `0x7400b938` selects the normal
PID variants. That word is not established as a service-enable switch.

Configuration builder `0x401e8fe7` emits one interface, bulk OUT `0x01` and bulk
IN `0x82`. Modes `2` and `3` add interrupt IN `0x83`. With hardware-register
`0x9c007400` bit `0x20` set, the bulk maximum packet size is 512 bytes; otherwise
it is 64. Service interrupt packets use that same maximum, while PTP uses eight
bytes. The interval is eight in the 512-byte layout and sixteen in the 64-byte
layout.

At caller `0x401e71e3`, the descriptor-mode byte is also passed as the builder's
argument. A small host model of this stable-mode case matches the saved GM5
configuration descriptors:

| Host model | Actual saved GM5 observation | Bytes compared | Result |
| --- | --- | ---: | --- |
| GH2 mode `1`, 512-byte layout | PC, `04da:2372` | 32 | Exact match |
| GH2 mode `3`, 512-byte layout | PictBridge, `04da:2374` | 39 | Exact match |

These are independently captured [GM5 observations](gm5-usb-observation.md),
not synthetic test fixtures. The matches support a useful descriptor comparison;
they do not establish identical code, a GM5 `2370` mode, or compatible diagnostic
commands. The service descriptor in the report is a **GH2 model output**, with no
live service-mode observation from either camera.

## The service entry is related to camera state

The GH2 connection logic uses a three-value settings word at `0x74001e30`.
Its getter is `0x4015600e`; its setter accepts `0`, `1` or `2`. Relative to the
GH2 update-settings buffer at `0x74001b38`, this is byte `0x2f8`, word `0x17c`
(`H017 Lc` in that export layout).

The word has consumers beyond USB, including whether the USB device advertises
a serial-number string. A boot path at `0x40003891` calls input predicate
`0x7bccb3b7`; when it returns one, the boot path stores **two into this settings
RAM word**. The predicate checks input-derived state and requires the previous
word to equal one. The [subsequent service-sequence study](gh2-service-sequence.md)
connects its key tests to GH2's documented DISPLAY / AF/AE LOCK startup entry.

The USB-related preparation and decision routines are more specific:

- At `0x400d6524`, a settings value other than one, or RAM override
  `0x7435b189 == 2`, causes RAM selection `0x7435b18a` to become two. With the
  settings value equal to one and override zero, it first arms the override
  to one.
- At `0x400d6475`, input bit `0x80` in the word at argument offset eight,
  state helper `0x400d84a2 == 1`, settings value one, and armed override one
  allow the override to become two. The later key-map trace identifies this UI
  bit as DELETE; its full timing/state sequence remains unresolved. Other
  branches of this routine also affect a neighboring
  settings word, so calling it a harmless universal toggle would be unjustified.
- Eligibility routine `0x400d6556` first requires a settings value other than
  one or override two. It then accepts selection three, or selection two with
  connection-state argument one. This predicate alone does not change USB mode.

The supplied, language-edited GM1 update export contains `0000` at word `0x17c`.
It has a different model and settings extent; equal coordinates do not establish
the same field. No settings file was edited and no offset is proposed for GM5.

## From a camera decision to the vendor USB interface

The verified chain after the connection logic chooses selection two is:

```text
0x400d50f6: pass selected connection mode to 0x400e9a8f
0x400e9a8f: map selection 0/1/2 to a driver-mode request
0x401e678d: queue message D042, with selection as its record's first word
0x407f31a4: message table maps D042 to branch 0x401f80a8
0x401f80ae: call record dispatcher 0x401f8356
0x401f8356: record 0 -> storage; 1 -> PTP; 2 -> vendor service
0x401f88f5: initialize vendor mode
0x401f8942: store descriptor mode 2 to 0x744dd1ed
0x401f896d: call USB connection/start helper 0x401e9808
```

This separates the actual USB mode request (`D042`) from other internal messages
used for media transfers. `D042` is an internal firmware message, not a USB/PTP
operation to send from a host.

The byte at `0x744dd1ed` selects descriptors; the halfword at `0x744dd1e6`
selects **bulk protocol phase**. They are different variables. The phase dispatcher
at `0x401e6aa3` routes phases one/two into mass-storage handling and phases
three/four into `0x401eee32`, the receive path for the previously identified
[binary memory readers](gh2-debug-tools.md). A pending-mode transition can restore
a selected mode and set phase three. The later follow-up also identifies vendor
request-zero transfer preparation, matched to the FZ30 host. Complete enumeration,
reset and receive conditions have not been validated on hardware.

## Relationship to the familiar service menu

GM5's own manual, page 27, uses **temporary cancellation of Initial Settings**
before exposing error history and camera information. Page 16 uses the same
first step before the longer initial-settings cancellation procedure. The manual
does not specify the USB identity in those states.

The GH2 boot-state and USB-selection consumers make that familiar service entry
a relevant lead. They do not establish whether GM5's information screens or
language-export state also activate the vendor USB interface. A future passive
descriptor comparison across the already understood service state would resolve
that narrower question. The camera was discharged during this offline work, so
no mode transition or additional request was attempted.

## Reproduce

With the existing decoded GH2 body and built host decoder:

```sh
python3 tools/gh2_usb_entry_verify.py work/legacy-control/GH2__V12.body.decoded.bin --out work/gh2-usb-entry-new.json
```

Use a fresh output path. The verifier reads the saved, sanitized GM5 USB evidence
by default. It has no device, socket, packet-generation, settings-restore or
flashing operation. Its semantic models are handwritten summaries of reviewed
instructions, rather than firmware execution or a complete CPU emulator.
