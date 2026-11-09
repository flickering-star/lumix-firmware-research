# GX9 update-directory authentication

Both official GX9 **1.4 and 1.5 signatures verify** with the public point
embedded in the decoded 1.4 camera program. Independent OpenSSL checks and
execution of the camera's actual ARM SHA-256/ECDSA code agree. The native parser
rejects changed directory metadata even when the ordinary body CRC is corrected.

This identifies the authentication stage. It does not establish a complete
modified-update installation, flash writer or alternate boot path. The
[reproducible evidence](../evidence/gx9-update-authentication.json) contains the
input identities, native call counts and negative controls.

## Signed data and representation

The UPD directory contains 36 records, each 92 bytes. Native function
`0x040275da` hashes the extent beginning with the repeated header at file offset
`0x2a0`: `0x4c + 36 × 0x5c = 3,388` bytes, ending at `0xfdc`, exclusive.
The component names, offsets, sizes, flags, plaintext hashes and CBC IVs lie
within that signed extent. The 64-byte signature is at file offset `0x220`.

| Package | SHA-256 of the signed extent |
| --- | --- |
| 1.4 | `5f12c256d087fad30ea7b9b3cfd7cbbf1faec365b20e0d44804663a7bfc5faf5` |
| 1.5 | `7862f96f377432bc84b1d0aec3686ced7556a6939e15afdf6495a711fb009079` |

The curve is **NIST P-256**. The public point is stored as two little-endian
32-byte coordinates; the signature contains two little-endian 32-byte integers,
`r` and `s`. The native verifier also interprets the SHA-256 output bytes as a
little-endian integer. Consequently the independent OpenSSL raw-digest check
reverses the 32 digest bytes and converts the coordinates and signature integers
to conventional big-endian DER representations. Supplying the unreversed
digest fails for both original packages.

The public point's stored-byte SHA-256 is
`9f1c0f68e2bad2b265fae5b36d625bf9bc0a9e6c49302542fa4a1815730829d1`.
It is public verification material; no private signing key was recovered.
The separately recovered AES key decrypts components but does not generate
valid signatures for changed directory contents.

## Native path

Addresses below belong to the fully decoded 1.4 `program` image, linked at
`0x03e80000`, SHA-256
`1ea24a84e5bbc1fa24beef59628a8c0fc13d8de042efbe187730031dc4f263d5`.

| Address | Observed role |
| --- | --- |
| `0x04014f80` | Updater orchestration; parses input before entering programming stages |
| `0x04015762` | Separate model/version/format checks, called before body authentication |
| `0x040271e4` | Supplies the 16-byte component decryption key to the parser context |
| `0x04027a9e` | Supplies the validation-reference descriptor at `0x04622bac` |
| `0x04622bac + 0x54/0x58` | Public-point length `64` and pointer `0x04622b6a` |
| `0x04027830` | Calls native SHA-256 wrapper `0x0402ca74` on the signed extent |
| `0x0402784a` | Calls native signature wrapper `0x0402af82` |
| `0x0402afd2` | Calls the underlying elliptic-curve verifier at `0x0402b82a` |
| `0x04027858` | Successful authentication checkpoint, before component processing |

The initialized-data scatter copy moves the AES key from its image source to
`0x05ed1c28`; the updater passes that runtime pointer. The authentication path
also tests a halfword at `0x03f1801a`. It is zero in both the official image and
the independently captured runtime image, selecting the verified signed path.
The owner subsequently ran the prepared local USB probe. Its saved USB log
independently verifies policy `0 → 1 → 0`, exact restoration of the complete
metadata block and an installed updater-code match. No update or flash command
was started. See the [physical policy proof](../evidence/gx9-update-policy-live.json).

An additional native control changes that halfword to **one inside the emulator**.
The same altered directory that returns `0x80000066` under policy zero then
reaches the next parser stage without calling ECDSA. At that checkpoint the
native stack flag controlling later component-hash checks is also zero. This
is a concrete candidate for permitting modified update contents. It has not
yet been tested by starting the connected camera's updater or programming flash.
Later [full-parser and persistence controls](gx9-flashing-research.md) also
identify the policy as part of the fixed-settings shadow, requiring its stored
bank to be considered for a permanent change.

