# Image App follow-up: native code, settings-copy gating and USB leads

The phone-app route has not yielded a GM5 firmware reader or an update key.
The native crypto routine examined here implements a Unix-style DES password
hash. The settings-copy UI also has a Bluetooth-service prerequisite in the
reviewed version, weakening its relevance to GM5. The manual's adjustment-tool
backup remains the strongest documented software-access lead.

## Sources and scope

This follows the initial [52-command-class review](reverse-engineering.md).
The source is still the public third-party
[Image App 1.10.14 decompilation](https://github.com/maiermic/panasonic-image-app/tree/ef9bd7c2a8390204894c53b49d1e01a230141e2d),
revision `ef9bd7c2a8390204894c53b49d1e01a230141e2d`. It is not a verified
extraction of the owner's installed APK.

The follow-up acquired ten transfer helpers under `core/p040a/p041a`, the
settings-copy UI caller and capability class, its matching smali, and three
native libraries. Each acquired file's Git blob hash matches the downloaded
bytes. [The evidence record](../evidence/image-app-followup.json) contains the
source paths, byte counts and SHA-256 hashes. Local copies, symbol listings and
disassembly are under `work/image-app-1.10.14/`; none were installed or executed.

| Native library | Bytes | Observed role |
| --- | ---: | --- |
| `libhttpc.so` | 38,032 | FUGU HTTP client and Java JNI bridge |
| `libisys.so` | 51,560 | Platform wrappers, network adapters and DES password routines |
| `libtsuru3.so` | 103,844 | DUAL04/NSL network stack, including Linux UDP transport |

These are **Android ARM libraries**. Their architecture and addresses establish
nothing about the GM5 processor or camera memory map. The initial three-library
review has now been extended to static triage of all nine libraries, as detailed
below. Negative findings remain limited to the actual inspections performed.

### Full-app acquisition and triage

After network access became available, the pinned repository archive was
downloaded. All **886 Panasonic Java files, nine native libraries and the
manifest** were extracted; each file matched its Git blob hash. The
[new evidence record](../evidence/image-app-full-triage.json) retains the archive
hash, coverage, selected source hashes and nine library hashes. The full local
manifest and static listings are under `work/image-app-full/`.

The literal inventory now finds **142 CGI fragments**. Relative to the original
135, the additions are a bare path, audio start/stop, a streaming template and
generic settings templates. The only diagnostic-keyword literal candidate is
`encryption` in `C1853h.java:495`, alongside SSID/password/security parsing. It is
a Wi-Fi setting, not an update-decryption function.

Dynamic symbols and ASCII strings were inspected in all nine native libraries.
The additional libraries cover DLNA, P2P networking, AAC/MP4 handling, G.711 and
audio packet-loss concealment. Two findings need context:

- `libdlnaCore.so` contains shell help at file offsets `0x124b5d–0x1250bd`, but
  its commands inspect XML documents: node paths, XPath, namespaces and schema
  validation. These are phone-library strings, not a demonstrated camera console.
- `libp2papl_api.so` contains `VIANA_COM_EncryptMsg` / `DecryptMsg`, AES, RSA,
  DES and SSL symbols. `C2180c.java` loads it through `P2pmwlibJNI`. No link to
  the GM5 update decoder or an update key has been established. The earlier DES
  password-hash finding concerns `libisys.so`, not every crypto routine in the app.

This is broad static triage, not a manual trace of every Java/native function.
Third-party packages and incorrectly decompiled methods remain additional limits.

## 1. `isys_crypt` is a password-hash routine

Static disassembly gives this call chain:

`isys_crypt` at `0x4798` calls `isys_pl_crypt` at `0x7290`, which calls
`isys_pl_des_setkey` at `0x6a5c` and `isys_pl_des_cipher` at `0x6eb0`.
These are ELF virtual addresses before the Android loader's load bias, not camera
addresses or offsets into GM5 firmware.

The implementation:

- Derives the DES input from caller-supplied password characters shifted by one
  bit, padding an eight-byte buffer.
- Tests the caller-supplied salt for an underscore at `0x72ca–0x72ce`, selecting
  the extended password-hash path.
- Uses a two-character salt and a count of 25 on the older path
  (`0x734c–0x734e`).
- Encodes the result using the conventional crypt alphabet, present at file
  offset `0xb60f`.

This combination matches the behavior of the DES password-hash family, also
visible in the [FreeBSD implementation](https://github.com/freebsd/freebsd-src/blob/7806832f23fb31d28386d42692b221776c9f4ee4/secure/lib/libcrypt/crypt-des.c).
It does not establish byte-for-byte source identity. The observed key material
comes from the function's caller; this is not an identified camera update key.
`libhttpc.so`'s dynamic imports do not include these DES routines. This import
check does not establish that no other app component uses them.

Reproduce the static review with an LLVM-compatible `objdump`:

```sh
objdump --dynamic-syms work/image-app-1.10.14/lib/armeabi/libisys.so
objdump --triple=thumbv5te-linux-androideabi --disassemble-symbols=isys_crypt,isys_pl_crypt,isys_pl_setkey,isys_pl_encrypt work/image-app-1.10.14/lib/armeabi/libisys.so
```

Use Thumb decoding for these functions. Default ARM decoding produces invalid
instructions and misleading branch targets in this stripped library.

`HTTPcJni.java` loads all three libraries. `HTTPcSwitcher.java` distinguishes
inside-home and outside-home modes and initializes the native stack for the
latter. The native stack is not evidence of a camera shell or of the camera's OS.

## 2. Settings-copy support is weaker than the URL alone suggested

The previously identified GET remains real app code:

`/cam.cgi?mode=getinfo&type=camsetting`

However, following its UI caller reveals a prerequisite:

1. `view/cameraconnect/GuidanceMenuActivity.java:2140–2151` consults a
   Bluetooth-related service path, including GATT service/characteristic UUIDs,
   when deciding whether to enable settings copy.
2. Its alternative capability getter, `model/p051c/C1847f.java:480`, returns
   `false` in the inspected implementation. Matching smali,
   `model/c/f.smali`, method `H()Z`, confirms that constant result.
3. `CameraSettingActivity.java:561,570` reads the `BT_Connected` intent extra and
   uses it to enable the save button. Its HTTP download remains at line 766.

The ordinary non-Bluetooth path therefore does not expose settings copy through
this UI. This is **client-side evidence**, not proof that GM5's server rejects
the GET: a camera handler may exist independently of the app's UI. Keep the
probe optional and retain any response, but lower its priority as a GM5 dump
lead. A successful binary response would still need its contents and extent
established before being called anything beyond a settings export.

The ten added transfer helpers introduce no additional literal CGI query. The
recursive inventory now covers 62 files and 136 literals; its sole extra literal
is the bare `cam.cgi` path component. The original 135-fragment evidence remains
unchanged. There is no new diagnostic command in that count.

## 3. USB maintenance names are cross-model references

The pinned [libgphoto2 PTP definitions](https://github.com/gphoto/libgphoto2/blob/26a57b27caeb865a6b1d415aa5a80b47837c9023/camlibs/ptp2/ptp.h)
label Panasonic `0x9703` as a maintenance/version query, `0x9704` as USB-mode
control, and `0x9606`/`0x9607` as data-send/update operations. These labels are
reverse-engineered comments, not GM5 support declarations or a documented memory
reader. Sending update data to a camera is not a firmware export.

The same repository's [GH4 2.2 device report](https://github.com/gphoto/libgphoto2/blob/26a57b27caeb865a6b1d415aa5a80b47837c9023/camlibs/ptp2/cameras/panasonic-dmc-gh4.txt)
advertises standard PTP/MTP operations without that Panasonic maintenance family.
Neither newer vendor-opcode definitions nor another body's report should be
transferred to GM5 without observing its actual interface and operation list.
No vendor-opcode replay was attempted.

The [service-manual backup](service-manual-findings.md) consequently remains a
separate lead: acquire a GM5-compatible adjustment package, driver and model
profile, then trace its backup request offline. Existing public FZ-series
Tatsujin archives supply historical names and driver references. The FZ30 package
is now [acquired and statically inspected](service-software-findings.md), including
an EEPROM-read packet; it is not established as GM5 compatible. Board-photo and datasheet
searches did not resolve IC6003's actual part number; its voltage and reader
setup remain unspecified.

## Next inputs that change the investigation

- **The update consumer or a camera-side reader:** the official
  [GM5 1.1 bytes are now analyzed](gm5-v11-analysis.md), but the payload encoding
  remains unresolved. The direct Olympus and legacy AES checks did not decode it.
- **A GM5 adjustment package or existing backup capture:** distinguish fixed
  calibration records from an address-and-length program reader.
- **One stock Android Image App PCAP and installed APK version:** establish the
  real GM5 requests and responses, then trace those exact paths. The existing
  [Android capture procedure](reverse-engineering.md#first-physical-capture-android)
  remains applicable.

No plaintext firmware, GM5 encryption key or engineering-console switch has been
recovered. The new evidence narrows which software paths are worth pursuing.
