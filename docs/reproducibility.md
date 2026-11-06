# Inputs, evidence and reproducibility

The public snapshot distributes source and research metadata. It excludes
official/decoded/patched firmware binaries, device NOR/RAM/settings dumps, raw
transfer captures, firmware archives, compiled programs and local SSH setup.
Ignored `firmware/`, `captures/` and `work/` are private input/output locations.
Manufacturer manuals are referenced by source information instead of bundled
PDFs. GNU simulator licensing is retained in its [COPYING](../tools/mn103_simulator/COPYING).

## Choose the correct workflow

Use the [GM1 guide](gm1-reproduction.md) for physical controls and the fully
decoded six-component update. Use the [GM5 guide](gm5-reproduction.md) for the
two hash-pinned main baselines, patch recipes and exact accepted package.
The [model-porting guide](porting-to-other-models.md) documents how to establish
a different model's transport, crypto, address map and updater policy.

The new `lumix_patch.py` and `gm5_public_package.py` take explicit local inputs.
They regenerate the tested main/package without the original camera's unique
NOR/settings backup or card UUID. Their output is offline: making a file does
not flash a camera or establish that its currently running updater will allow it.

The earlier `gm5_*` experiment collectors/builders retain tightly pinned source
hashes and historical capture/output paths. They are the original experiment
harnesses, not a universal installer. Some require the original body's private
settings/NOR fixture and cannot be replayed from a public checkout alone. Do
not substitute another body's calibration data or relax a guard merely to make
one of these historical harnesses pass.

## Interpreting evidence

Files under `evidence/` are summarized reports, not the raw firmware or full USB
packets. Relative paths into ignored directories identify withheld inputs.
Hashes let an owner compare independently obtained data. A summary is not an
independent reproduction when the raw input is unavailable to the reader.

Public summaries normalize machine-specific home paths and omit the research
card UUID. Their original bytes are retained privately. Hashes of historical
reports/source snapshots refer to those original artifacts; the normalized
public JSON is not necessarily byte-identical to its historical report hash.
Firmware/component digests and the exact patch/package hashes are unchanged.

Distinguish source-derived behavior, bounded native emulation, physical readback
and owner observations. For example, the GM5 language proof contains exact short
ROM windows and post-cycle settings/UI reads; normal-mode flashing and pressing
the off/on switch are owner observations. The full post-language main readback
was explicitly stopped. The earlier policy-only proof did compare the full main.

Original source and executable versions are retained privately for historical
runs, so a later additive source change need not reproduce their source hashes.
The 81-test region-readiness receipt and 111-test later full-suite result are
different milestones. Tests requiring firmware or emulator binaries skip when
those local prerequisites are absent; report executed and skipped counts.

```sh
python3 -m unittest discover -s tests -v
python3 tools/audit_public_tree.py
```

The audit checks the Git index, not all private files on disk: only explicitly
staged text/source/report paths are eligible. The public-release branch is a new source-only root snapshot: it has no
ancestors containing the previously tracked manual. Original research history
is preserved locally and is not part of this public branch. When publishing to
an existing private repository, replace or remove its old private refs before
changing visibility; merely selecting a new default branch does not hide old
branches or their history.

This is an unmaintained snapshot. Independent reproductions and ports belong in
your own fork; [contributions and support are not accepted](../CONTRIBUTING.md).
