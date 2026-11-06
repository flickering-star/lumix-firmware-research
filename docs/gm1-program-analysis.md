# GM1 plaintext, update decoder and directory signature

**All six components of the official GM1 1.1 update are decoded and match their
declared SHA-256 fields.** The complete main and secondary programs also equal
the independent physical USB captures byte for byte. Later live GM5 reads
recovered its own key and decoded all eight GM5 components; its directory
signature verifies with its own public key. The current priority is a verified
[GM5 flashing route](gm5-flashing.md); aspect-ratio work is deferred.

The [complete decoding report](../evidence/gm1-v11-decoded.json),
[main acquisition](../evidence/gm1-main-program.json) and
[secondary acquisition](../evidence/gm1-secondary-program.json) retain the
inputs, output hashes and physical comparison results. Decoded binaries remain
local in ignored `work/gm1-v11-decoded/`; they are not committed or repackaged.

## Cipher selector three: five-round AES-128-CBC

The secondary update job copies sixteen key bytes from **RAM `0x70007bdc`**
through call `0x7bd4a358` into update-context offset forty. Main startup copies
flash `0x405a3884..0x405ab54c` to RAM `0x70000000`, placing the key's original
bytes at **flash `0x405ab460`**, main-file offset `0x5ab460`:

```text
350481b566d22d5b89dc46775e644622
```

Version dispatch `0x7bd4971a` sends format `0x200` to handler `0x7bd4976b`.
Cipher selector three constructs the class at `0x40286c7a` with a 128-bit key.
Its decrypt initializer calls `0x4028767c`. Unlike the normal AES initializer
`0x40286fd5`, that routine divides the usual round count by two before expanding
the key. For AES-128, ten rounds become **five**. It uses the same AES key
expansion and block core, with a shortened round schedule; this is not a key
transformation and is not standard AES-128.

Each encrypted directory entry supplies its own sixteen-byte CBC IV at entry
offset sixty. Components contain whole blocks and are decoded without padding
removal. The first 64 decoded main-program bytes exactly matched the original
word-read sample. Full decoding then matched both complete physical programs
and every component's SHA-256:

| Component | Decoded bytes | SHA-256 |
| --- | ---: | --- |
| `program` | 9,437,184 | `a96fb6da618b33207db0d357ac5e2513583aaa71dd01df44bed498e63992fabe` |
| `guires` | 11,534,336 | `e8e364a8d6593d60941df82ebe7552b6eb4a200ccd115c8b92d081341a6fc48d` |
| `program2` | 3,538,944 | `7e8c7d96a95a505d5500fafbd076a56e95f27267708c1f02deb2606fcd304968` |
| `armcode` | 3,407,872 | `f9918698295c495373a41dcc8689c4faa05ac9aee8965ee2118ba29a3b1b1124` |
| `other` | 3,670,016 | `a2368124c44360d805968200249bd0f20172748a4b410ab6c2ae7454b2b07454` |
| `eep` | 393,216 | `9e7f1ea599b8ef41559a5911b6933d5c9ca2a5ee8c7199c2bd5ee3a36d2c5b5e` |

The original literal-key scans tested standard AES-128/256. Their negative
results are retained in the evidence; they did not test this reduced-round
cipher. The initializer key was present in the main program throughout.

The host [C decoder](../tools/panasonic_aes5.c) passes both the standard ten-round
NIST AES-128 block control and a five-round physical GM1 block control. The
[Python driver](../tools/panasonic_v2_decode.py) requires intact, pinned input
files and verifies each component before recording success. It never creates
an encoded update or flash image.

## CRC32, SHA-256 and ECDSA have different jobs

Outer digest selector three selects a **four-byte CRC32**, not SHA-256. Its
initial state is all ones, it updates through the reflected CRC table and
complements the final value. The existing container checks independently
reproduce the outer CRC over encoded body bytes from file offset `0x200`.

