# GM5 firmware access investigation — 2026-11-04

The immediate objective is executable firmware or a memory-read primitive. Native
65:24 JPEG and EVF/live-view changes remain the eventual project goal. A GM5 has
now been [observed over USB](gm5-usb-observation.md), including a successful
standard PTP DeviceInfo query. No GM5 firmware dump, plaintext decode or flash
operation has been achieved.

The software investigation now has two concrete routes: the owner's **Android
Image App** traffic and the **adjustment-software backup operation documented on
page 53 of the service manual**. A public Image App 1.10.14 decompilation provides
command evidence; the service tool's backup extent remains unknown. A
memory-capable GM5 debug menu or shell is **not yet established**. The manual also
establishes a parallel NOR flash bus for a hardware fallback.

The official GM5 1.1 update is now acquired. Its
[eight-component container, CRC and encoding checks](gm5-v11-analysis.md) are
verified against actual bytes. The [FZ30 service package](service-software-findings.md)
has also been statically unpacked; it supplies an older USB protocol reference,
with GM5 compatibility unresolved.

The owner's language-edited `PRIVATE.zip` now supplies a concrete **GM1 EEPROM
export**. Its [settings analysis](settings-backup-findings.md) identifies the
format, language coordinate and repeated blocks, without establishing a console
flag. An offline parser/comparator supports subsequent controlled GM5 captures.

New settings backups were unavailable during the initial offline work, which follows
[offline consumers](offline-consumer-findings.md): actual GH2 export/import code
for the same text format and named FZ30 read-mode handlers. A tentative GH2
decoded-size issue is recorded with model controls; it is not established on GM5.

Further [GH2 diagnostic tracing](gh2-debug-tools.md) now identifies binary
maintenance handlers for firmware-relative, RAM-relative and absolute-address
word reads. Their native dispatch links are checked offline. This establishes
readers in GH2 code, while their complete activation conditions and GM5 support
remain unresolved. No interactive text shell has been established.

## What the Olympus branch actually establishes

Inspected the local `pen-f` branch `codex/xpan-multicamera` at
`6b6741c1a111452768241bd82653ef2e3f8c3061`, without checking it out or modifying it.
Its `XPAN_EP7_DEBUG_CONSOLE.md`, `XPAN_EP7_SHELL_COMMANDS.md` and
`XPAN_EP7_FIRMWARE_DUMP.md` document:

- The E-P7 loads typed parameters from `PARAMDT/CP000001.CSV`; parameter `F971`
  enables a Wi-Fi engineering console on TCP 23.
- Physical E-P7 evidence confirms `sys mdump4` can return memory. CRLF and an
  initial wake-up line matter for that shell.
- Its built-in `flash dump` was traced offline but was not sent to hardware:
  the fixed read buffer overlaps a declared loaded firmware range.
- A resident RAM dump and a complete flash backup are different artifacts.

This supports searching for a corresponding **mechanism**, not transferring
Olympus filenames, parameter IDs, addresses or commands to Panasonic. No evidence
found here connects Panasonic's service settings to the Olympus parameter loader.

