# GM1 LUT review sources

These are chatbot-written assembly sources for the GM1 LUT port: native pool10
ownership, independent processing jobs, queue/producer wrappers, persistence,
native list/touch handling and opacity. They are authored patch code, not a
Panasonic source release or a decompilation of the entire firmware.

The authoritative installed bytes are the bounded component recipe
`recipes/gm1-v11-luts.json` and the matching updater deltas. These selected
sources show key subsystems; they are not a standalone firmware build system.
Some code is selected or combined by the private research linker, and the
shared GM5 conversion/storage routines are reused with GM1 bindings. Compiling
every file verbatim does not reproduce the installed image.

The final producer wrapper is `gm1_lut_producer_stack.S`. Its metadata remains
inside its allocated stack frame through native Post and interrupt handling.
The dispatcher uses the same principle. Retained LUT data is a real native
pool10 child; original video buffer sizes and allocator instructions are
unchanged. There is no exFAT overlay, arbitrary empty-RAM reservation or new
SD scan at startup.

See `docs/gm1-luts.md` for usage, the known transient colored-line issue,
reproduction and the lack of independent recovery.
