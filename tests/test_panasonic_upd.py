"""Exercise observed UPD bounds, corruption checks and the Olympus hypothesis."""
import importlib.util
from pathlib import Path
import struct
import unittest
import zlib


spec = importlib.util.spec_from_file_location(
    "panasonic_upd", Path(__file__).parents[1] / "tools/panasonic_upd.py")
upd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upd)


def refresh_crc(data):
    struct.pack_into("<I", data, 0x40, zlib.crc32(data[0x200:]))


def fixture():
    data = bytearray(0xA00)
    data[:4] = b"UPD\0"
    struct.pack_into("<II", data, 4, 0x200, 0x200)
    data[12:16] = b"GM5\0"
    struct.pack_into("<I", data, 0x3C, len(data) - 0x200)
    data[0x2A0:0x2E0] = data[:0x40]
    data[0x200:0x20C] = b"panasonic\0\0\0"
    struct.pack_into("<I", data, 0x2E8, 2)
    for index, (name, offset, destination) in enumerate([
        (b"program", 0x400, 0), (b"other", 0x600, 0x800)]):
        struct.pack_into("<12s4I32s16s16s", data, 0x2EC + index * 0x5C,
                         name, offset, 0x200, destination, 3,
                         bytes(32), bytes(16), bytes(16))
    data[0x600:] = bytes(range(256)) * 4
    refresh_crc(data)
    return data


class UpdTests(unittest.TestCase):
    def test_relative_offsets_and_holes_are_kept_distinct(self):
        data = fixture()
        report = upd.inspect(bytes(data), check_olympus=True)
        self.assertEqual(data, fixture())
        self.assertTrue(report["body_crc32_matches"])
        self.assertTrue(report["payloads_contiguously_cover_file_tail"])
        self.assertEqual(report["components"][1]["file_offset"], 0x800)
        self.assertEqual(report["components"][1]["destination_offset_candidate"], 0x800)
        hypothesis = report["destination_coverage_hypothesis"]
        self.assertEqual(hypothesis["payload_bytes"], 0x400)
        self.assertEqual(hypothesis["uncovered_ranges"][0],
                         {"start": 0x200, "end_exclusive": 0x800, "bytes": 0x600})
        self.assertFalse(report["components"][0]["field32_matches_encoded_sha256"])

    def test_corrupt_payload_and_truncation_are_rejected(self):
        data = fixture()
        data[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC32"):
            upd.parse(bytes(data))
        with self.assertRaisesRegex(ValueError, "length"):
            upd.parse(bytes(fixture()[:-16]))

    def test_bad_ranges_are_rejected_even_with_repaired_crc(self):
        for stored_offset in (0x100, 0x400, 0xA00):
            data = fixture()
            struct.pack_into("<I", data, 0x2EC + 0x5C + 12, stored_offset)
            refresh_crc(data)
            with self.subTest(offset=stored_offset), self.assertRaises(ValueError):
                upd.parse(bytes(data))
        data = fixture()
        struct.pack_into("<I", data, 0x2E8, 100)
        refresh_crc(data)
        with self.assertRaisesRegex(ValueError, "Directory count"):
            upd.parse(bytes(data))

    def test_unsupported_model_and_header_copy_are_rejected(self):
        for position in (12, 0x2AC):
            data = fixture()
            data[position] ^= 1
            refresh_crc(data)
            with self.subTest(position=position), self.assertRaises(ValueError):
                upd.parse(bytes(data))

    def test_unsigned_marker_requires_explicit_opt_in_and_intact_crc(self):
        original = fixture()
        expected = upd.parse(bytes(original))
        original[0x200] = 0
        refresh_crc(original)
        with self.assertRaisesRegex(ValueError, "marker"):
            upd.parse(bytes(original))
        self.assertEqual(upd.parse(bytes(original), allow_unsigned=True), expected)
        original[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC32"):
            upd.parse(bytes(original), allow_unsigned=True)
        original[0x201] ^= 1
        refresh_crc(original)
        with self.assertRaisesRegex(ValueError, "marker"):
            upd.parse(bytes(original), allow_unsigned=True)

    def test_olympus_known_vector_and_entropy_invariance(self):
        original = b"0123456789abcdef"
        decoded = upd.olympus_transform(original)
        self.assertEqual(decoded, bytes(x ^ 255 for x in b"13026475ba98decf"))
        self.assertEqual(upd.olympus_transform(decoded, inverse=True), original)
        data = bytes(range(256)) * 3 + bytes(16) * 20
        transformed = upd.olympus_transform(data)
        self.assertEqual(upd.statistics(data)["entropy_bits_per_byte"],
                         upd.statistics(transformed)["entropy_bits_per_byte"])
        self.assertEqual(upd.statistics(data)["zero_bytes"],
                         upd.statistics(transformed)["ff_bytes"])
        with self.assertRaises(ValueError):
            upd.olympus_transform(b"misaligned")


if __name__ == "__main__":
    unittest.main()
