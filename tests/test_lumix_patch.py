"""Hash guards and malformed recipes, using synthetic bytes only."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
from lumix_patch import apply_recipe, sha


class PatchRecipeTests(unittest.TestCase):
    def setUp(self):
        self.original = bytes(range(32))
        self.wanted = self.original[:4]+b"\xfe"+self.original[5:]
        self.recipe = {"schema": 1, "id": "synthetic", "model": "TEST", "input_bytes": 32,
                       "variants": [{"input_sha256": sha(self.original), "output_sha256": sha(self.wanted),
                                     "patches": [{"offset": "0x4", "before": "04", "after": "fe"}]}]}

    def test_exact_change_and_whole_input_digest(self):
        result, report = apply_recipe(self.original, self.recipe)
        self.assertEqual(result, self.wanted)
        self.assertFalse(report["camera_contacted"])
        with self.assertRaisesRegex(ValueError, "supported baseline"):
            apply_recipe(b"\xff"+self.original[1:], self.recipe)

    def test_preimage_and_complete_output_digest_are_independent_guards(self):
        for field, value, message in [("before", "05", "Original patch bytes"),
                                      ("output_sha256", "0"*64, "Output SHA-256")]:
            recipe = copy.deepcopy(self.recipe)
            variant = recipe["variants"][0]
            if field == "before":
                variant["patches"][0][field] = value
            else:
                variant[field] = value
            with self.assertRaisesRegex(ValueError, message):
                apply_recipe(self.original, recipe)

    def test_overlap_and_size_changes_are_rejected(self):
        for change in ("overlap", "size"):
            recipe = copy.deepcopy(self.recipe)
            edits = recipe["variants"][0]["patches"]
            if change == "overlap":
                edits.append(copy.deepcopy(edits[0]))
            else:
                edits[0]["after"] = "fefe"
            with self.assertRaisesRegex(ValueError, "Invalid or overlapping"):
                apply_recipe(self.original, recipe)


if __name__ == "__main__":
    unittest.main()
