"""Physical cipher oracle, exclusive-output guards and fixed package scope."""
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_reflash_control import assemble, validate_scope, DESTINATION, LENGTH


@unittest.skipUnless(shutil.which("clang"), "Requires clang")
class CipherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temporary.name)/"codec"
        subprocess.run(["clang", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(ROOT/"tools/panasonic_aes5.c"), "-o", str(cls.binary)],
                       check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_forward_inverse_nist_and_independent_camera_block(self):
        result = subprocess.run([str(self.binary), "--selftest"], check=True, capture_output=True, text=True)
        self.assertIn("Encryption/decryption: NIST", result.stdout)
        # Physical GM1 block, with a chosen IV and nonzero file offset. The
        # expected ciphertext is independent of the new encoder implementation.
        key = "350481b566d22d5b89dc46775e644622"
        vector = bytes.fromhex("cd6a60a6c34c6893a76ad12db4d8bdf2")
        ciphertext = bytes.fromhex("147069b0d8d7a35b439688d2b8e59278")
        iv = bytes(range(16))
        plaintext = bytes(a^b for a, b in zip(vector, iv))
        with tempfile.TemporaryDirectory() as directory:
            source, encoded, decoded = (Path(directory)/n for n in ("input", "encoded", "decoded"))
            source.write_bytes(b"prefix"+plaintext+b"suffix")
            subprocess.run([str(self.binary), "--encrypt", str(source), str(encoded), key,
                            iv.hex(), "6", "16"], check=True, capture_output=True)
            self.assertEqual(encoded.read_bytes(), ciphertext)
            subprocess.run([str(self.binary), str(encoded), str(decoded), key,
                            iv.hex(), "0", "16"], check=True, capture_output=True)
            self.assertEqual(decoded.read_bytes(), plaintext)

    def test_existing_output_and_invalid_ranges_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory)/"input", Path(directory)/"output"
            source.write_bytes(bytes(32))
            for mode in ([], ["--encrypt"]):
                target.write_bytes(b"keep")
                result = subprocess.run([str(self.binary), *mode, str(source), str(target), "00"*16,
                                         "00"*16, "0", "16"], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(target.read_bytes(), b"keep")
                target.unlink()
                for offset, size in (("0", "15"), ("0", "0"), ("17", "16"), ("-1", "16")):
                    result = subprocess.run([str(self.binary), *mode, str(source), str(target), "00"*16,
                                             "00"*16, offset, size], capture_output=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(target.exists())


@unittest.skipUnless((ROOT/"work/gm5-reflash-control-1/GM5__V11.bin").is_file(),
                     "Requires prepared private control package")
class PackageScopeTests(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT/"work/gm5-reflash-control-1/GM5__V11.bin").read_bytes()

    def test_exact_prepared_scope(self):
        entry = validate_scope(self.raw)
        self.assertEqual((entry["destination_offset_candidate"], entry["size"]), (DESTINATION, LENGTH))

    def test_valid_crc_cannot_hide_changed_destination_digest_flags_or_component(self):
        changes = ((0x2EC+20, struct.pack("<I", 0x1FA0000)),  # Settings bank.
                   (0x2EC+24, struct.pack("<I", 0)),
                   (0x2EC+28, bytes(32)),
                   (0x2EC, b"program\0"),
                   (0x348, b"x"))  # A hidden unused directory entry.
        for offset, value in changes:
            with self.subTest(offset=hex(offset)):
                changed = bytearray(self.raw)
                changed[offset:offset+len(value)] = value
                struct.pack_into("<I", changed, 0x40, zlib.crc32(changed[0x200:]))
                with self.assertRaises(ValueError): validate_scope(bytes(changed))

    def test_unknown_template_or_changed_installed_code_cannot_be_packed(self):
        official = ROOT/"firmware/official-gm5-v11/GM5__V11.bin"
        if not official.is_file(): self.skipTest("Requires retained official image")
        with self.assertRaisesRegex(ValueError, "template"):
            assemble(bytes(0x600), b"", b"")
        with self.assertRaisesRegex(ValueError, "unchanged installed"):
            assemble(official.read_bytes(), bytes(LENGTH), bytes(LENGTH))


if __name__ == "__main__":
    unittest.main()
