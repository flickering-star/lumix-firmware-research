# GX9 flashing route and policy persistence

The owner's Windows-local USB test confirmed the live policy field can be
changed and restored. Native ARM tests now trace unsigned-container acceptance,
fixed-settings preparation, sector transfer and bank reload. A rebuilt **1.4
research candidate** sets policy one in both its initial program shadow and
stored `eep_fix` component. The owner has now reported successfully installing
that candidate and a working camera. A subsequent physical USB inspection
verified policy one at the original address through both read paths, with
matching code and complete normalized metadata guards.

The [post-flash result](gx9-postflash-policy.md) separates that installation
report from the independently decoded USB readback. Earlier candidate evidence
records the preparation-time state, including `ready_to_install: false`.

## Physical policy result

The downloaded owner-run capture contains 14 checksum-validated service
transactions. It reads the policy at service address `0x83f1801a`, changes
`00 00 → 01 00`, verifies the word and complete block, then restores `00 00`.
Only block offset `0x1a` changes. The original 1 KiB block and both updater/Linux
code controls match after restoration. Its ZIP SHA-256 is
`b0c3112f9c102f99a2fbbea31e1a41761574e4c950a8e0a8f6c77628a502249a`.

[Independent wire proof](../evidence/gx9-update-policy-live.json) and
[replay verifier](../tools/gx9_update_policy_capture_verify.py) establish this
without trusting the producer's result booleans. Downloading those saved files
did not open the disconnected camera or issue new USB requests.

A separate [Windows-local helper](gx9-policy-helper.md) supports an
owner-run enable-and-leave operation. It checks both the absolute policy word
and the native fixed-bank shadow, leaves one set on success, and offers a RAM
restore command. Its portable controls pass on the PC; native integration
controls also pass with modeled USB/alias coherence. Saved owner-run reports
show the original helper successfully enabling the live policy. After the
reported installation, the corrected helper's read-only inspection passed on
the connected camera with policy one and no memory writes.

## The policy belongs to fixed settings

The decoded main image contains complete default copies of the EEPROM banks:

| Component | Offset in `program` | Linked RAM address | Complete copied extent |
| --- | --- | --- | --- |
| `eep_ow_a` | `0x20000` | `0x03ea0000` | 128 KiB |
| `eep_ow_b` | `0x40000` | `0x03ec0000` | 128 KiB |
| `eep_adj` | `0x60000` | `0x03ee0000` | 128 KiB |
| `eep_fix` | `0x80000` | `0x03f00000` | 128 KiB |

Each complete default region equals its separate official component. The
verification policy is **`eep_fix + 0x1801a`**, or **`program + 0x9801a`**,
linked at `0x03f1801a`. It is a two-byte value whose low byte changes `0 → 1`.

Native bank loader `0x0426ad4e`, bank ID three, requests the entire fixed bank
from the firmware's virtual flash address `0x40e00000` into `0x03f00000`.
The actual byte-read wrapper is `0x041ffeca`. With a stored zero-policy bank,
this native reload overwrites a program shadow initially patched to one.
Consequently a program-only patch does not establish persistence.

The ordinary type-four update's fixed-bank preparation at
`0x04015370..0x040153f0` copies the existing identity fields at `0x1c020` and
`0x1c040`, plus sectors `0xbf` and `0xff`, into the incoming fixed-bank image.
Native tests verify the entire resulting bank and preserve all seven
owner-specific bytes differing from the official default. The policy at
`0x1801a` remains the incoming payload's value; it is outside those copied
fields and sectors.

The update record's destination `0x1a40000` is relative to a storage boundary
at `0xc40000`. Native instructions at `0x0401555a` subtract that boundary and
convert the resulting `0xe00000` byte offset to **512-byte sector `0x7000`**.
This agrees with the fixed-bank read API's `0x40e00000` virtual address. These
are flash-driver coordinates, not demonstrated raw CPU/USB memory mappings.

The [persistence verifier](../tools/gx9_policy_persistence_verify.py) executes
that native preparation and update-transfer sequence, the sector wrappers,
and a fresh native bank reload. Its simulated controller completes 256 sectors
for each bank transfer. The new policy remains one after reload into fresh RAM;
an injected first-transfer error propagates as failure. Controller completions,
locks and logging are modeled. NAND erasure, ECC, bad-block translation and
power-loss behavior are not emulated. See the
[persistence evidence](../evidence/gx9-policy-persistence.json).

## Other native updater controls

The [route verifier](../tools/gx9_update_route_verify.py) establishes separate
stages using the original 1.4 ARM code:

- A synthetic 8 KiB container with one clear component completes the full native
  parser under policy one, including when its plaintext digest is deliberately
  wrong. A bad body CRC still fails. The same fixture fails its signature under
  policy zero.
- With a controlled current-version parameter `0x140`, the original 1.4 header
  is rejected, the original 1.5 header is accepted, and changing the header type
  to zero permits the same version. A mismatched model remains rejected.
- The main C runtime's native scatter initialization copies/clears all six
  declared ranges correctly. Both initial policy zero and one survive that
  stage. Execution stops before entering ThreadX; this is not a complete boot.

No CRC, SHA-256 or signature check is mocked in those parser controls. C
copy/zero helpers are modeled. The scatter helpers themselves execute natively.
[Route evidence](../evidence/gx9-update-route-controls.json) records all results.

