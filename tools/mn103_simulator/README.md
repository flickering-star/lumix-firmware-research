# GNU AM33-2 execution adapter

Build from the `gm5` repository root:

```sh
python3 tools/mn103_simulator/build.py
python3 tools/gm5_emulator.py updater-tests --out work/emulator-check-new
```

The [emulator and backup notes](../../docs/gm5-emulator.md) explain the native
controls, memory maps, execution limits, GNU build portability fix and missing
short-swap encodings. `runner.c` and the instruction-boundary hooks implement an
offline line-protocol harness. `short-swaps.igen` adds only the two short aliases
listed in GNU's opcode table, with its existing long-form operations. There is
no camera transport or full camera hardware model. The optional `devices.c`
binding and `nor_model.c` implement the traced x16 NOR command subset, shared
read/write aliases, injected errors and operation-boundary power interruption.
The [virtual-installation notes](../../docs/gm5-virtual-installation.md) describe
the native writer tests and explicit synchronization/cache/board abstractions.

GNU source, generated files, binaries and private traces stay under ignored
`work/`. The build receipt records exact hashes and commands. The linked adapter
and CPU simulator are GPL-3.0-or-later; see [COPYING](COPYING).

`--variant rtos_aliases` builds a separate executable/receipt and adds optional
`RAM_ALIAS ADDRESS SIZE SHADOW`. It creates shared backing only for bounded
`0x70` RAM and its matching `0xb0` view. Scenarios use the frontend's
`ram_aliases` list to replace an exact RAM map with that pair. Neither the old
default executable nor its historical evidence is replaced. The
[native RTOS/UI notes](../../docs/gm5-native-rtos.md) describe the new controls
and current interrupt-notification boundary.
