# GM5 LUT subsystem review sources

These are the chatbot-written native assembly sources for key LUT subsystems:
owned image-memory allocation and leases, table sampling/conversion, independent
processing frames, the queue adapter, saved-bank storage/restoration, sliders
and native list/touch handling. Firmware source and manufacturer bitmap/font
assets are not included.

The exact release is reproduced by `recipes/gm5-v11-luts.json` and
`tools/gm5_lut_package.py`. The source files expose build-time branches and
symbolic bindings; they are review material, not a complete firmware build
system or a claim that compiling each file alone produces the installed
bytes. Some final integration choices, fixed addresses, trampolines and
resource changes are expressed by the guarded byte recipe. Preserve its
input/output hashes when reproducing the owner-tested package.

The allocator uses `LUT_ADJACENT_POOL` for retained leases and
`LUT_ADJACENT_UNCACHED` for eligible payload spans. The native manager owns
one 2 MiB allocation; the subpool exposes 128 KiB minus 512 bytes of root
metadata. No fixed empty RAM hole or modified video-buffer size is required.
These software ownership checks do not prove hardware/DMA behavior in every
camera mode.

The recipe writes a 3072-byte session rather than the earlier 2560-byte
session; its tail owns the touch backup. Exported entry points retain
trampolines where needed. Earlier speculative pool/lifecycle/activation code
is excluded from this source selection and removed from the release image.

See `docs/gm5-luts.md` for limitations and the lack of independent recovery.
