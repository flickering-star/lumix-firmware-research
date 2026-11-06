"""Current-image guards and native saved-language persistence controls."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_emulator import DEFAULT_BACKEND
from gm5_region_emulator import MAIN, candidate, dispatch, MENU_TABLE, NORMALIZER_TABLE, JP
from gm5_region_persistence import persistence


@unittest.skipUnless((ROOT/MAIN).exists(), "Requires verified private installed-main readback")
class RegionScopeTests(unittest.TestCase):
    def test_wrong_or_already_patched_main_is_rejected(self):
        original = (ROOT/MAIN).read_bytes()
        for data in (bytes(len(original)), candidate(original), bytes([original[0]^1])+original[1:]):
            with self.assertRaisesRegex(ValueError, "verified policy-zero"):
                candidate(data)

    def test_only_japanese_language_dispatch_changes_and_policy_zero_is_preserved(self):
        original = (ROOT/MAIN).read_bytes()
        result = candidate(original)
        for table in (MENU_TABLE, NORMALIZER_TABLE):
            old, new = dispatch(original, table), dispatch(result, table)
            self.assertEqual({k: v for k, v in old.items() if k != JP},
                             {k: v for k, v in new.items() if k != JP})
            self.assertNotEqual(old[JP], new[JP])
        self.assertEqual(result[0x6B1BDC:0x6B1BDE], b"\0\0")
        self.assertEqual(result[0x6A0:0x6B0], original[0x6A0:0x6B0])
        self.assertEqual(original[0xAA01D:0xAA01F], bytes.fromhex("c913"))
        self.assertEqual(result[0xAA01D:0xAA01F], bytes.fromhex("ca13"))


@unittest.skipUnless((ROOT/MAIN).exists() and (ROOT/DEFAULT_BACKEND).exists(),
                     "Requires current private images and built native simulator")
class RegionPersistenceTests(unittest.TestCase):
    def test_native_save_then_reload_resets_stock_english_and_retains_patched_english(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = persistence(root/"stock", ROOT/DEFAULT_BACKEND)
            modified = persistence(root/"unlocked", ROOT/DEFAULT_BACKEND, patch=True)
            self.assertEqual(original["final_settings_language"], 0)
            self.assertEqual(original["final_ui_language"], 0)
            self.assertEqual(modified["final_settings_language"], 1)
            self.assertEqual(modified["final_ui_language"], 1)
            a = (root/"stock/native_save/virtual-nor.bin").read_bytes()
            b = (root/"unlocked/native_save/virtual-nor.bin").read_bytes()
            self.assertEqual(a[0x1FA0000:], b[0x1FA0000:])
            self.assertEqual(a[0x1FA01B9], 1)
            original_ram = (root/"stock/native_reboot/ram.data").read_bytes()
            modified_ram = (root/"unlocked/native_reboot/ram.data").read_bytes()
            self.assertEqual(original_ram[0xA0E912], 0)
            self.assertEqual(modified_ram[0xA0E912], 4)
            self.assertTrue(original["all_save_changes_within_two_settings_banks"])
            self.assertTrue(modified["all_save_changes_within_two_settings_banks"])


if __name__ == "__main__":
    unittest.main()
