# Local MN103 disassembly adapter

This small callback adapter builds unmodified GNU binutils 2.42 decoder sources
into an offline command-line reader. It does not emulate or execute camera code.
The GNU sources are fetched separately over verified HTTPS and checked against
the SHA-256 values in `build.py`; their GPLv3+ notices are preserved.

```sh
python3 tools/mn103_adapter/build.py
work/toolchain/mn10300/mn103-dis FILE BASE START END MACH
```

All numeric arguments accept hexadecimal. `BASE` maps byte zero of `FILE` to a
candidate runtime address. `MACH` is `300` for base MN103/AM30, `330` for AM33,
or `332` for AM33-2. Selecting a decoder does not establish the camera's CPU.
Bad start alignment can decode data or instruction operands as instructions.

For the verified legacy GH2 body, the inner directory starts `program` at file
offset `0x400`; its reset entry loads `0x40000018`. The investigated mapping is
therefore `BASE=0x3ffffc00`. GM1/GM5 have since been decoded independently; their
standalone main payloads use `BASE=0x40000000` and `program2` uses
`BASE=0x7bc00000`. For the older GH2 body, for example:

```sh
work/toolchain/mn10300/mn103-dis work/legacy-control/GH2__V12.body.decoded.bin 0x3ffffc00 0x401dfa87 0x401dfb23 332
```

The output includes instruction addresses and raw-byte annotations. The local
`build.json` records source hashes, compile arguments and executable hash.
`evidence/gh2-settings-consumers.json` records known instruction controls and
the selected firmware regions used in the research.

The GH2 body also contains a second linked segment: file offset `0x8c0400`
maps to `0x7bbc0000`, so use `BASE=0x7b2ffc00` for its instructions. The
[diagnostic findings](../../docs/gh2-debug-tools.md) document the reset, startup
copy and library/string references supporting that mapping. The
`tools/gh2_debug_verify.py` verifier checks the selected regions and dispatch
links against the exact known GH2 plaintext hash.
