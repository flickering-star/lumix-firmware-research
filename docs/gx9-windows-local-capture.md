# GX9 USB captures saved directly on Windows

`tools/gx9_usb_capture_windows.py` runs directly on the Windows PC and saves
data locally before transfer. Its three profiles cover RAM ranges already read
successfully on the owner's GX9. It sends only `0x35` buffer controls and
canonical `0x5c` 1 KiB reads. It validates the measured service interface, PnP
camera model, working WinUSB driver and pinned official libusb DLL.

The capture tool makes no network connection, USB reset, driver installation
or camera write request. Every completed block and transfer-log entry is
flushed locally. Normal completion or a handled error produces a ZIP with the
data, log, report and source snapshot. An interrupted process may leave partial
files and a lock; inspect the previous job before starting another reader.

## Run locally on Windows

Copy the script onto the Windows PC with the camera connected in its previously
tested service mode. It uses the existing Python installation and official DLL
in `%LOCALAPPDATA%\Temp\lumix-gx9-research`. No package installation is needed.

Check the portable controls and current camera identity:

```powershell
C:\Python315\python.exe .\gx9_usb_capture_windows.py --selftest
C:\Python315\python.exe .\gx9_usb_capture_windows.py
```

The second command queries Windows PnP only and sends zero service requests.
To save the established Linux-prefix interval onto the Desktop:

```powershell
C:\Python315\python.exe .\gx9_usb_capture_windows.py --capture linux-prefix --workspace "$env:USERPROFILE\Desktop\GX9-captures"
```

The command prints the output folder and final `capture.zip` path. Other
profiles are `pre-linux` and `early-tables`. They do not add unverified address
ranges. The original DLL location stays independent of the selected output
folder; `--dll` can specify the same verified DLL elsewhere.

The worker requests that Windows remain awake only while the job runs, then
clears that request. This follows Microsoft's
[SetThreadExecutionState API](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate).
It does not change the persistent power plan or override an explicit sleep.

## Verification

The packet constructors and response checks were replayed against **3,220
original hardware exchanges**, including all three profiles, without issuing
new USB requests. Portable descriptor, packet and range controls pass. See the
[replay evidence](../evidence/gx9-local-capture-replay.json).

The standalone wrapper also passed its controls on Windows and captured the
80 KiB `early-tables` profile successfully. Its hash exactly matches the earlier
independent acquisition, and its temporary job power request ran.
