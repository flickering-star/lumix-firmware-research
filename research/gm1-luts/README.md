# GM1 LUT review sources

These are chatbot-written assembly sources for the GM1 LUT port: native pool10
ownership, independent processing jobs, queue/producer wrappers, persistence,
native list/touch handling and full-strength processing. They are authored
patch code, not a Panasonic source release or a decompilation of the entire firmware.

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

The current GM1 recipe removes opacity completely. The old opacity-only review
files are removed here as well. `gm1_lut_full_strength_job.S` copies the source
table without blending or strength checks. `gm1_lut_fixed_style.S` hides all
adjustment rows while keeping native controls for original profiles.
`gm1_lut_title_only.S` uses the original native row-selectability predicate
at the common button/touch entry for a LUT tab. The native fifth-row flags
are reused. Native profile and kind2 entries replay their original prefix.
No polling or new preview/capture check is added. The owner found the preceding
no-opacity firmware usable, with a small performance penalty versus native
styles. The new row-entry change has bounded native button/touch checks;
physical testing of the new apps remains pending. GM5 opacity is unchanged.

The GM1 binding uses the unmodified native row predicate at`4014d879` over
the parameter-list pointer at`708f475c`: state4 is selectable and state1 is
hidden, matching the native fifth-row convention. The original direction
handler assumes some child is eligible and can still request editor entry
when every row is hidden. The common entry at`4010ab73` therefore enforces
that native predicate for LUT IDs7..16 only. Original style IDs and kind2
internal enums replay the original prefix. This runs only on an attempted
button/touch entry, with no additional background or frame-time checks.

See `docs/gm1-luts.md` for usage, the known transient colored-line issue,
reproduction and the lack of independent recovery.
