"""Public LUT recipe guards; no camera or private images are required."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from gm5_lut_package import LAYOUT, PACKAGE_SHA, RECIPE, components, edits, official


class LUTRecipeTests(unittest.TestCase):
    def test_disjoint_exact_preimages_and_untouched_bytes(self):
        source=bytes(range(16))
        records=[dict(offset=1,before='0102',after='aabb'),dict(offset=12,before='0c',after='ff')]
        result=edits(source,records)
        self.assertEqual(result,bytes.fromhex('00aabb030405060708090a0bff0d0e0f'))
        self.assertEqual(source,bytes(range(16)))

    def test_unknown_overlap_unbounded_and_malformed_edits_are_refused(self):
        cases=[
            [dict(offset=-1,before='00',after='01')],
            [dict(offset=True,before='00',after='01')],
            [dict(offset=0,before='',after='')],
            [dict(offset=0,before='00',after='0102')],
            [dict(offset=0,before='ff',after='01')],
            [dict(offset=16,before='00',after='01')],
            [dict(offset=0,before='00'*257,after='01'*257)],
            [dict(offset=0,before='0001',after='ffff'),dict(offset=1,before='01',after='ff')],
        ]
        for records in cases:
            with self.subTest(records=records),self.assertRaises(ValueError):edits(bytes(range(16)),records)

    def test_committed_recipe_is_bounded_and_has_exact_program_geometry(self):
        recipe=json.loads(RECIPE.read_text())
        self.assertEqual(recipe['package_sha256'],PACKAGE_SHA)
        self.assertEqual(recipe['package_bytes'],24118784)
        self.assertFalse(recipe['full_firmware_or_key_included'])
        for part,layout in zip(recipe['components'],LAYOUT):
            self.assertEqual((part['name'],part['destination'],part['bytes'],part['write_bytes']),layout)
            end=0
            for edit in part['edits']:
                before,after=bytes.fromhex(edit['before']),bytes.fromhex(edit['after'])
                self.assertTrue(0<len(before)<=256)
                self.assertEqual(len(before),len(after))
                self.assertGreaterEqual(edit['offset'],end)
                end=edit['offset']+len(before)
                self.assertLessEqual(end,part['bytes'])
        self.assertEqual(len(recipe['accepted_main_baselines']),3)
        self.assertEqual(recipe['saved_lut_banks'],[
            dict(offset=0x7A0000,bytes=0x20000),dict(offset=0x7C0000,bytes=0x20000)])

    def test_incomplete_or_unknown_camera_backups_are_refused(self):
        recipe=json.loads(RECIPE.read_text())
        for raw in (b'',bytes(0x800000),bytes(0x2000000)):
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):components(raw,recipe)


if __name__=='__main__':unittest.main()
