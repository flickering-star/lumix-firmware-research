# GX9 Bluetooth protocol definitions

The recovered Linux `bt` application contains **eight GATT service definitions
referencing 34 characteristics**, including a separate factory service. The
[extraction and native verifier](../tools/gx9_bluetooth_protocol_verify.py) pins
the 88,892-byte executable, SHA-256
`71936c863d9ad0b6d28f2b7dcae4707128a2175f01fcf69628991600ef117ae4`.
The complete service/characteristic UUID mapping is recorded in
[the evidence](../evidence/gx9-bluetooth-protocol.json).

These are configured definitions. Advertising, current mode, pairing,
permissions and external reachability have not been measured. Raw property and
permission fields do not establish the application's complete access policy.

## Factory service and native callbacks

The factory service is `054ac620-3214-21e6-ac0d-0002a5d5c51b`. It differs from
the product service `054ac620-3214-11e6-ac0d-0002a5d5c51b`.

| Factory characteristic UUID | Internal ID | Raw property / permission fields |
| --- | --- | --- |
| `00000001-3215-11e7-ac0d-0002a5d5c51b` | `0x27` | `0x02 / 0x01` |
| `00000002-3215-11e7-ac0d-0002a5d5c51b` | `0x28` | `0x08 / 0x10` |
| `00000003-3215-11e7-ac0d-0002a5d5c51b` | `0x29` | `0x0a / 0x11` |

The named factory callbacks execute in the native ARM emulator:

- `BtSrvFact_ReadData`, entry `0x13784`, returns four identical bytes made from
  the low byte of a counter at `0x34ed8`, then increments it. Controls cover
  `00`, `01`, `fe`, `ff` and wrap to `00`; a following 12-byte sentinel remains
  unchanged.
- `BtSrvFact_WriteData`, entry `0x137f0`, increments counter `0x34edc` for a
  four-byte input. Three- and eight-byte inputs do not increment it.

Timestamp, logging and `memset` are modeled; the counter logic executes the
camera's instructions. No socket, file or process import is executed. These
functions implement test counters, so their names do not establish a memory
dump or flash-write API. The complete receive/characteristic routing still
needs to be followed.

## Process-call review

The executable imports `system`. Four direct ARM branch sites reach that import:
`0x12f40`, `0x12fe8`, `0x13054`, and `0x131b0`. Static review places them in
radio-test handling: a fixed `/etc/init.d/btteststart` path and fixed
`hci_cmd` command formats with numeric fields. Those are radio-controller
operations, not an identified camera-system firmware updater.

This direct-reference review is not a complete indirect-call or external
data-flow proof. No arbitrary shell request or delivery of Linux command event
60 through Bluetooth has been established. The previously identified internal
[Linux command-handler route](gx9-linux-command.md) remains a separate lead.

```sh
python tools/gx9_bluetooth_protocol_verify.py \
  --bt work/gx9-filesystems/rootfs2-files/usr/pvc/bin/bt \
  --out work/gx9-bluetooth-protocol.json
```

The next useful protocol step is to trace the other characteristic callbacks
through the Bluetooth application, NWA and the RTOS event consumers. This
analysis requires no live radio or connected camera.