Underlying engineering-shell reference:
[cmdada's system notes](https://github.com/cmdada/em10-fw/blob/6adb3bef36239859ae3fcd94b0dbb7db6de6ffa1/notes/system.md).

## Image App: inspected code and useful leads

Source: [maiermic/panasonic-image-app](https://github.com/maiermic/panasonic-image-app/tree/ef9bd7c2a8390204894c53b49d1e01a230141e2d),
revision `ef9bd7c2a8390204894c53b49d1e01a230141e2d`, labeled Image App 1.10.14.
This is a third-party decompilation; it is not a verified extraction of the owner's
installed app. Its modified manifest's `debuggable=true` does not establish that
the Play Store app is debuggable.

The initial review retrieved **52 top-level Java files in `core/p040a`**, plus HTTP transport and logging
classes. All 66 initially retrieved text files matched their recorded Git blob
hashes. A further settings-copy activity was inspected to identify the consumer.
The local sources and acquisition manifest are under
`work/image-app-1.10.14/` and are excluded from Git.

The reproducible [core inventory](../evidence/image-app-1.10.14-core.json) contains
**135 unique CGI string literals**, with file hashes and line references. These
include templates, fragments, and commands for other camera/camcorder families;
they are not 135 validated GM5 commands. Generic builders also take arguments
from callers or camera-supplied menus, which literal extraction does not resolve.

Paths below are relative to
`panasonic-image-app_1.10.14/source/com/panasonic/avc/cng/` at the pinned revision.

| Finding | Code evidence | Meaning for GM5 research |
| --- | --- | --- |
| Plain HTTP command builder | `core/p040a/C1497c.java:66,352` | Builds `http://HOST/cam.cgi?mode=...&type=...&value=...&value2=...`. The phone capture can reveal the actual GM5 branch and values. |
| Access request | `C1501d.java:171–181` and `C1497c.java:425` | Builds `mode=accctrl&type=req_acc`, with caller-supplied identity and encoded client name. This is session access, not firmware decryption. |
| Camera menus | `C1468ao.java:93,123,153` | Requests capability, allmenu and curmenu. Save the complete responses, including command attributes and values absent from the physical UI. |
| Binary settings export | `C1468ao.java:182` and `C1450al.java:211` | `getinfo&type=camsetting` is specifically expected to return `application/octet-stream`. Follow-up tracing found Bluetooth-related UI prerequisites; GM5 support is unverified and low confidence. |
| Settings import | `C1468ao.java:203,230` | `startsenddata&type=camsetting&value=LENGTH`, then POST `senddata`. Its caller is `view/camerasetting/CameraSettingActivity.java:766,817`. This is settings copying, not a demonstrated firmware exporter. |
| Phone-to-camera geodata | `C1519h.java:535..584` | Sets playback mode, sends clock information, starts `geodata`, then uploads data. Establishes another structured input path; does not establish an exploitable parser. |
| Device description | `C1469ap.java:138` | `getinfo&type=ddd` exists in the Viana-family command class. It is an optional cross-family query, not a confirmed GM5 endpoint. |
| Media services | `C1450al.java:704` | Uses UPnP ContentDirectory `Browse`; use the actual SSDP LOCATION and service descriptions rather than another body's hardcoded device path. |
| App debug logging | `util/DebugLogProvider.java` | Stores logs in the phone's SQLite database. Its name does not indicate a camera debug shell. |

The literal review found no `firmware`, memory-dump, Telnet, shell, encryption or
decryption candidate strings in those **52 core files**. This is a limited
negative result, not a search of every app component or the camera firmware.
Native libraries, dynamically assembled commands and camera-supplied menus remain
outside that literal result. A [follow-up review](image-app-native-findings.md)
examined ten additional transfer helpers, the settings-copy UI gating and three
native libraries. The only additional CGI literal was a bare path component;
the native DES routine matches a Unix-style password hash. No GM5 update key or
executable-memory reader was identified in the inspected material.

The subsequent [full-app triage](../evidence/image-app-full-triage.json) covers
all 886 Panasonic Java files and all nine native libraries from the same pinned
repository. It finds 142 CGI literals, with added fragments concerning streaming,
audio and generic setting builders. No firmware-reader literal was identified.
Native AES/SSL and XML-shell strings require context and do not establish camera
decryption or a camera console; see the [updated findings](image-app-native-findings.md).
The app explicitly handles pending approval and client rejection. The
[connection notes](camera-connections.md) distinguish Wi-Fi authentication,
application-session access and ordinary USB modes.

Panasonic's own [Image App guide](https://av.jpn.support.panasonic.com/support/global/cs/soft/image_app/dsc/android/android02.html)
lists GM5 among supported remote-shooting models and says exposed settings depend
on the body and current mode. It does not document binary settings-copy support
for GM5. Successful phone pairing therefore does not imply `camsetting` works.

## First physical capture: Android

Use the existing stock Image App. Record its version and each body's firmware,
region and mode. An Android capture is preferable to guessing more endpoints.

1. Install [PCAPdroid](https://github.com/emanuele-f/PCAPdroid) on the Android phone.
2. Select **PCAP file** as dump mode and Image App as the app filter. Start capture
   before opening Image App. Its local VPN capture does not require root.
3. Connect to GM5 normally. Open remote shooting and its settings menus; change
   one ordinary aspect ratio, then browse/download an existing photograph. Note
   the time of each action. Keep this first capture short.
4. Stop and retain the original PCAP, an action log and the installed app version.
   Copy them under `captures/` for local analysis. Review identifiers before sharing.

The [PCAPdroid guide](https://emanuele-f.github.io/PCAPdroid/quick_start.html)
documents that non-root capture preserves application-layer bytes but synthesizes
network/transport headers and captures phone-initiated connections. Camera-initiated
UDP live view or discovery may be absent; an absent packet is not proof an endpoint
does not exist. If Image App bypasses the VPN or fails to connect with it enabled,
record that result and use a capture at a controlled access point or a rooted
phone. Another client on the same Wi-Fi does not automatically see the phone's
unicast traffic.

The recovered camera control path is HTTP, so TLS interception is unnecessary
for that traffic. Check the actual capture before assuming all app traffic is
plaintext. In Wireshark, useful starting filters are:

```text
http.request
http.request.uri contains "cam.cgi"
ssdp || udp.port == 1900
tcp.port == 60606
```

Inspect complete TCP streams for split HTTP requests and responses. Preserve the
pairing identity, headers, any session tokens, HTTP and application result codes,
device/service descriptions and binary response bodies. Distinguish actual memory
address/length parameters from camera settings or media-object identifiers.

## Read-only computer capture

After the phone capture, close Image App and connect the computer to camera Wi-Fi.
Use the actual camera IP. The existing probe now has an optional extended mode:

```sh
python3 tools/camera_probe.py snapshot --host 192.168.54.1 --label gm5-normal --firmware 1.1 --extended --console-banner --out captures/gm5-normal
```

Use the body's actual firmware version in that command. The default six queries
are unchanged. `--extended` adds only four GET queries: lens, curmode, ddd and
camsetting. All raw bytes, HTTP headers, lengths, hashes and camera result codes
are retained. Binary settings are classified as an **unvalidated candidate**;
XML error pages and HTTP 200 alone are not treated as a binary export.

`--console-banner` makes one TCP connection to port 23, listens briefly and sends
**zero application bytes**. Open/silent, closed and banner results remain distinct.
An open port alone is not shell confirmation; a closed port does not exclude an
engineering shell behind another mode or transport.

If the camera rejects an unpaired client, repeat to a **new directory** with
`--pair`. `--client-id` and `--client-name` can reproduce values observed in the
phone capture if the default identity `0` is unsuitable. Pairing is opt-in and
can require an on-camera access confirmation.

An unsupported optional query yields a partial capture and a nonzero exit status;
keep the output. If the owner already has a known working service-mode state, a
separate capture in that state can reveal changed menus or services. Entering or
changing service mode is not itself a read-only action, and this probe does not
do it. Do not upload a settings blob merely to test the export hypothesis.

## Firmware sample and storage

The official [GM5 update page](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gm5.html)
was verified through the browsing tool. It lists version **1.1**, dated
2015-02-09, archive `GM5__V11.zip` (31,905,359 bytes), extracted `GM5__V11.bin`.
The page's Mac download link targets:

```text
https://av.jpn.support.panasonic.com/support/share/eww/en/dsc/fts/mac/GM5__V11.zip
```

The ZIP and BIN are now in `firmware/official-gm5-v11/`, acquired with system
`curl` over verified HTTPS. The BIN SHA-256 is
`d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243`.
The [receipt](../evidence/gm5-v11-acquisition.json) records the source URLs,
archive hash and ZIP integrity check. Earlier DNS restrictions no longer prevent
acquisition. To inspect the retained sample:

```sh
python3 tools/panasonic_upd.py firmware/official-gm5-v11/GM5__V11.bin --out work/gm5-upd-report.json --olympus-check
```

The [original GM5 byte analysis](https://reverseengineering.stackexchange.com/questions/13410/extract-firmware-of-my-camera-lumix-mg5)
shows a readable `UPD` header and directory names including `program`,
`guires`, `program2` and `armcode`, followed by high-entropy payload. It reports
31,901,184 bytes for the BIN. Those sizes and names are independently confirmed
in our acquired sample, together with the full directory and body CRC32.
Short binwalk MyISAM/ZBOOT hits
do not provide a valid unpacker, and neither entropy nor a partition name proves
a cipher, operating system or executable architecture.

The uploaded [Panasonic service manual, order DSC1411019CE](../evidence/gm5-service-manual-source.json)
is now locally verified and inspected. All 62 pages were text-extracted, and key
tables and diagrams were also checked visually. The 8,586,793-byte PDF has
SHA-256 `8b517daaaaad766987180fc4dc8fe13e3b7a0e31cdec848a471c73f09ce3a8de`;
its Git blob matches the uploaded file. See the
[acquisition record](../evidence/gm5-service-manual-source.json) and
[detailed manual findings](service-manual-findings.md).

- **Page 53, note 2** explicitly describes using adjustment-software communication
  to back up **IC6003 data**. The extent is omitted, while page 8 describes an
  EEPROM backup and page 28 distinguishes Data Area from Program Area. This is a
  service-protocol lead, not proof of executable firmware export.
- **Page 58** identifies IC6003 as **256-Mbit NOR (32 MiB)** with `DQ0..DQ15`,
  `A0..A23`, `WE#`, `OE#` and `CE#`. This establishes a **16-bit parallel bus**.
  The exact part, voltage, complete ball map and external-reader isolation remain
  unresolved; an SPI clip or eMMC reader does not match the shown interface.
- **Pages 60 and 62** trace FP9009's `TXD`/`RXD` to hot-shoe external-flash
  circuitry. These labels do not identify a debug UART.
- **Pages 27–29** document error history/camera information, without a memory-dump
  command or engineering-console entry. Page 59 documents Wi-Fi SDIO and normal
  USB wiring, without a service command protocol.

Earlier Panasonic manuals name **DIAS (DSC Integrated Assist Software)** and
**TATSUJIN**, useful names for locating adjustment packages and bundled help. A
GM5-compatible package or driver has not been acquired or identified. The full
manual findings distinguish these cross-model references from GM5 evidence.

Reading this NOR is a concrete fallback if software access fails. It could reveal
boot/update code without first solving update-package protection, **if those
regions are stored in plaintext**. A raw chip dump does not automatically reveal
encrypted regions or a key stored in SoC OTP/internal ROM. A verified RAM reader
would instead expose resident decrypted code but could omit boot stages and
unloaded components.

## Investigation order and acceptance criteria

1. **Obtain remaining inputs:** installed Android APK(s), one
   short GM5 PCAP and any GM5 adjustment package/help or existing service capture.
   The full service PDF and official ZIP/BIN are acquired and verified; retain
   their originals and hashes.
2. **Resolve the phone protocol:** match actual pairing and requests to code;
   save allmenu/capability and advertised UPnP service descriptions. Determine
   which read/export operations GM5 implements, including the settings candidate.
   In parallel, compare same-body GM5 service exports around one known normal
   setting change; the supplied GM1 sample is a format reference, not an offset map.
3. **Look for an engineering entry:** compare observed normal/service responses
   where available; trace concrete diagnostic commands, file paths or export
   fields. A configuration flag needs a known consumer before being called a
   debug-shell switch. App upload paths are investigation targets, not established
   vulnerabilities or a reason to fuzz a working camera blindly.
4. **Inspect service software and storage:** establish the documented backup's
   extent and transport; identify IC6003's actual part and parallel-bus access.
   A genuine debug UART has not been located, and the hot-shoe TXD/RXD labels
   should not be treated as one.
5. **Prove a dump:** obtain repeatable bytes from known readable ranges, verify
   chunk completeness, reconstruct code/data and establish architecture/load
   addresses. Then inspect the actual update/decryption and integrity consumers.

Encryption and update authentication are separate questions. A successful dump
or recovered decryption key would enable analysis; modified firmware acceptance
and a recovery path would still need to be established before native XPan work
can reach a camera.

## Installed Android app extraction and offline reproduction

With [Android platform-tools](https://developer.android.com/tools/adb), enable
USB debugging and authorize the computer on the phone. These commands inspect
the installed app:

```sh
adb shell dumpsys package com.panasonic.avc.cng.imageapp > captures/image-app-package.txt
adb shell pm path com.panasonic.avc.cng.imageapp
```

For **every** `package:/...apk` returned, run `adb pull` with that exact path into
a new local directory; retain base and split APKs. Do not reinstall or re-sign the
app for this capture. Record SHA-256 hashes. With [JADX](https://github.com/skylot/jadx),
decompile the pulled app for comparison; native `.so` libraries need separate
inspection. The public older decompilation is sufficient for the current lead,
while the installed version establishes the owner's actual client behavior.

To reproduce the checked-in core inventory from the pinned public source checkout:

```sh
python3 tools/image_app_inventory.py PATH_TO_CHECKOUT/panasonic-image-app_1.10.14/source/com/panasonic/avc/cng/core/p040a --out work/new-image-app-core.json
```

The local original report is `work/image-app-core-inventory.json`; full-app
triage is under `work/image-app-full/`. The extractor does not replay its strings.
The broader suite passed **21 tests**, including the UPD parser checks, after
network permissions changed. Earlier runs skipped four localhost integration
cases under the former restriction. Socket-free fixtures exercise request
encoding, HTTP parsing, binary settings preservation, error classification and
passive-banner behavior. None of these tests establishes GM5 compatibility.
