# GM5 connections: Wi-Fi pairing and USB investigation

Wi-Fi is the most useful first physical connection: capture a successful stock
Android Image App session, then reproduce its access request from the computer.
Normal USB can provide device/interface information and media access; neither
ordinary connection has been shown to expose executable firmware.

To retain the Mac's internet, GM5 can join the home router through **Via Network**.
The owner's manual, pages 262/265/295–296, places this choice behind **DISP.**
on the QR/SSID screen, followed by **From List**. Keep the Mac on its existing
network. The [source receipt](../evidence/gm5-wifi-via-network.json) also records
the Xiaomi's RNDIS interfaces and the absence of a macOS tethering adapter.

## Wi-Fi has two access steps

1. Join the camera's network using its displayed SSID/password or the app's QR
   setup. Select the camera's smartphone remote-shooting connection mode, rather
   than its separate send-to-PC feature. Panasonic's
   [GM5-specific guide](https://av.jpn.support.panasonic.com/support/spn/global/dsc/help/image_app/en/camera/DMC-GM5_GM1S_LX100/connect.html?no=0)
   describes the supported connection methods.
2. Request an application session. The inspected app builds:
   `GET /cam.cgi?mode=accctrl&type=req_acc&value=CLIENT_ID&value2=CLIENT_NAME`.
   The client name is URL-encoded. Joining Wi-Fi alone may therefore leave camera
   commands inaccessible.

At the pinned Image App revision, `C1501d.java:171–181` builds that request and
`C1497c.java:425` selects `accctrl`. The callers in
`model/service/p056c/C2013a.java` and `ImageAppTotalService.java` construct an
identity with prefix `4D454930-0100-1000-8001-` and a stored `Dlna_UUID_Seed`.
They explicitly test `ok_under_research`, `ok_under_research_no_msg`,
`err_others_requesting` and `err_user_refused`. Pending responses cause repeated
requests with a delay. Some decompiled control flow is incomplete; this is
static evidence of the handshake, not a GM5-validated implementation.

A computer can send the same HTTP request format. Whether the GM5 requires this
identity form, additional steps or on-camera confirmation must be observed.
There is no evidence here of an Android-only cryptographic requirement. A failed
unpaired query does not distinguish lack of command support from access denial.
The app-derived [evidence](../evidence/image-app-full-triage.json) records the
source hashes and limitations.

For the first capture, start recording before launching Image App and include
connection approval and normal menu browsing. See the
[Android procedure](reverse-engineering.md#first-physical-capture-android).
For a later PC test, close Image App so its session cannot confound the result,
connect the PC to the camera network and use the camera IP actually observed.

The existing probe's `--pair`, `--client-id` and `--client-name` retain an access
request and its raw response. Its pairing request is currently one-shot: it does
not reproduce the app's pending-approval loop, and non-XML response handling has
not been validated on GM5. Preserve those responses rather than interpreting a
partial capture as proof that PC access is impossible.

### Attempt on 2026-11-05

After the owner connected the devices to the phone hotspot, one SSDP discovery
send and one HTTP `getstate` request to a single candidate peer both failed on
the Mac with **errno 65, No route to host**. The HTTP failure occurred after
0.019 seconds. No HTTP response, camera identity, access denial or pairing result
was received. The candidate's identity as the camera was not established.

The [sanitized observation](../evidence/gm5-wifi-attempt.json) preserves the scope
and raw-log hash. The camera later discharged; the owner suspected a timeout.
The recorded host errors do not establish what caused the camera's displayed
error. Local network permission, routing and hotspot behavior remain unresolved.
No further camera-network probes were made during the subsequent offline study.

## USB offers a separate lead

GM5's USB connection uses the combined **AV OUT / DIGITAL** socket, `JK2001`.
The supplied service manual's page 59 shows USB data signals and AV signals on
that same connector; page 18 explicitly describes PC access over a USB cable.
The separate HDMI socket is not the USB connection. A USB data cable matching
the camera's connector is required; the AV label does not make it AV-only.

The official GM5 [specifications](https://panasonic.jp/dc/products/DMC-GM5/spec.html)
list USB mass storage and PTP. Its
[advanced manual](https://help.na.panasonic.com/wp-content/uploads/2023/02/DMCGM5_SQW0047_ENG.pdf)
describes `[PC]` and `[PictBridge(PTP)]` modes. These support ordinary media
transfer/printing, not a documented direct view of internal firmware storage.

A normal USB connection would still let us record device descriptors, interfaces
and endpoints. In PTP mode, a standard device-information query could identify
advertised operations. These observations would establish what this actual GM5
exposes; another model's vendor commands are not evidence of GM5 support.

The [GM5 service manual](service-manual-findings.md) documents adjustment-tool
backup but leaves its transport and memory extent unspecified. The older
[FZ30 service package](service-software-findings.md) explicitly uses USB
maintenance mode and has an EEPROM-read request. That makes service USB worth
investigating, while GM5 entry, protocol compatibility and program-memory access
remain unverified. The older driver's product IDs are not observed GM5 IDs.

The first [physical USB observation](gm5-usb-observation.md) now records the
owner's GM5 in PC mode (`04da:2372`) and PictBridge mode (`04da:2374`). A standard
PTP DeviceInfo query succeeded and reports version 1.1; no service command was
sent. PC mode exposes only card storage in its advertised configuration, and
normal PictBridge advertises no vendor operation codes. Service access remains
unverified.

The [GH2 service-entry follow-up](gh2-usb-maintenance-entry.md) now provides a
specific comparison: its normal descriptor layouts reproduce these GM5 captures,
while a separate vendor interface uses `04da:2370` and `ff/a0/b0`. This remains
GH2 evidence, with no GM5 service enumeration observed.

The earlier macOS
local-network permission prompt was reported during work that included localhost
HTTP integration tests; its precise OS trigger was not independently identified.
Those tests have finished. Offline inspection does not require LAN access.
