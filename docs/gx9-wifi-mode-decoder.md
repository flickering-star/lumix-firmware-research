# GX9 Wi-Fi HTTP mode decoder

The recovered PSM application has a **26-entry HTTP mode table** at `0x5dea8`.
Native function `PsmCgi_GetMode`, `0x2fdcc`, uses query-value extractor
`0x2fc5c` to select from it. All 26 entries and eight additional controls now
execute successfully in the offline ARM emulator.

The [verifier](../tools/gx9_wifi_mode_verify.py) pins the recovered PSM SHA-256
`7cafa9b91050c613b9fa76391f12003cbdd0a8e91f4e2e46dc0b22b1a5166fbd`.
The [evidence](../evidence/gx9-wifi-mode-controls.json) contains every defined
mode, internal ID, fixture and result. No HTTP request or camera action is sent.

| Query fixture | Native mode result |
| --- | --- |
| `mode=getinfo` | 5 |
| `mode=getstate` | 4 |
| `mode=camcmd` | 6 |
| `event=60&mode=getinfo` | 5 |
| `mode=getinfo&event=60` | 5 |
| `mode=linux_cmd` | 8, unrecognized/missing-mode sentinel |
| `mode=firmware` | 8 |
| `mode=60` | 8 |
| Missing mode / null query / 24-byte unknown mode | 8 |

The native query extractor and mode lookup are not replaced. C string/memory
operations, logging and timestamps are modeled. The test stops after decoding
the mode; it does not execute that mode's camera command or every subtype.

The defined entries cover settings, stream control, camera state/info, camera
commands/control, content information, transfer progress/data, playback/editing,
accessory control and notifications. No standalone `firmware` or `linux_cmd`
mode occurs in this table. This does not rule out an updater reached through a
subtype, another endpoint, or another protocol.

Earlier native [CGI/ICC event-path controls](../tools/gx9_linux_event_path_verify.py) establish
that `cam.fcgi` constructs outer event **6000**, including for a query containing
`event=60`. The new decoder controls show that adding that parameter also leaves
the selected `getinfo` mode unchanged. They do not establish an external route
to internal Linux command event 60.

```sh
python tools/gx9_wifi_mode_verify.py \
  --psm work/gx9-filesystems/rootfs2-files/usr/pvc/bin/psm \
  --out work/gx9-wifi-mode-controls.json
```

The remaining protocol work includes the selected-mode handlers, transfer
subtypes and their RTOS consumers. Pairing and current physical Wi-Fi behavior
remain untested in this offline work.
