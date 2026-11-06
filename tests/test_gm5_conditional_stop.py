"""Register-conditional boundaries allow native same-task transitions."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_emulator import put, run_scenario

BACKEND = ROOT/"work/toolchain/gdb-mn10300-build/gm5-mn103-sim-cooperative_stops"


@unittest.skipUnless(BACKEND.is_file(), "Requires separately built cooperative_stops backend")
class ConditionalStopTests(unittest.TestCase):
    def scenario(self, different=False, mode="fast"):
        return {"name": "register_conditional_stop", "maps": [[0x70000000,0x10000]], "images": [],
                "memory": [put(0x70008000,bytes.fromhex("802acbff"))],
                "registers": {"pc":0x70008000,"sp":0x7000E000,"a0":0x1122,"a1":0x2233 if different else 0x1122},
                "stops":{"returned":0x70008003},"stops_if_registers_differ":[
                    {"label":"different_context","address":0x70008002,"left":"a0","right":"a1"}],
                "execution_mode":mode,"budget":10,"trace_every":1}

    def test_equal_registers_continue_different_registers_stop_in_both_modes(self):
        for different in (False,True):
            results,traces=[],[]
            with self.subTest(different=different), tempfile.TemporaryDirectory() as temporary:
                for mode in ("fast","step"):
                    directory=Path(temporary)/mode
                    result=run_scenario(self.scenario(different,mode),BACKEND,directory)["result"]
                    self.assertEqual(result["stop"],"different_context" if different else "returned")
                    self.assertEqual(result["steps"],1 if different else 2)
                    self.assertEqual(int(result["registers"][0],0),42)
                    results.append(result);traces.append((directory/"trace.jsonl").read_bytes())
                self.assertEqual(results[0],results[1]);self.assertEqual(traces[0],traces[1])

    def test_unsupported_registers_and_duplicate_labels_are_rejected(self):
        for field,value in (("left","unknown"),("label","returned")):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as temporary:
                spec=self.scenario();spec["stops_if_registers_differ"][0][field]=value
                with self.assertRaises(ValueError):run_scenario(spec,BACKEND,Path(temporary)/"run")


if __name__ == "__main__":unittest.main()
