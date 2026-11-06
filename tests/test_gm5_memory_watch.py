"""Observe real RAM changes without modifying CPU state or polling devices."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_emulator import run_scenario
BACKEND = ROOT/"work/toolchain/gdb-mn10300-build/gm5-mn103-sim-language_watch"


@unittest.skipUnless(BACKEND.exists(), "Build --variant language_watch")
class MemoryObservationTests(unittest.TestCase):
    def test_python_frontend_preserves_ram_observation_metadata_and_trace(self):
        spec = {"name": "frontend_observation", "maps": [[0x1000, 4096], [0x70000000, 4096]],
                "images": [], "memory": [{"address": 0x1000, "hex": "8001fc8200000070ff"}],
                "registers": {"pc": 0x1000, "sp": 0x70000800}, "stops": {}, "execution_mode": "fast", "budget": 10,
                "memory_observations": [{"label": "language", "address": 0x70000000, "size": 1}]}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"run"
            result = run_scenario(spec, BACKEND, output)
            self.assertEqual(result["memory_observations"], spec["memory_observations"])
            changes = [json.loads(line) for line in (output/"trace.jsonl").read_text().splitlines()
                       if '"event":"memory_change"' in line]
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["after"], "01")
        for observation in ({"label": "device", "address": 0x40000000, "size": 1},
                            {"label": "bad\nRUN", "address": 0x70000000, "size": 1},
                            {"label": "big", "address": 0x70000000, "size": 65}):
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(ValueError):
                    run_scenario(dict(spec, memory_observations=[observation]), BACKEND, Path(temporary)/"run")

    def execute(self, *, mode="fast", observe=True, budget=10, initial="0000", extra=""):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trace = root/"trace.jsonl"
            protocol = root/"scenario.protocol"
            commands = ["MAP 0x1000 4096", "MAP 0x70000000 4096",
                        "BYTES 0x1000 8001fc8200000070ff", "BYTES 0x70000000 "+initial,
                        "REG 9 0x1000", "REG 8 0x70000800", f"BUDGET {budget}",
                        f"MODE {mode}", "TRACE_EVERY 1", "TRACE "+str(trace)]
            if observe: commands.append("MEMWATCH 0x70000000 2 language")
            if extra: commands.append(extra)
            commands += ["RUN", "DUMP 0x70000000 16 "+str(root/"ram.data")]
            protocol.write_text("\n".join(commands)+"\n")
            execution = subprocess.run([str(BACKEND), str(protocol)], capture_output=True, text=True)
            events = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
            results = [json.loads(line) for line in execution.stdout.splitlines() if line.startswith('{"event":"result",')]
            return execution, events, results, (root/"ram.data").read_bytes() if (root/"ram.data").exists() else None

    def test_fast_and_step_report_the_actual_store_and_preserve_execution(self):
        observed = []
        for mode in ("fast", "step"):
            run, events, results, data = self.execute(mode=mode)
            self.assertEqual(run.returncode, 0, run.stderr)
            changes = [e for e in events if e.get("event") == "memory_change"]
            self.assertEqual(len(changes), 1)
            change = changes[0]
            self.assertEqual(change["instruction_pc"], "0x00001002")
            self.assertEqual(change["next_pc"], "0x00001008")
            self.assertEqual((change["before"], change["after"]), ("0000", "0100"))
            plain_run, plain_events, plain_result, plain_data = self.execute(mode=mode, observe=False)
            self.assertEqual(plain_run.returncode, 0)
            self.assertEqual((results, data), (plain_result, plain_data))
            self.assertEqual([e for e in events if e.get("event") != "memory_change"], plain_events)
            observed.append(change)
        self.assertEqual(*observed)

    def test_initial_values_and_same_value_stores_are_not_reported_as_changes(self):
        for mode in ("fast", "step"):
            run, events, _, data = self.execute(mode=mode, initial="0100")
            self.assertEqual(run.returncode, 0)
            self.assertFalse(any(e.get("event") == "memory_change" for e in events))
            self.assertEqual(data[:2], b"\1\0")

    def test_last_store_at_instruction_budget_is_still_observed(self):
        for mode in ("fast", "step"):
            run, events, results, data = self.execute(mode=mode, budget=2)
            self.assertEqual(run.returncode, 0)
            self.assertEqual(results[0]["stop"], "budget_exhausted")
            self.assertEqual(len([e for e in events if e.get("event") == "memory_change"]), 1)
            self.assertEqual(data[:2], b"\1\0")

    def test_mmio_nor_invalid_sizes_and_labels_are_rejected_before_execution(self):
        for command in ("MEMWATCH 0x40000000 1 nor", "MEMWATCH 0x9c000000 1 device",
                        "MEMWATCH 0x70000000 0 empty", "MEMWATCH 0x70000000 65 too_big",
                        "MEMWATCH 0x70ffffff 2 crosses_boundary", "MEMWATCH 0x70000000 1 bad-label"):
            with self.subTest(command=command):
                run, _, result, data = self.execute(extra=command)
                self.assertNotEqual(run.returncode, 0)
                self.assertEqual(result, [])
                self.assertIsNone(data)


if __name__ == "__main__":
    unittest.main()
