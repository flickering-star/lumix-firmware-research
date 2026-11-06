"""Exercise genuine ARM/Thumb instructions and preserve unexplained boundaries."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_arm_emulator import BACKUP, extract, run_scenario, scenario

AVAILABLE = all(importlib.util.find_spec(name) for name in ("unicorn", "capstone"))


@unittest.skipUnless(AVAILABLE and (ROOT/BACKUP).is_file(), "Requires pinned ARM-backend environment and private NOR backup")
class ArmEmulatorTests(unittest.TestCase):
    def test_native_thumb_returns_with_caller_bank_and_agrees_in_run_and_step_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            results, traces = [], []
            for mode in ("run", "step"):
                spec = scenario("native_arm_domain2", 0x23D22)
                spec["registers"].update(r0=0x800F, r4=0x12345678)
                spec["execution_mode"] = mode
                directory = Path(temporary)/mode
                result = run_scenario(spec, directory)["result"]
                self.assertEqual(result["stop"], "returned")
                self.assertEqual(int(result["registers"]["r0"], 0), 2)
                self.assertEqual(int(result["registers"]["sp"], 0), 0x7000E000)
                self.assertEqual(int(result["registers"]["lr"], 0), 0x7000FFF1)
                self.assertEqual(int(result["registers"]["r4"], 0), 0x12345678)
                self.assertTrue(int(result["registers"]["cpsr"], 0)&0x20)
                results.append(result); traces.append((directory/"trace.jsonl").read_bytes())
            self.assertEqual(results[0], results[1]); self.assertEqual(traces[0], traces[1])

    def test_native_arm_vector_blx_and_cp15_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            for name, entry, stop, expected_pc, thumb in (
                ("vector", 0, {"reset": 0x20}, 0x20, False),
                ("blx", 0x50, {"thumb_entry": 0x120}, 0x120, True),
                ("cp15", 0, {"unreachable": 0x7000FFF0}, 0x268, False),
            ):
                spec = scenario(name, entry, thumb=False); spec["stops"] = stop
                result = run_scenario(spec, Path(temporary)/name)["result"]
                self.assertEqual(result["stop"], "unmodeled_system_instruction" if name == "cp15" else next(iter(stop)))
                self.assertEqual(int(result["pc"], 0), expected_pc)
                self.assertEqual(bool(int(result["registers"]["cpsr"], 0)&0x20), thumb)
                self.assertEqual(int(result["registers"]["sp"], 0), 0x7000E000)

    def test_unknown_memory_faults_and_invalid_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            spec = scenario("unknown_arm_device", 0x70008000)
            spec["memory"] = [{"address": 0x70008000, "hex": "08687047"}]
            spec["registers"]["r1"] = 0x9C013006
            result = run_scenario(spec, Path(temporary)/"fault")["result"]
            self.assertEqual(result["stop"], "unmapped_or_protected_access")
            self.assertEqual(result["fault"]["address"], "0x9c013006")
            self.assertEqual(result["fault"]["instruction_pc"], "0x70008000")
            self.assertEqual(result["fault"]["bytes"], 4)
            for mutation in ("hash", "overlap", "extent"):
                spec = scenario(mutation, 0x23D22)
                if mutation == "hash": spec["images"][0]["sha256"] = "0"*64
                elif mutation == "overlap": spec["maps"].append([0, 0x1000])
                else: spec["maps"][0][1] = 17
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    run_scenario(spec, Path(temporary)/mutation)
        self.assertTrue(extract().is_file())


if __name__ == "__main__": unittest.main()
