# GM1 internal 0111 updater profile

The owner's `gm1rombackup.zip` contains a complete33,554,432-byte mapped flash
backup with internal revision words `0111/0111`. Its SHA-256 is
`1e1a5de4055d8ae12d97db5ca3298329d40422272711d4eb78e943e56ee69c86`.
All32,768 individual block hashes and the completed-image hash agree. The raw
backup, body identity and executable components remain private.

The [profile review](../evidence/gm1-0111-updater-profile.json) checks the
following differences from the official-download `0110` image:

| Field | Official `0110` | Installed `0111` |
| --- | --- | --- |
| Main service dispatcher | `40369f7c` | `40369f78` |
| Dispatcher jump table | `4057b98c` | `4057b9a4` |
| Command5c read handler | `4036b711` | `4036b70d` |
| Command9c direct-store handler | `4036b379` | `4036b375` |
| Key record | `405ab460` | `405ab478` |
| ROM-policy initializer | `405c5b40` | `405c5b58` |
| Temporary RAM-policy halfword | `70903814` | `70903814` |
| Updater entry saving the policy | `4154a254` | `4154a286` |

The dispatcher prologue differs only in its relocated jump-table pointer.
Read dispatch, read handler, direct-write dispatch/handler and ACK templates
match byte-for-byte at the new locations. The key record matches the official
build. The original startup copy changes its ROM source/end by24 bytes and
keeps the destination; the relocated ROM-policy halfword therefore still maps
to `70903814`. The updater's saved-policy prologue and allowance templates
match the reviewed original behavior.

All six original complete-page fingerprints differ, so the old exact profile
correctly refused this body. Reading the old policy address on `0111` yields
an unrelated value. An unchecked revision skip would not fix that mapping.
The new profile uses complete-page fingerprints and revision-specific key/ROM
offsets, while preserving the fixed RAM store and all rechecks.

## Existing patches and matching restore

The app continues to use the same official GM1 1.1 BIN. Stable and LUT patch
deltas apply to that decoded official `0110` base; their executable payloads
are unchanged. Installing them replaces the selected program components, so
installed `0111` code relocations do not require rebasing patch addresses.
The displayed version remains1.1 and the internal program revision becomes0110.
This does not establish that applying old patch offsets directly to `0111`
would work.

The matching Stock Program Restore is separately constructed from bounded XOR
deltas against the same official download. Its decrypted program, graphics and
secondary program reproduce the reviewed original `0111` components exactly.
It excludes the remaining settings/body-calibration ranges. Complete firmware,
keys, serials and calibration are not bundled as raw inputs in the application.
Native startup/SD feature edits and recording-limit changes are not added.

## Validation scope

[Original service-code execution](../evidence/gm1-0111-service-native.json)
covers three1024-byte ROM reads and RAM-policy stores1→0→1 through the original
dispatcher and ACK builder. The complete policy page is compared and restored;
the frozen CPU reports no executable-ROM write. This is an explicit offline
API/frame/data fixture, not a physical USB transfer or full camera boot.

The app is also checked against four retained exact profiles, with unknown
revisions, mixed headers, changed code and changes after inspection refused.
Package validation checks real encoding/decoding, component hashes, native
preservation ranges, unchanged stable/LUT output compared with an `0110`
source profile, exact `0111` restore and reinspection of each prepared image.
Physical update installation and recovery on this body remain untested.