## Positive and negative controls

The native verifier runs inside Unicorn. C memory-copy/zero-fill helpers are
modeled. Native CRC32 is first checked against an independent 64-byte control;
the full 102,537,728-byte CRC is then accelerated with the matching host CRC32
representation. A progress-sizing loop is accelerated separately. SHA-256,
ECDSA, the CRC comparison and the parser's authentication branches execute
actual camera instructions.

| Input/control | Result |
| --- | --- |
| Original 1.4 | OpenSSL success; native parser reaches `0x04027858` |
| Original 1.5, using the 1.4 verifier | OpenSSL success; native parser reaches `0x04027858` |
| One signed component-digest byte changed, body CRC recalculated | OpenSSL rejects; native parser returns `0x80000066` |
| One signature byte changed | OpenSSL rejects for both packages |
| Unreversed SHA-256 bytes supplied to OpenSSL | Rejected for both packages |
| Validation-reference descriptor omitted | Native parser returns `0x80000005` without calling ECDSA |
| Body byte changed, original CRC retained | Native parser returns `0x80000064` before calling ECDSA |
| Altered directory, correct CRC, no public-reference descriptor, emulated policy one | Reaches the parser checkpoint without ECDSA; later component-hash flag is zero |

Successful native runs stop at the authentication checkpoint. That is
deliberately recorded as a checkpoint, not a successful return from the full
parser. Payload decryption, all-component verification, updater model/version
rules and actual programming are separate stages. The earlier
[complete host decodes](gx9-firmware-decryption.md) verify every component's
plaintext against the now-authenticated directory hashes.

## Reproduce offline

The [verifier](../tools/gx9_update_auth_verify.py) reads local input files and
runs the host's OpenSSL executable. Add `--native` to execute the parser and its
negative controls in Unicorn 2.1.4:

```sh
python3 tools/gx9_update_auth_verify.py \
  --program work/gx9-components-v14-decoded/program.plaintext.bin \
  --firmware work/gx9-official-v14/GX9__V14.bin \
  --firmware work/gx9-official-v15/GX9__V15.bin \
  --native --out work/gx9-update-auth-check.json
```

This verification performs no camera or network access. Its input-image memory
is read-only inside the emulator, and execution stops before the parser's
in-place component decryption.

## Completed Windows-local policy test

[The local USB probe](../tools/gx9_update_policy_probe_windows.py) uses the
existing WinUSB driver and pinned libusb DLL on the PC. It does not use SSH.
The default `--inspect` mode verifies the installed 1.4 updater-code block,
the complete policy metadata block, known code/buffer controls and an independent
word read at service address `0x83f1801a`.

The optional `--roundtrip` mode performs those guards first, temporarily changes
only the policy halfword `0 → 1`, verifies the exact changed block and word,
then restores `1 → 0` in a `finally` path. Restoration requires the complete
original block to match. It never starts an update, changes an SD card,
programs flash or resets the camera. It stops if the pinned 1.4 code or metadata
differs. Its packet/ACK, inspection, restoration, injected read-failure and
mismatched-code controls passed offline. **The owner's physical round trip
completed successfully**, and the saved raw transfers passed
[independent offline replay](../tools/gx9_update_policy_capture_verify.py).
Both writes were restored before the camera was disconnected.

Keep `gx9_update_policy_probe_windows.py` and `gx9_usb_capture_windows.py` in the
same directory. With the existing PC Python and libusb setup:

```powershell
& C:\Python315\python.exe .\gx9_update_policy_probe_windows.py --inspect
& C:\Python315\python.exe .\gx9_update_policy_probe_windows.py --roundtrip
```

Each run prints its result and saves `report.json`, flushed USB events, acquired
blocks and a ZIP under `%LOCALAPPDATA%\Temp\lumix-gx9-research\gx9-policy-local-*`.
No connection credentials are required or included.