## Prepared research candidate

The corrected local artifact is
`work/gx9-policy-one-candidate-v14-20261109-2/gx9-v14-policy-one.research-upd`.
It was transferred to the owner's PC, then renamed without changing its bytes
to `GX7M3V14.bin` for the Japanese DC-GX7MK3. The owner reports that the camera
recognized and installed it. Japanese and global official 1.5 payloads were
independently downloaded and compared byte-for-byte before choosing this
regional filename; see the [filename comparison](gx9-postflash-policy.md).

| Property | Result |
| --- | --- |
| Package size | 102,538,240 bytes; original full 1.4 layout retained |
| Package SHA-256 | `719fc4e4daeb17f09172e7ac59675fdc0a637376a73284e814f9a9b266aa6883` |
| Changed plaintext | One byte in `program`, one byte in `eep_fix`, representing the same policy |
| Other nonempty components | All 33 stored payloads byte-identical to official 1.4 |
| Full decode checks | All 35 nonempty component digests match the rebuilt directory |
| Encryption control | Re-encoding both original components reproduces their official ciphertext byte-for-byte |
| Version handling | Advertised UPD revision `0x140 → 0x141`; program version bytes unchanged |
| Update type | Original type four retained, including its identity-preservation path |
| Native checks | Model/version accepts; policy-one directory gate accepts |
| Signature | Original signature intentionally fails for changed metadata; policy one would be required |
| Installation/boot | Owner reports successful manual installation and working camera; subsequent physical USB reads verify policy one |

The first program-only candidate is superseded by the fixed-bank reload
finding. The corrected [builder](../tools/gx9_policy_candidate.py) requires the
physical policy capture, checks the native persistence controls, regenerates
both encrypted components, validates every full component digest and restricts
outputs to a fresh directory under `work/`. Raw key values and proprietary
firmware bytes are excluded from its report and publication.
[Candidate evidence](../evidence/gx9-policy-candidate.json) records its exact
inputs, changes and validation limits.

## SD and protocol leads

| Route | Evidence so far | Unresolved step |
| --- | --- | --- |
| USB | Absolute RAM writes and the policy round trip are measured; native dispatcher reproduces all 14 saved replies; fixed bank is area `0x22` | Queued event `0x000e8202` remains to be traced to an updater or persistent-save action |
| SD update | Owner reports successful installation and boot; subsequent physical USB inspection verifies policy one | Full installed-image readback and an additional controlled power-cycle test have not been performed |
| Alternate SD update / `.AHX` | Native selection of `a:\MC282.upd` / `a:\MC282e.upd` reaches the updater; decoded key predicate verified | Physical entry/buttons, media behavior and arbitrary SD code boot remain unproven |
| Wi-Fi | Internal ICC/NWA/PSM command route and all 26 HTTP modes execute in native emulation; adding `event=60` leaves `getinfo` mode unchanged | External delivery of Linux event 60 and updater-related subtypes remain unproven |
| Bluetooth | Eight service definitions / 34 characteristics extracted; named factory callbacks execute as four-byte test counters | Other callbacks, pairing and external-to-RTOS delivery remain unresolved; no system updater identified |

The extracted Linux init script runs internal `/etc/init.d/S??*` entries. A
literal scan of all extracted regular files found only `RAID_AUTORUN` in
`strace` for the autorun term; that is not an SD execution hook. Absence of a
literal filename does not rule out other boot paths.

Subsequent [alternate update-path controls](gx9-sd-update-route.md) execute the
model-tag construction, filename formatting and `e`-file preference in native
ARM code. They stop before the updater and preserve an initially enabled policy
within that routine. This is an update-file route, not a demonstrated arbitrary
SD boot mechanism or a verified USB-to-SD handoff.

Bluetooth startup loads `mtk_stp_bt` and `mtkbt`. The separate `btteststart`
script loads the MT6630 radio patch from `/lib/firmware` and starts `bt_drv`;
that patch concerns the radio, not the camera's main firmware. The test driver
contains `/tmp/hcicmd_socket`; the camera BT application contains GATT
product/factory-advertising paths and `/tmp/unix_sockstream_nwa`. These are
internal protocol leads, not a demonstrated remotely reachable shell or flasher.

The [Bluetooth protocol analysis](gx9-bluetooth-protocol.md) now records the
product/factory UUID tables and nine native counter controls. The named factory
read/write functions are test counters; their names do not imply arbitrary
memory or persistent storage access. The application's direct process calls
reviewed so far belong to radio-test handling.

The [Wi-Fi mode decoder controls](gx9-wifi-mode-decoder.md) execute the original
PSM query extractor and table lookup. All 26 listed modes pass. `linux_cmd`,
`firmware` and numeric `60` are unrecognized as mode names, while an added
`event=60` parameter leaves `getinfo` selected. These are decoder controls,
not execution of the requested command or exclusion of other subtypes.

The [native USB protocol analysis](gx9-usb-native-protocol.md) now identifies
the maintenance descriptor builder, all 256 first-dispatch routes, settings
shadow access, stored-bank selection and several commands queued to another
task. It reproduces the old area-`0x20` read failure and identifies `0x22` as
the fixed-bank selector. The helper's fixed-shadow read is now physically
verified at area `0x22`, index `0xc00d`; the post-flash inspection performed no
write or queued updater command.
