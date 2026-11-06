# Investigating another Lumix model

Transfer the investigation method, then establish a profile for the target
model and exact build. A matching USB PID, recognizable instruction or valid
update prompt does not establish compatible address maps or acceptance policy.
An untested model requires its own memory-read and updater-policy evidence.

## Establish identity and a read-only transport

Record model/region, firmware version, power/service state, cable/host path and
raw USB descriptors. Use the target's own service manual for temporary service
entry. An existing permanent service indication can result from prior language
or region changes; it is not a reproduced startup sequence.

GM1 and GM5 demonstrated `04da:2370` with `ff/a0/b0`, configuration one,
interface/alternate zero and bulk OUT `01`, bulk IN `82`, interrupt IN `83`.
Normal storage/PTP and the vendor service interface are different paths. A host
open failure or absent device is not a camera rejection. Investigate enumeration
and host access before sending a protocol command.

The established maintenance transaction is:

1. Prepare OUT with vendor setup bytes `4000000000000000`, then send the request.
2. Prepare IN with `4000000001000000`, then read the one-byte response type.
3. Prepare IN again, then read the full frame **including** its type byte.
4. Validate length, sequence/complement, status, checksum and terminator before
   interpreting any payload. Stop on error; do not automatically retry writes.

| Operation | Demonstrated meaning | Scope |
| --- | --- | --- |
| `38` | Fixed-area settings word read | Establish a known control for the actual model/body. |
| `70` | Program-relative word read | Main base/mapping must be independently corroborated. |
| `5c` | Absolute interval read; 1,030-byte class-one frames | The host limits each aligned read to 1,024 bytes. |
| `9c` | Absolute halfword RAM write on tested GM5 | Requires separately traced target code, original-value guards and readback. |

The shared host parser is [gm1_capture_verify.py](../tools/gm1_capture_verify.py).
The probe sources deliberately reject unknown model identities, ranges and
control bytes. Add an independently evidenced model profile; do not disable
those checks to make an unrecognized camera proceed. A small successful word
read should match a block read, then repeated forward/reverse windows, before
large acquisition or any write is attempted.

## Recover and validate the actual updater

Record the official update's exact source URL, bytes and SHA-256. Parse its
container independently; identify image geometry, directory fields, CRC/hash
selectors, cipher dispatch and actual consumers in native code. Acquire a small
installed-code control through the verified transport and compare it against
candidate decoded data. Encryption keys and IV handling must be rediscovered or
verified for that model.

The GM1/GM5 selector-three cipher is five-round AES-128-CBC, not standard
ten-round AES. Their encryption keys differ. Their separate directory signatures
also use different public keys. GH2's older parser/cipher behavior is not a
profile for a newer model. Component hash matches establish plaintext agreement;
they do not replace signature verification or camera eligibility checks.

Trace how key material, public keys and update context fields are initialized
from ROM into RAM. Map every alias/copy using real consumers; do not assume a
constant ROM-to-RAM offset. The GM5 policy initializer is `0x406b1bdc`, copied
to RAM `0x70a68490`. The traced GM1 runtime candidate is `0x70903814`. These
addresses are findings about those builds, not addresses to try on a different model.

Trace both signed and unsigned input branches, their return codes and all
callers. Determine whether a flag is read before/after decode, at a handoff or
after reboot. Test lifetime across USB reconnect and a normal power cycle as
separate events. A factory programming parser or a flash-chip part number does
not establish a physical entry method or accessible address interval.

## Separate local proof from installation proof

Preserve an original backup and the exact installed code used to construct a
candidate. Keep settings/calibration outside an experiment's payload. Review
the full erase/program plan, component bounds, advertised versus installed
versions, and all changed bytes. Run decoded native routines in a bounded
emulator where possible; compare complete virtual outputs, including rejection,
programming-error and power-cut controls. Record hardware/RTOS abstractions.

Proceed through independent observations: parsed file, exact decode/signature
controls, camera eligibility prompt, completed update, and installed code
readback. A progress bar is not sufficient proof. For a small patch, exact short
ROM windows plus post-cycle runtime observations can be a deliberately bounded
proof; label it accordingly rather than claiming a full image comparison.

For language work, trace saved-language normalization, list construction and
menu visibility separately. A one-time RAM language change can disappear on
restart. Prove ordinary menu selection/save/reload, then physical persistence
without host language writes masking the result. The GM5 three-byte recipe
addresses all three paths; another model may use different code and tables.

Publish source, minimal patch recipes, digests, model-specific addresses, native
call relationships, positive/negative controls and clear untested boundaries.
Leave firmware files, raw captures, calibration data and access credentials
local. This archive does not provide maintenance or review for independent ports.
