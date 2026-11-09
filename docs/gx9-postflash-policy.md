# GX9 / Japanese GX7MK3 post-flash policy result

On 2026-11-09 the owner reported that the prepared policy-one firmware installed
successfully and the camera works. A subsequent physical USB inspection of the
DC-GX7MK3 confirmed **policy one at the unchanged address `0x83f1801a`**.
The corrected Windows `CHECK.cmd` operation passed without a memory write.

## Filename and installed candidate

The prepared 1.4 candidate is 102,538,240 bytes, SHA-256
`719fc4e4daeb17f09172e7ac59675fdc0a637376a73284e814f9a9b266aa6883`.
It changes the same policy in `program` and `eep_fix`; its UPD revision is
`0x141`, while the program version bytes remain unchanged.

The camera initially did not recognize the global-style `GX9__V14.bin` name.
The official [Japanese download page](https://av.jpn.support.panasonic.com/support/dsc/download/fts/dl/gx7mk3.html)
uses `GX7M3V15.bin`; the [global page](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gx9.html)
uses `GX9__V15.bin`. Independently downloaded 1.5 binaries compare byte-for-byte
equal, both SHA-256
`c08354c91d083d74b274c4884ab4f06d3f72e47ea289ea80c9685f2292f5b801`.
The existing patched 1.4 file was therefore renamed to **`GX7M3V14.bin`** on the
owner's PC. Its full SHA-256 remained unchanged. The owner then reported the
successful installation. A Japanese official 1.4 binary was not obtained or
compared; the regional payload comparison used official 1.5.

## Measured result

The old CHECK stopped at its first settings-buffer comparison. That word had
changed from `f2b0` to `0000`; it had not reached the policy read. Direct reads
of the established ranges showed matching code and policy one. After adding
the newly observed buffer value, the helper's actual inspection passed:

| Check | Physical USB result |
| --- | --- |
| Absolute policy, `0x9b` at `0x83f1801a` | `1`, twice |
| Fixed-bank shadow, `0x35`, area `0x22`, index `0xc00d` | `1`, twice |
| Complete metadata block, `0x83f18000`, 1 KiB | Policy `01 00` at offset `0x1a`; remaining bytes match the original guard |
| Linux code, `0x80208000`, 1 KiB | Original guard matches; repeat exact |
| Updater code, `0x84027800`, 1 KiB | Original guard matches; repeat exact |
| Settings-buffer control | `0000`; repeat exact |
| Service transactions | Twelve reviewed reads; zero memory or flash writes |

The helper still requires the same code and complete normalized metadata
hashes. It accepts only the two measured buffer values and requires the value
to remain unchanged during the inspection. It does not relocate the address or
skip a failed code/metadata guard.

The [post-flash evidence](../evidence/gx9-postflash-policy.json) records the
decoded result and hashes. The
[offline verifier](../tools/gx9_postflash_policy_verify.py) checks every saved
request, response type, frame checksum, payload, code hash, policy reading and
repeat. It rejects any request outside the exact twelve-read sequence.

For a privately saved helper capture containing `report.json`, `events.jsonl`
and `memory.bin`:

```sh
python3 tools/gx9_postflash_policy_verify.py --capture CAPTURE_DIR --out result.json
```

The verifier passed on the real capture. Five fault controls rejected an
injected write command, mismatched memory file, bad reply checksum, an extra
metadata change and changed Linux code. Updated helper tests passed twelve
portable state controls and eight integrations using the native ARM USB
handlers. Its self-test also passed on the owner's Windows PC before physical
inspection.

## What this establishes

The installation and working-camera observation come from the owner. The
independent USB capture establishes policy one in the running camera, agreement
between the absolute and fixed-shadow paths, and the guarded block contents.
This supports the intended persistent-policy result after the reported update.
The capture does not read the entire installed firmware or perform an
additional controlled power-cycle test. Raw firmware, captures, keys and SSH
connection material remain private.
