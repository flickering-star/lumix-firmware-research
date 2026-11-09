# GX9 alternate update-file selection

The decoded 1.4 main program contains a second path into the firmware updater
that constructs **`a:\MC282.upd`** and **`a:\MC282e.upd`**. Native tests now
execute model-tag construction, formatting, file selection and the preceding
decoded-key predicate. This identifies an alternate update path on volume `a:`;
it does not demonstrate arbitrary code booting from an SD card.

The [verifier](../tools/gx9_sd_update_route_verify.py) and
[evidence](../evidence/gx9-sd-update-route.json) pin the same original 1.4 main
program used for the update-policy analysis. No camera, card, real filesystem
or flash is accessed.

## Native selection

Selection starts at `0x03f7bf94`. Function `0x041b6128` constructs the camera
identity and supplies model tag `MC282`. The native formatter `0x041afaec`
executes the formats at `0x03f7c110` and `0x03f7c11c`; the filenames are produced
by the original code, rather than inferred from a string match.

The path checks the `e` file first:

| Modeled files present | Selected path | Updater caller parameter at `+0x0c` |
| --- | --- | --- |
| Neither | Cleanup path; no updater entry | — |
| `MC282.upd` | `a:\MC282.upd` | 2 |
| `MC282e.upd` | `a:\MC282e.upd` | 3 |
| Both | `a:\MC282e.upd` | 3 |

Successful controls stop at entry `0x04014f80`, **before executing the updater**.
They verify its selected path and caller parameters. The missing-file control
stops at cleanup `0x03f7c0e0`. These are checkpoints, not claims that the entire
routine returned successfully.

The function makes task-control requests for IDs `2..0xec` and LED calls before
file selection. Those operations, media preparation and file existence are
modeled. Sixty-three repetitive idle loops are accelerated; their repeated
identical stack-byte stores are not hardware timing tests. Model construction
and string formatting execute natively, with C copy/zero helpers modeled.

A control starts with live policy one and both files present. The policy remains
one at updater entry; no bank reload or policy write occurs within this selection
routine. This does **not** establish retention through USB disconnect, a reboot,
or the ordinary update menu.

## Entry predicate

Caller `0x03f7901e` reaches selection via `0x03f7905e`. Its checks include bit
five clear in MMIO halfword `0x7f093080`, key predicate `0x041b5de2`, and a
media/GPIO predicate at `0x041e7e3c`. The complete caller and real input hardware
have not been executed.

The key predicate requires decoded bits **`0x508`**. Native positive/negative
controls verify all required bits, rejection of a missing bit, acceptance of
additional bits, and rejection when the modeled media predicate is false.
Additional controls execute all three original key converters from raw ADC
halfwords at `0x0621935a`, using the fixed-bank calibration centers. Removing
any one channel rejects the condition. These ADC controls do not replace the
key converters; only the media predicate is modeled.

The physical button names corresponding to those channels have not been
established. Therefore this finding is not yet a button sequence or an SD boot
procedure. It also does not prove an `.AHX` loader, Linux replacement or generic
autorun mechanism. Both selected files are passed to the existing firmware
updater, where policy, parsing and programming remain separate stages.

```sh
python tools/gx9_sd_update_route_verify.py \
  --program work/gx9-components-v14-decoded/program.plaintext.bin \
  --out work/gx9-sd-update-route.json
```
