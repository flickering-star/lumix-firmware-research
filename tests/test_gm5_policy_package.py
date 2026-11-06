"""Reject wrong installed inputs and CRC-valid changes outside the policy scope."""
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_policy_package import patched, validate, LENGTH, PATCH

SOURCE = ROOT/"work/gm5-emulator-installed-initializers-final/private-inputs/installed-program.bin"
PACKAGE = ROOT/"work/gm5-policy-zero-1/GM5__V11.bin"


@unittest.skipUnless(SOURCE.exists() and PACKAGE.exists(), "Requires private installed backup and prepared policy package")
class PolicyPackageTests(unittest.TestCase):
    def test_different_or_already_patched_input_cannot_be_used_as_installed_source(self):
        original = SOURCE.read_bytes()
        for wrong in (bytes(LENGTH), patched(original), bytes([original[0]^1])+original[1:]):
            with self.subTest(sha_prefix=wrong[:8].hex()):
                with self.assertRaisesRegex(ValueError, "exact installed"):
                    patched(wrong)
        self.assertEqual(original[PATCH:PATCH+2], b"\1\0")

    def test_valid_crc_cannot_redirect_or_expand_the_main_policy_candidate(self):
        raw = PACKAGE.read_bytes()
        expected = patched(SOURCE.read_bytes())
        validate(raw, expected)
        for offset, replacement in ((0x2EC+20, struct.pack("<I", 0x1FA0000)),
                                     (0x2EC+24, struct.pack("<I", 0)),
                                     (0x2EC+28, bytes(32)),
                                     (0x2EC, b"eep_ow_a\0"),
                                     (0x348, b"x")):
            with self.subTest(offset=hex(offset)):
                candidate = bytearray(raw)
                candidate[offset:offset+len(replacement)] = replacement
                struct.pack_into("<I", candidate, 0x40, zlib.crc32(candidate[0x200:]))
                with self.assertRaises(ValueError): validate(bytes(candidate), expected)


if __name__ == "__main__":
    unittest.main()
