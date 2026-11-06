"""Native reads/writes through the two GM5 RAM views share one backing store."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_emulator import put, run_scenario
from gm5_rtos_emulator import BACKEND


@unittest.skipUnless((ROOT/BACKEND).is_file(), "Requires separately built rtos_aliases backend")
class RamAliasTests(unittest.TestCase):
    def spec(self, reverse=False, mode="fast"):
        return {"name": "ram_alias_coherence", "maps": [[0x70000000, 0x10000]], "images": [],
                "ram_aliases": [{"address": 0x70000000, "size": 0x10000, "alias": 0xB0000000}],
                "memory": [put(0x70008000, bytes.fromhex("6075ff"))],
                "registers": {"pc": 0x70008000, "sp": 0x7000E000, "d0": 0x11223344,
                              "a0": 0x70001000 if reverse else 0xB0001000,
                              "a1": 0xB0001000 if reverse else 0x70001000},
                "stops": {"returned": 0x70008002}, "execution_mode": mode, "budget": 10, "trace_every": 1,
                "memory_observations": [{"label": "shared_word", "address": 0x70001000, "size": 4}],
                "dumps": [{"name": "normal.data", "address": 0x70001000, "size": 4},
                          {"name": "alias.data", "address": 0xB0001000, "size": 4}]}

    def check_coherence(self, reverse):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results, traces = [], []
            for mode in ("fast", "step"):
                directory = root/mode
                result = run_scenario(self.spec(reverse, mode), ROOT/BACKEND, directory)
                self.assertEqual(result["result"]["stop"], "returned")
                self.assertEqual(int(result["result"]["registers"][1], 0), 0x11223344)
                self.assertEqual((directory/"normal.data").read_bytes(), bytes.fromhex("44332211"))
                self.assertEqual((directory/"alias.data").read_bytes(), bytes.fromhex("44332211"))
                events = [json.loads(line) for line in (directory/"trace.jsonl").read_text().splitlines()]
                changes = [event for event in events if event.get("event") == "memory_change"]
                self.assertEqual(len(changes), 1)
                self.assertEqual((changes[0]["instruction_pc"], changes[0]["after"]), ("0x70008000", "44332211"))
                results.append(result["result"]); traces.append(events)
            self.assertEqual(results[0], results[1]); self.assertEqual(traces[0], traces[1])

    def test_alias_write_is_visible_to_normal_read_and_observer(self):
        self.check_coherence(False)

    def test_normal_write_is_visible_to_alias_read_and_observer(self):
        self.check_coherence(True)

    def test_frontend_refuses_device_aliases_missing_maps_and_overlap(self):
        for aliases in (
                [{"address": 0x40000000, "size": 4, "alias": 0x80000000}],
                [{"address": 0x70001000, "size": 4, "alias": 0xB0001000}],
                [{"address": 0x70000000, "size": 0x10000, "alias": 0xB0000001}],
                [{"address": 0x70000000, "size": 0x10000, "alias": 0xB0000000}]*2):
            with self.subTest(aliases=aliases), tempfile.TemporaryDirectory() as temporary:
                spec = self.spec(); spec["ram_aliases"] = aliases
                with self.assertRaises(ValueError):
                    run_scenario(spec, ROOT/BACKEND, Path(temporary)/"run")

    def test_backend_independently_refuses_non_ram_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            protocol = Path(temporary)/"scenario.protocol"
            protocol.write_text("RAM_ALIAS 0x40000000 4 0x80000000\nRUN\n")
            result = subprocess.run([str((ROOT/BACKEND).resolve()), str(protocol)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("RAM alias must pair bounded", result.stderr)


if __name__ == "__main__":
    unittest.main()
