from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_emulator import DEFAULT_BACKEND
from gm5_virtual_install import BACKUP, control_tests


class NorModelTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("clang"), "Requires clang for sanitizer checks")
    def test_device_boundaries_status_programming_failure_and_power_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/"nor-model-test"
            adapter = ROOT/"tools/mn103_simulator"
            subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I", str(adapter),
                            str(ROOT/"tests/gm5_nor_model_test.c"), str(adapter/"nor_model.c"),
                            "-o", str(binary)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn("NOR behavioral controls passed", result.stdout)

    @unittest.skipUnless((ROOT/DEFAULT_BACKEND).exists() and (ROOT/BACKUP).exists(),
                         "Requires built simulator and private verified GM5 backup")
    def test_installed_native_writer_and_negative_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            report = control_tests(ROOT/DEFAULT_BACKEND, Path(directory)/"controls")
            self.assertEqual(report["passed"], 15)
            self.assertFalse(report["camera_contacted"])
            by_name = {case["name"]: case for case in report["controls"]}
            self.assertFalse(by_name["program_without_erase_masking"]["requested_data_readback_matches"])
            self.assertTrue(by_name["unsupported_sub_buffer_length"]["overrun_of_declared_length_detected"])
            self.assertEqual(by_name["range_program_failure"]["execution"]["result"]["registers"][0], "0x8000000c")


if __name__ == "__main__":
    unittest.main()
