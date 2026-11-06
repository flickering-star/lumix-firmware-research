"""Execute native two-register completion polling, including stuck hardware."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_emulator import put, run_scenario
from gm5_native_rtos_controls import callback_trampoline
from gm5_region_emulator import SECONDARY, SECONDARY_SHA

BACKEND = ROOT/"work/toolchain/gdb-mn10300-build/gm5-mn103-sim-command_latches"


@unittest.skipUnless(BACKEND.exists() and (ROOT/SECONDARY).exists(), "Requires command_latches backend and retained secondary")
class CommandControllerTests(unittest.TestCase):
    def scenario(self, busy=2, stuck=0, mode="fast"):
        code = callback_trampoline(0x7BC8B9E4)
        return {"name": "native_completion_poll", "maps": [[0x70000000, 0x10000], [0x7BC00000, 0x360000]],
                "images": [{"path": str(ROOT/SECONDARY), "address": 0x7BC00000, "sha256": SECONDARY_SHA}],
                "memory": [put(0x70008000, code)], "registers": {"pc": 0x70008000, "sp": 0x7000E000},
                "command_controller": {"busy_reads": busy, "stuck_mask": stuck},
                "stops": {"returned": 0x70008000+len(code)-1}, "execution_mode": mode,
                "budget": 1000 if not stuck else 200, "trace_every": 1}

    def test_native_polls_complete_at_multiple_latencies_and_match_step_mode(self):
        for busy in (0, 1, 7):
            results = []
            with self.subTest(busy=busy), tempfile.TemporaryDirectory() as temporary:
                for mode in ("fast", "step"):
                    result = run_scenario(self.scenario(busy, mode=mode), BACKEND, Path(temporary)/mode)["result"]
                    self.assertEqual(result["stop"], "returned")
                    self.assertEqual(int(result["registers"][8], 0), 0x7000E000)
                    controller = result["command_controller"]
                    self.assertEqual((controller["starts"], controller["completions"], controller["pending"]), (2, 2, [False, False]))
                    results.append(result)
                self.assertEqual(results[0], results[1])

    def test_stuck_busy_does_not_fabricate_completion(self):
        for mask in (1, 2):
            with self.subTest(mask=mask), tempfile.TemporaryDirectory() as temporary:
                result = run_scenario(self.scenario(stuck=mask), BACKEND, Path(temporary)/"run")["result"]
                self.assertEqual(result["stop"], "budget_exhausted")
                self.assertTrue(result["command_controller"]["pending"][mask-1])
                self.assertLess(result["command_controller"]["completions"], 2)

    def test_unmodeled_values_and_bus_width_stop(self):
        for code, value, expected in (("f070ff", 1, "control_unmodeled_command"),
                                       ("f050ff", 16, "control_unsupported_access")):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temporary:
                spec = self.scenario();spec["memory"] = [put(0x70008000, bytes.fromhex(code))]
                spec["registers"].update(a0=0x9C010008, d0=value)
                spec["stops"] = {"returned": 0x70008002}
                result = run_scenario(spec, BACKEND, Path(temporary)/"run")["result"]
                self.assertEqual(result["stop"], expected)

    def test_adjacent_unreviewed_register_remains_unmapped(self):
        with tempfile.TemporaryDirectory() as temporary:
            spec = self.scenario();spec["memory"] = [put(0x70008000, bytes.fromhex("f060ff"))]
            spec["registers"]["a0"] = 0x9C01000A
            spec["stops"] = {"returned": 0x70008002}
            result = run_scenario(spec, BACKEND, Path(temporary)/"run")["result"]
            self.assertEqual(result["stop"], "target_exception")


if __name__ == "__main__":
    unittest.main()
