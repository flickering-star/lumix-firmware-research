# Evidence log: GM5 native XPan

This file preserves the initial cloud investigation. The
[2026-11-04 firmware-access follow-up](reverse-engineering.md) supersedes its
download-availability and environment status. The official GM5 1.1 archive is now
downloaded, hashed and [structurally inspected](gm5-v11-analysis.md); Android app
and service-software findings are also recorded. Later live service-USB work
recovered GM5's key, decoded all eight components and demonstrated reversible
control of its unsigned-update RAM flag across USB unplug/replug. The current
[flashing investigation](gm5-flashing.md) records locally validated prompt-test
packages and a successful update prompt. An owner-authorized confirmation with
default signature policy showed brief progress, but 24 KiB of sampled firmware
remained unchanged, consistent with validation rejection. The complete 32 MiB mapped NOR backup is packet-verified. The
[native-code emulator](gm5-emulator.md) passes 44 official-build controls and
three installed-build initializer controls. A later
[one-byte main policy change](gm5-policy-zero-package.md) is now physically
installed: the complete 8 MiB readback matches the candidate, ROM and RAM policy
zero persisted through the owner's normal off/on cycle, and the installed
version fields remain unchanged. The [physical proof](../evidence/gm5-policy-zero-physical-proof.json)
supersedes the earlier unproven-installation checkpoint. Aspect-ratio work
remains deferred.
All network-blocker statements below describe the initial cloud investigation,
before the successful local acquisition.
The subsequent [physical USB observation](gm5-usb-observation.md) also supersedes
the original camera-unreachable status below.

## Scope and confidence

Requested feature: 65:24 JPEG output and matching live-view/EVF framing on the
Japanese and global Panasonic DMC-GM5. No camera is reachable from this cloud
session. No firmware flash, camera setting write, or service-menu change was
performed. No GM5 binary has been acquired or examined.

The GitHub repository initially had no commits or project files. This research
toolkit establishes the initial project baseline.

## Observed network blocker

GitHub repositories and the Python package index are reachable through the
configured HTTPS proxy when commands run with the required execution access.
Requests to `av.jpn.support.panasonic.com` fail at proxy CONNECT with HTTP 403.
The active restricted policy omits that domain. A draft allowlist addition was
saved successfully; saving a draft does not apply it to the running environment.
The available environment tools cannot unlock settings controls or publish the
draft. A GM5 detail-page path was attempted but could not be verified because
the request was denied before it reached the site. We therefore do not assert
that this path exists or that Panasonic currently offers a GM5 firmware update.

Firmware download assets for other Lumix cameras are documented on
`panasonic.jp`; this host may also be needed if a verified GM5 download redirects
there. The minimum immediate requirement is access to Panasonic's support index.

## Phone protocol: source-backed findings

Read-only requests used by existing public Lumix tools:

| Purpose | Request parameters on `/cam.cgi` |
|---|---|
| State | `mode=getstate` |
| Capability | `mode=getinfo&type=capability` |
| Complete menu | `mode=getinfo&type=allmenu` |
| Current menu | `mode=getinfo&type=curmenu` |
| Current aspect ratio | `mode=getsetting&type=aspectratio` |
| Current picture size | `mode=getsetting&type=pictsize` |

An older controller also emits
`mode=setsetting&type=aspectratio&value=4:3`, with selectable values `4:3`, `3:2`,
`1:1` and `16:9`. Its README reports GM1 compatibility and does not report GM5
validation. Those values are a baseline for investigation, not a discovered GM5
command set. No code here sends `setsetting`.

Other public clients use the session-access request
`mode=accctrl&type=req_acc&value=0&value2=CLIENT_NAME`. Camera approval may be
required. Some model families use different request parameters; our optional
pairing request is not claimed to be confirmed on GM5.

HTTP status 200 may carry a failure in XML `<result>`. The probe stores the raw
response and checks this application result rather than equating HTTP reachability
with success. Any `aspectratio` menu entry should be compared against what is
visible and selectable on the physical camera. An enum endpoint can simply reject
65:24; a protocol setter does not itself create new crop code.

