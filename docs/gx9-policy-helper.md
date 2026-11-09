# GX9 Windows policy helper

[`gx9_policy_helper_windows.py`](../tools/gx9_policy_helper_windows.py) can leave
the verified **1.4 live RAM policy set to one** for a separate manual update
attempt. It also supports inspection and restoration to zero. It performs no
firmware installation, SD-card write, camera reset or flash operation.

The owner has reported a successful manual installation and working camera.
The corrected helper then passed a physical, read-only inspection with policy
one through both access paths. See the [post-flash result](gx9-postflash-policy.md).

Keep these three unchanged files together on the Windows PC:

- `gx9_policy_helper_windows.py`
- `gx9_update_policy_probe_windows.py`
- `gx9_usb_capture_windows.py`

They use the existing Python and WinUSB/libusb setup. No additional Python
packages, administrator prompt or network connection are needed.

## Run independently

Prepare the SD card before starting the powered camera session. Connect the
camera in the service USB mode already used for the earlier capture, then run
from the helper directory:

```powershell
& C:\Python315\python.exe .\gx9_policy_helper_windows.py --inspect
& C:\Python315\python.exe .\gx9_policy_helper_windows.py --enable
```

Success prints `Verified live RAM policy 1 through both read paths` and
`Policy 1 was left enabled`. The helper closes its USB interface. Keep the
camera powered on between enabling and the intended manual update. A reboot or
fixed-settings reload can replace this RAM value with the stored bank's value.
The owner subsequently installed the prepared two-component candidate and
reported that the camera works; readback from the running camera confirms one.
The helper itself only inspects or changes RAM.

To put the live RAM policy back to zero:

```powershell
& C:\Python315\python.exe .\gx9_policy_helper_windows.py --restore
```

That command does not rewrite the stored fixed bank. Inspection and either
requested state are idempotent: an already-correct value produces no write.

The optional `--firmware PATH` verifies the exact prepared two-component
candidate before opening USB. It accepts its SHA-256 regardless of filename;
it does not copy or install the file:

```powershell
& C:\Python315\python.exe .\gx9_policy_helper_windows.py --enable --firmware E:\GX7M3V14.bin
```

The candidate is 102,538,240 bytes, SHA-256
`719fc4e4daeb17f09172e7ac59675fdc0a637376a73284e814f9a9b266aa6883`.
It changes the policy in both `program` and `eep_fix`; the old program-only
candidate is superseded. Full-file decoding and native preparation/reload tests
pass. Installation and boot are owner-reported; the subsequent USB inspection
independently verifies policy one and the guarded blocks. See
[candidate and persistence details](gx9-flashing-research.md).

## Checks and saved results

Before any write the helper checks the model, service interface, transport and
DLL hashes, known buffer word, Linux code, installed updater code, and complete
1 KiB policy block. Only the policy's two bytes are normalized when checking
that block, allowing an already-enabled state to be inspected or restored.

The buffer control accepts the two physically observed values: `f2b0` before
installation and `0000` afterward. Its final read must equal its initial read;
all code and complete normalized metadata guards remain unchanged. An older
helper rejected `0000` before it reached the policy read. That failure did not
indicate a relocated policy address.

It reads the flag both as absolute address `0x83f1801a` and through the native
fixed-bank shadow reader, `0x35`, area `0x22`, index `0xc00d`. Both must agree
before and after a change. The absolute write remains the same fixed `0x9c`
halfword operation used in the owner's successful round trip.

After changing the value it verifies both readings, every byte of the expected
block and repeated code/buffer controls. If a post-write check fails or is
interrupted, it attempts to restore the original value and complete block.
An unsuccessful restoration is reported as an uncertain state, never success.
There are no automatic retries or arbitrary address/value arguments.

Each run prints its `report.json` and `capture.zip` locations under
`%LOCALAPPDATA%\Temp\lumix-gx9-research\gx9-policy-helper-*`. The ZIP includes
flushed USB events and acquired blocks for offline checking. A lock prevents
overlap with the other capture tools; Windows is kept awake only for the run.

Portable controls run without opening USB:

```powershell
& C:\Python315\python.exe .\gx9_policy_helper_windows.py --selftest
```

Twelve state controls cover inspection, enabling, restoring and already-correct
states with both buffer values. Six precondition failures cause no write.
Fourteen injected post-write failures and two changed-buffer controls verify
restoration; a simulated disconnect verifies uncertain-state reporting. The
[preflight receipt](../evidence/gx9-policy-helper-preflight.json) records these results.

Eight additional [native integration controls](../evidence/gx9-policy-helper-native.json)
feed replies produced by the camera's ARM handlers into the unchanged helper
logic. Inspection, enabling, already-enabled handling and restoration pass.
The USB exchange and alias coherence are modeled explicitly; the real helper
checks coherence through both physical read paths. The
[integration verifier](../tools/gx9_policy_helper_native_verify.py) performs no
camera access.

The updated helper was copied to the owner's PC, where `--selftest` passed.
Its actual `--inspect` operation also passed on the connected camera: twelve
service reads, policy one through both paths, complete metadata/code repeats,
and zero memory or flash writes. The existing `CHECK.cmd` uses this operation.
The [wire verifier](../tools/gx9_postflash_policy_verify.py) independently checks
the saved request/reply bytes and memory payloads.
