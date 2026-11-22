import struct
import unittest

from apps.lumix_updater.languages import PROFILES, apply_languages


class LanguageCatalogTest(unittest.TestCase):
    def fixture(self, model):
        profile = PROFILES[model]
        raw = bytearray(0x900000 if model == "DMC-GM1" else 0x800000)
        count = profile["catalog_bytes"] // 8 - 1
        # Deliberately use IDs outside the cameras' current0..25 range. The
        # implementation must take IDs and order from the catalog.
        ids = list(range(32, 32 + 2 * count, 2))[::-1]

        def write_list(address, entries):
            data = b"".join(struct.pack("<HBBI", value, 4, 0, 0) for value in entries)
            data += struct.pack("<HBBI", 65535, 0, 0, 0)
            raw[address - 0x40000000:address - 0x40000000 + len(data)] = data

        write_list(profile["master"], ids)
        operands = []
        for index in range(profile["regional_lists"]):
            target = 0x40700000 + 32 * index
            write_list(target, (ids[2 * index % count], ids[(2 * index + 1) % count]))
            for bounds, opcode in ((profile["normalizer"], b"\xfc\xdc"),
                                   (profile["menu"], b"\xfc\xdd")):
                address = bounds[0] + index * 6
                offset = address - 0x40000000
                raw[offset:offset + 6] = opcode + struct.pack("<I", target)
                operands.append(address + 2)
        raw[profile["hide"] - 0x40000000] = 0xC9
        for address, original, previous_unlock in profile["japanese"]:
            struct.pack_into("<I", raw, address - 0x40000000, previous_unlock)
        return bytes(raw), ids, operands

    def test_catalog_drives_every_region_without_a_language_id_list(self):
        for model, profile in PROFILES.items():
            with self.subTest(model=model):
                original, ids, operands = self.fixture(model)
                changed, metadata = apply_languages(original, model)
                self.assertEqual(metadata["language_ids"], ids)
                for address in operands:
                    self.assertEqual(struct.unpack_from("<I", changed, address - 0x40000000)[0],
                                     profile["master"])
                offset = profile["master"] - 0x40000000
                self.assertEqual(changed[offset:offset + profile["catalog_bytes"]],
                                 original[offset:offset + profile["catalog_bytes"]])
                for address, target, _ in profile["japanese"]:
                    self.assertEqual(struct.unpack_from("<I", changed, address - 0x40000000)[0], target)
                repeated, report = apply_languages(changed, model)
                self.assertEqual(repeated, changed)
                self.assertEqual(report["edits"], [])

    def test_invalid_master_list_is_rejected(self):
        for model, profile in PROFILES.items():
            original, _, _ = self.fixture(model)
            raw = bytearray(original)
            raw[profile["master"] - 0x40000000 + 2] = 0
            with self.subTest(model=model), self.assertRaises(ValueError):
                apply_languages(raw, model)

    def test_missing_region_reference_is_rejected(self):
        for model, profile in PROFILES.items():
            original, _, operands = self.fixture(model)
            raw = bytearray(original)
            struct.pack_into("<I", raw, operands[0] - 0x40000000, 0)
            with self.subTest(model=model), self.assertRaises(ValueError):
                apply_languages(raw, model)

    def test_unsupported_model_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_languages(bytes(16), "DMC-GM1S")


if __name__ == "__main__":
    unittest.main()
