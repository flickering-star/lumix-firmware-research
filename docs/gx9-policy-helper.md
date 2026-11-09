# GX9 Windows policy helper

[`gx9_policy_helper_windows.py`](../tools/gx9_policy_helper_windows.py) can leave
the verified **1.4 live RAM policy set to one** for a separate manual update
attempt. It also supports inspection and restoration to zero. It performs no
firmware installation, SD-card write, camera reset or flash operation.

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
fixed-settings reload can replace this RAM value. **Retention through USB
disconnect and entry into the SD updater has not been physically verified.**
This helper therefore verifies the policy precondition; it does not establish
that the complete update/boot sequence is ready or will succeed.

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
& C:\Python315\python.exe .\gx9_policy_helper_windows.py --enable --firmware E:\GX9__V14.bin
```

The candidate is 102,538,240 bytes, SHA-256
`719fc4e4daeb17f09172e7ac59675fdc0a637376a73284e814f9a9b266aa6883`.
It changes the policy in both `program` and `eep_fix`; the old program-only
candidate is superseded. Full-file decoding and native preparation/reload tests
pass, but physical installation and boot remain untested. See
[candidate and persistence details](gx9-flashing-research.md).

## Checks and saved results

Before any write the helper checks the model, service interface, transport and
DLL hashes, known buffer word, Linux code, installed updater code, and complete
1 KiB policy block. Only the policy's two bytes are normalized when checking
that block, allowing an already-enabled state to be inspected or restored.

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

Six state controls cover inspection, enabling, restoring and already-correct
states. Five precondition failures cause no write. Fourteen injected post-write
failures verify restoration, and a simulated disconnect verifies uncertain-state
reporting. The [preflight receipt](../evidence/gx9-policy-helper-preflight.json)
records these results. The new complete helper and its additional fixed-bank
read have not yet been run on the physical camera.

Four additional [native integration controls](../evidence/gx9-policy-helper-native.json)
feed replies produced by the camera's ARM handlers into the unchanged helper
logic. Inspection, enabling, already-enabled handling and restoration pass.
The USB exchange and alias coherence are modeled explicitly; the real helper
checks coherence through both physical read paths. The
[integration verifier](../tools/gx9_policy_helper_native_verify.py) performs no
camera access.

The helper files were copied to the owner's PC, where `--selftest` passed.
The prepared candidate was transferred separately and its complete SHA-256
verified on that PC. Those preparation steps did not open the camera.
