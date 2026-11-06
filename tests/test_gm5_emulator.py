import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_emulator import DEFAULT_BACKEND, header_scenario, run_scenario, updater_tests


@unittest.skipUnless((ROOT/DEFAULT_BACKEND).exists(), "Build GNU AM33-2 harness first")
class EmulatorTests(unittest.TestCase):
    def scenario(self, code, *, budget=20):
        return {"schema": 1, "name": "cpu_guard", "maps": [[0x1000, 4096], [0x70000000, 4096]],
                "images": [], "memory": [{"address": 0x1000, "hex": code}],
                "registers": {"pc": 0x1000, "sp": 0x70000800}, "stops": {}, "budget": budget}

    def execute(self, spec):
        with tempfile.TemporaryDirectory() as directory:
            return run_scenario(spec, ROOT/DEFAULT_BACKEND, Path(directory)/"run")["result"]

    def test_host_syscall_is_stopped_before_execution(self):
        for mode in ("step", "fast"):
            with self.subTest(mode=mode):
                spec = dict(self.scenario("f0c0"), execution_mode=mode)
                result = self.execute(spec)
                self.assertEqual(result["stop"], "unmodeled_host_syscall")
                self.assertEqual(result["steps"], 0)
                self.assertEqual(result["pc"], "0x00001000")

    def test_unmapped_hardware_read_raises_target_exception(self):
        for mode in ("step", "fast"):
            with self.subTest(mode=mode):
                result = self.execute(dict(self.scenario("fca80000009c"), execution_mode=mode))
                self.assertEqual(result["stop"], "target_exception")
                self.assertNotEqual(result["signal"], 0)

    def test_infinite_native_branch_stops_at_step_budget(self):
        for mode in ("step", "fast"):
            with self.subTest(mode=mode):
                result = self.execute(dict(self.scenario("ca00", budget=8), execution_mode=mode))
                self.assertEqual(result["stop"], "budget_exhausted")
                self.assertEqual(result["steps"], 8)

    def test_stop_reports_exact_boundary_after_a_nonbranch_instruction(self):
        for mode in ("step", "fast"):
            result = self.execute(dict(self.scenario("8001ff"), execution_mode=mode))
            self.assertEqual(result["stop"], "target_break")
            self.assertEqual(result["pc"], "0x00001002")
            self.assertEqual(result["steps"], 1)

    def test_short_swap_aliases_match_gnu_long_forms_and_preserve_flags(self):
        for mode in ("step", "fast"):
            for name, short_base, long_byte in (("swap", 0x80, 0xCB), ("swaph", 0x90, 0xDB)):
                for source in range(4):
                    for destination in range(4):
                        results = []
                        value = (0, 0xFFFFFFFF, 0x800100FE, 0x12345678)[source]
                        expected = int.from_bytes(value.to_bytes(4, "little"), "big") if name == "swap" else ((value & 0x00FF00FF)<<8 | (value & 0xFF00FF00)>>8)
                        for code in (bytes([0xF6, short_base | source<<2 | destination, 0xFF]),
                                     bytes([0xF9, long_byte, (source+12)<<4 | destination+12, 0xFF])):
                            with self.subTest(mode=mode, instruction=name, source=source, destination=destination, code=code.hex()):
                                spec = dict(self.scenario(code.hex()), execution_mode=mode)
                                spec["registers"].update({f"d{i}": 0x11111111*(i+1) for i in range(4)})
                                spec["registers"].update({f"d{source}": value, "psw": 0x10000F})
                                result = self.execute(spec)
                                self.assertEqual(result["stop"], "target_break")
                                self.assertEqual(int(result["registers"][destination], 0), expected)
                                self.assertEqual(result["registers"][11], "0x0010000f")
                                results.append(result["registers"][:9]+result["registers"][10:])
                        self.assertEqual(*results)

    def test_fast_native_header_matches_step_trace_registers_and_stack(self):
        image = (ROOT/"firmware/official-gm5-v11/GM5__V11.bin").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            outputs = []
            for mode in ("step", "fast"):
                out = Path(directory)/mode
                spec = header_scenario("differential_header", image[:512])
                spec["execution_mode"] = mode
                spec["dumps"] = [{"name": "stack.data", "address": 0x700EF000, "size": 0x2000}]
                result = run_scenario(spec, ROOT/DEFAULT_BACKEND, out)["result"]
                self.assertEqual(result["stop"], "returned")
                outputs.append((result, (out/"trace.jsonl").read_bytes(), (out/"stack.data").read_bytes()))
            self.assertEqual(*outputs)

    def test_native_updater_policy_and_call_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            report = updater_tests(ROOT/DEFAULT_BACKEND, Path(directory)/"controls")
            self.assertEqual(report["passed"], 16)
            self.assertFalse(report["camera_contacted"])


if __name__ == "__main__":
    unittest.main()