The component validator uses SHA-256 over decoded component data and compares
the result to the 32-byte directory field at entry offset twenty-eight.
Calls include `0x7bd49ba5 → 0x402885a1` (initialize),
`0x7bd49bc3 → 0x402887bf` (update), and
`0x7bd49c10 → 0x402888a4` (finish).

The directory has a **separate ECDSA P-256 signature**. The normal GM1 job
supplies the public-key profile `0x7be1cec0`; profile offset eighty-eight points
to the 64-byte public key at **`0x7be1ce64`**. The nearby string `ecdsa-p256`
agrees with the native arithmetic, but the conclusion does not rely on the
string alone.

At `0x7bd49a55`, the consumer hashes `76 + 92 × component_count` bytes from the
inner copied header: file **`0x2a0..0x514`** for six GM1 entries. At
`0x7bd49a7a`, it passes that digest, the public key and the signature from file
**`0x220..0x260`** to wrapper `0x40287a94`, reaching curve arithmetic at
`0x40014e8c`. A failed signature returns an update error before component decode.

The key coordinates and signature integers are stored as little-endian
32-byte values. The native verifier also treats the SHA-256 output as a
little-endian integer. With those conventions, the official GM1 signature
verifies both in an independent Python curve implementation and through
**LibreSSL 3.3.6**. One-bit changes to the hash or signature fail. See the
[signature evidence](../evidence/gm1-directory-signature.json) and
[offline verifier](../tools/panasonic_signature_verify.py).

Because the signed directory includes component hashes and IVs, decryption
does not establish the ability to make an accepted modified consumer update.
The recovered public key is for verification; no private signing key was found.

One branch can skip the signature for a zero first byte in the inner marker
when context offset ninety-two allows it. Job `0x7bd4a254` zero-initializes its
context, then sets this allowance at `0x7bd4a2ef` when runtime byte `0x70903814`
is zero. The meaning and writers of that runtime byte are still being traced.
The official `panasonic` marker follows the verified signature branch. This is
an explicit alternate unsigned-input mode in the code, not yet a demonstrated
camera bypass; the normal consumer's complete acceptance policy is unresolved.

## Separate factory programming path

`GM1.AHX` / `GM1E.AHX` have a different input consumer that parses S3 text into
a RAM staging buffer and reaches NOR erase/program routines. The
[factory-loader notes](factory-programming.md) record its entry and hardware
gates, source addresses and limits. Complete authentication/acceptance behavior
and a physical entry procedure remain under investigation. No factory image or
write attempt has been made.

## Reproduce the decoder and signature checks

Use a fresh output directory; existing artifacts are refused:

```sh
cc -O2 -std=c11 -Wall -Wextra -Werror tools/panasonic_aes5.c -o work/panasonic-aes5
python3 tools/panasonic_v2_decode.py firmware/official-gm1-v11/GM1__V11.bin --key-source captures/gm1-usb-resume-3atwz8co/result/program-main.bin --physical-secondary captures/gm1-usb-resume-fveg1az5/result/program2.bin --out work/gm1-v11-decoded-new
python3 tools/panasonic_signature_verify.py firmware/official-gm1-v11/GM1__V11.bin --gm1-secondary captures/gm1-usb-resume-fveg1az5/result/program2.bin --out work/gm1-signature-new.json
```

The same GM1-key decode attempt on the official GM5 image fails the first
component's SHA-256. Its partial candidate output in `work/gm5-v11-decoded/`
is **not validated plaintext**. The
[GM5 signature comparison](../evidence/gm5-against-gm1-signature-key.json) also
fails under GM1's public key. These are bounded cross-model negatives: they
do not identify GM5's cipher/key or establish that GM5 lacks authentication.

Those cross-model failures are preserved as history. Subsequent GM5 service
reads resolved its key and updater independently; the validated GM5 plaintext
is in `work/gm5-v11-decoded-verified/`. The older failed output named above
remains unsuitable for analysis.
