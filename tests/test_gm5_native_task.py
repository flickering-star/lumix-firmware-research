"""Native saved-frame execution and refusal of invalid task continuations."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_emulator import sha
from gm5_region_emulator import SECONDARY
from gm5_task_emulator import execute_switch, inspect_switch

STATE = ROOT/"work/gm5-native-language-command-flow-5/native_parent_menu_entry/native_03"
BACKEND = ROOT/"work/toolchain/gdb-mn10300-build/gm5-mn103-sim-cooperative_stops"


@unittest.skipUnless(STATE.is_dir() and BACKEND.is_file() and (ROOT/SECONDARY).is_file(),
                     "Requires retained native task-switch boundary and CPU backend")
class NativeTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads((STATE/"report.json").read_text())["result"]
        cls.secondary = (ROOT/SECONDARY).read_bytes()

    def test_native_switch_preserves_storage_and_matches_in_both_execution_modes(self):
        results, traces = [], []
        with tempfile.TemporaryDirectory() as temporary:
            for mode in ("fast", "step"):
                suspended = {}
                output = Path(temporary)/mode
                event, record = execute_switch(STATE, self.result, self.secondary, BACKEND,
                                               output, suspended, execution_mode=mode)
                self.assertEqual((event["previous_task"]["id"], event["next_task"]["id"]), (7, 60))
                self.assertEqual(event["frame_kind"], "native_activation_frame")
                self.assertEqual(record["result"]["pc"], "0x7be02cda")
                self.assertEqual(int(record["result"]["registers"][6], 0), 0x40284F77)
                self.assertEqual(suspended[event["previous_task"]["tcb"]]["saved_sp"], 0x700EFF44)
                self.assertNotIn(event["next_task"]["tcb"], suspended)
                results.append(record["result"])
                traces.append((output/"trace.jsonl").read_bytes())
            self.assertEqual(results[0], results[1]); self.assertEqual(traces[0], traces[1])

    def test_unknown_code_pending_devices_and_unmapped_stack_are_refused(self):
        for change in ("code", "pc", "nor", "controller", "registers", "stack", "selected_task"):
            with self.subTest(change=change):
                result = copy.deepcopy(self.result); secondary = self.secondary
                if change == "code": secondary = secondary[:-1]+bytes([secondary[-1]^1])
                elif change == "pc": result["pc"] = "0x7be02f1c"
                elif change == "nor": result["nor"]["pending"] = 1
                elif change == "controller": result["command_controller"]["pending"] = [True, False]
                elif change == "registers": result["registers"][14] = "1"
                elif change == "stack": result["registers"][8] = "0x0"
                elif change == "selected_task":
                    result["registers"][4], result["registers"][5] = result["registers"][5], result["registers"][4]
                with self.assertRaises(ValueError): inspect_switch(STATE, result, secondary, {})

    def test_uninitialized_frame_and_changed_saved_frame_are_refused(self):
        event = inspect_switch(STATE, self.result, self.secondary, {})
        suspended = {event["next_task"]["tcb"]: {"saved_sp": event["incoming_sp"],
                                                      "frame_sha256": event["frame_sha256"]}}
        self.assertEqual(inspect_switch(STATE, self.result, self.secondary, suspended)["frame_kind"],
                         "previously_saved_by_native_switch")
        suspended[event["next_task"]["tcb"]]["frame_sha256"] = "0"*64
        with self.assertRaises(ValueError): inspect_switch(STATE, self.result, self.secondary, suspended)
        original = (STATE/"ram.data").read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory/"scenario.json").write_bytes((STATE/"scenario.json").read_bytes())
            for mutation in ("zero_sp", "wrong_entry"):
                ram = bytearray(original)
                if mutation == "zero_sp": struct.pack_into("<I", ram, event["next_stack_slot"]-0x70000000, 0)
                else: struct.pack_into("<I", ram, event["incoming_sp"]-0x70000000+4, 0x40001000)
                (directory/"ram.data").write_bytes(ram)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    inspect_switch(directory, self.result, self.secondary, {})
        self.assertEqual(sha((STATE/"ram.data").read_bytes()), sha(original))


if __name__ == "__main__": unittest.main()
