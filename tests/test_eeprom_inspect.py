"""Check EEPROM word units, malformed captures and meaningful snapshot diffs."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


spec = importlib.util.spec_from_file_location(
    "eeprom_inspect", Path(__file__).parents[1] / "tools/eeprom_inspect.py")
eeprom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eeprom)


def fixture(words=None, start=0):
    if words is None:
        words = [0] * 16 + [0x0100, 0, 0x270f, 0x6363, 0x270f, 0x6363] + [0] * 10
    lines = ["###### EEPROM DATA INFORMATION ######",
             "#@1:10     : AREA          : UPDATE ",
             "#@2:00     : TYPE          : ROM ",
             f"#@3:{start:04x}   : START ADDRESS : 0x{start:04x}h ",
             f"#@4:{len(words):04x}   : DATA SIZE    : 0x{len(words):04x}h ",
             "#####################################",
             " ".join(f"L{i:x}" for i in range(16))]
    for at in range(0, len(words), 16):
        lines.append(f"H{(start + at) // 16:03x} " + "".join(f"{w:04x}," for w in words[at:at + 16]))
    return ("\r\n".join(lines) + "\r\n").encode()


class EepromTests(unittest.TestCase):
    def test_word_count_and_language_coordinate_are_not_text_offsets(self):
        table = dict(eeprom.parse(fixture(start=0x100)), model="GM1")
        report = eeprom.inspect(table)
        self.assertEqual(report["word_count"], 32)
        self.assertEqual(report["decoded_bytes"], 64)
        marker = report["language_pattern_candidates"][0]
        self.assertEqual((marker["row"], marker["column"]), ("H011", "L0"))
        self.assertEqual(marker["export_word_address"], 0x110)
        self.assertEqual(marker["relative_byte_offset"], 32)
        self.assertEqual(marker["value_hex"], "0100")

    def test_missing_duplicate_and_malformed_rows_are_rejected(self):
        data = fixture()
        for bad in (data.rsplit(b"H001", 1)[0],
                    data.replace(b"H001", b"H000"),
                    data.replace(b"0100,", b"010,"),
                    data + data.splitlines(keepends=True)[-1]):
            with self.subTest(bad=bad[-30:]), self.assertRaises(ValueError):
                eeprom.parse(bad)

    def test_metadata_range_and_address_space_changes_are_rejected(self):
        for old, new in ((b"0x0020h", b"0x0030h"), (b"#@2:00", b"#@2:01"),
                         (b"#@1:10", b"#@1:20"), (b"#@3:0000", b"#@3:ffff")):
            with self.subTest(new=new), self.assertRaises(ValueError):
                eeprom.parse(fixture().replace(old, new))

    def test_compare_pinpoints_one_changed_language_byte_and_rejects_cross_model(self):
        before = dict(eeprom.parse(fixture().replace(b"0100,", b"0000,")), model="GM1")
        after = dict(eeprom.parse(fixture()), model="GM1")
        difference = eeprom.compare(before, after)
        self.assertEqual(difference["changed_words"], 1)
        self.assertEqual(difference["changes"][0], {
            "export_word_address": 16, "row": "H001", "column": "L0",
            "before_hex": "0000", "after_hex": "0100", "xor_hex": "0100"})
        with self.assertRaisesRegex(ValueError, "model"):
            eeprom.compare(before, dict(after, model="GM5"))

    def test_zip_selects_tables_without_extracting_card_databases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PRIVATE.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("GM1U.TXT", fixture())
                archive.writestr("PRIVATE/PANA_GRP/FILEINFO.TBL", b"not EEPROM")
            tables = eeprom.load_tables(path)
            self.assertEqual(list(tables), ["GM1U"])
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["PRIVATE.zip"])
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("nested/GM1U.TXT", fixture())
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                eeprom.load_tables(path)

    def test_string_contents_are_omitted_and_byte_order_is_explicit(self):
        words = [int.from_bytes(b"debug!"[i:i + 2], "little") for i in range(0, 6, 2)] + [0] * 13
        table = dict(eeprom.parse(fixture(words)), model="GM1")
        report = eeprom.inspect(table)
        self.assertNotIn("words", report)
        hit = report["word_serializations"]["little"]["diagnostic_keyword_hits"][0]
        self.assertEqual(hit, {"keyword": "debug", "encoding": "ascii", "relative_byte_offset": 0})
        self.assertEqual(report["word_serializations"]["big"]["diagnostic_keyword_hits"], [])


if __name__ == "__main__":
    unittest.main()