## Firmware research: avoid cross-generation assumptions

Public S5/S5M2-family research describes `UPD\0` containers, partition tables and
encrypted payloads. Those cameras are much newer than GM5. Their offsets,
processor architecture, encryption and claimed signature scheme are **not
established facts about GM5**. Some published interpretations also require
independent verification: high entropy alone cannot distinguish good compression
from encryption, and a 64-byte field alone cannot prove ECDSA P-256.

Panasonic DVD/BD firmware tools named `pana-fw` handle FRM packages for those
devices. Their availability does not establish compatibility with camera updates.
They were inspected as a possible lead and are not used on an unknown GM5 image.

GH4 service-menu research describes `GH4F.TXT` (48 KiB) and `GH4U.TXT` (18 KiB)
as configuration/calibration/user-data dumps. These are not demonstrated full
executable firmware backups and their GM5 equivalents have not been established.
Changing region or configuration cannot be presumed to add arbitrary crop ratios.
No force-restore or counter/calibration modification is part of this work.

## Native feature investigation once a sample is available

1. Establish the exact model/version and retain the untouched official package,
   extracted binary, hashes and acquisition provenance.
2. Identify the update container from actual bytes. Validate entry boundaries,
   checksums and compression before trying to infer executable architecture.
3. If a payload is encrypted, characterize it and investigate the corresponding
   update/decryption path; do not describe entropy analysis as decryption.
4. Locate the `aspectratio` dispatcher, enum validation, JPEG geometry tables,
   image-size labels and display/EVF masks. Check whether they share a central
   crop table or maintain independent tables.
5. Check thumbnail/playback behavior, EXIF dimensions, RAW crop semantics, image
   orientation and existing aspect ratios. A successful menu entry alone does
   not demonstrate native XPan support.
6. Establish update acceptance and a real recovery path before a modified image
   is considered for a physical body. This project currently offers no repacker,
   signature bypass, patch offsets, flashable image or tested recovery procedure.

## Source revisions inspected

These are third-party research sources, not Panasonic documentation. Source files
were read locally; no third-party code was executed or copied into this toolkit.

| Source | Revision | Evidence |
|---|---|---|
| [peci1/lumix-link-desktop](https://github.com/peci1/lumix-link-desktop/tree/59e98be8e87cd2da26a30de2e5fe5519165cd94d) | `59e98be8e87cd2da26a30de2e5fe5519165cd94d` | `Control.html` aspect selector; README GM1 support and access prompt |
| [cleverfox/lumixproto](https://github.com/cleverfox/lumixproto/tree/14a27949ff408eab1f917167188f974841d08252) | `14a27949ff408eab1f917167188f974841d08252` | GX80 HTTP control and UDP preview notes |
| [seichris/lumix-panasonic-2010-era-image-sync-iphone-app](https://github.com/seichris/lumix-panasonic-2010-era-image-sync-iphone-app/tree/05eeee689bfbb29edafbf2080fc8ff8f4010d34b) | `05eeee689bfbb29edafbf2080fc8ff8f4010d34b` | GM1S validation; GM5 explicitly remains a candidate; access request |
| [ShaoCI-Hz/lumix-fullframe-reverse](https://github.com/ShaoCI-Hz/lumix-fullframe-reverse/tree/62d77cb5a63db6e9f098ee4065d409d5cb4d461e) | `62d77cb5a63db6e9f098ee4065d409d5cb4d461e` | Newer full-frame update-format research; official acquisition locations |
| [terrancewong/GH4Hack](https://github.com/terrancewong/GH4Hack/tree/ad193248002c2a23fb7082cfcb9b159b3170d2c5) | `ad193248002c2a23fb7082cfcb9b159b3170d2c5` | `notes/002.Backup.ROM.md` documents small service data dumps |

Official starting points, presently unverified because of the network blocker:

- [Panasonic body firmware index](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/index.html)
- [Panasonic Image App support](https://av.jpn.support.panasonic.com/support/global/cs/soft/image_app/)
