"""Execute both native call conventions and detect the former double frame."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_emulator import DEFAULT_BACKEND, put, run_scenario, word
from gm5_native_rtos_controls import callback_trampoline
from gm5_region_persistence import call


@unittest.skipUnless((ROOT/DEFAULT_BACKEND).is_file(), "Requires built GNU AM33-2 simulator")
class CallbackAbiTests(unittest.TestCase):
    def execute(self, own_frame, *, wrong_call=False):
        entry, callback, stack, bad_return = 0x70008000, 0x70008100, 0x700F0000, 0x70008200
        # Both functions clobber d2/a2 and return42. The indirect-ABI version
        # saves d2/a2 and reserves12local bytes itself, as the real UI handler
        # does. The direct-ABI leaf relies on CALL's automatic frame.
        callee = (bytes.fromhex("cfa0f8fef4") if own_frame else b"")+bytes.fromhex("8a559a66802adfa014")
        code = (callback_trampoline(callback) if own_frame and not wrong_call
                else call(b"", callback, 0xA0, 20)+b"\xff")
        spec = {"schema": 1, "name": "callback_abi", "maps": [[0x70000000, 0x100000]], "images": [],
                "registers": {"pc": entry, "sp": stack, "d2": 0x22334455, "a2": 0x66778899},
                "memory": [put(entry, code), put(callback, callee), word(stack-20, bad_return)],
                "stops": {"returned": entry+len(code)-1, "stale_frame_return": bad_return},
                "budget": 100, "trace_every": 1, "execution_mode": "fast"}
        with tempfile.TemporaryDirectory() as temporary:
            record = run_scenario(spec, ROOT/DEFAULT_BACKEND, Path(temporary)/"run")
        return record["result"]

    def test_calls_callback_restores_its_own_frame_and_preserved_registers(self):
        result = self.execute(True)
        self.assertEqual(result["stop"], "returned")
        regs = [int(value, 0) for value in result["registers"]]
        self.assertEqual((regs[0], regs[2], regs[6], regs[8]), (42, 0x22334455, 0x66778899, 0x700F0000))

    def test_direct_call_leaf_uses_the_automatic_frame(self):
        result = self.execute(False)
        self.assertEqual(result["stop"], "returned")
        regs = [int(value, 0) for value in result["registers"]]
        self.assertEqual((regs[0], regs[2], regs[6], regs[8]), (42, 0x22334455, 0x66778899, 0x700F0000))

    def test_double_frame_cannot_be_mistaken_for_callback_success(self):
        result = self.execute(True, wrong_call=True)
        self.assertEqual(result["stop"], "stale_frame_return")
        self.assertEqual(int(result["registers"][8], 0), 0x700F0000-20)


if __name__ == "__main__":
    unittest.main()
