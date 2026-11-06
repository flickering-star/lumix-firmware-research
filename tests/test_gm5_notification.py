"""Bound the notification profile and verify the consumed MOVHU semantics."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
from gm5_emulator import DEFAULT_BACKEND, REGISTERS, put, run_scenario
from gm5_notify_emulator import request
from gm5_region_emulator import SECONDARY


class NotificationStoreTests(unittest.TestCase):
    @unittest.skipUnless((ROOT/DEFAULT_BACKEND).is_file(), "Requires built native CPU backend")
    def test_native_movhu_store_preserves_registers_and_psw_except_pc(self):
        registers = {"pc": 0x70008000, "sp": 0x7000E000, "d0": 0x11220002,
                     "d1": 0x55667788, "a0": 0x70001000, "mdr": 0xAABBCCDD, "psw": 0x307}
        spec = {"name": "notification_store_semantics", "maps": [[0x70000000, 0x10000]], "images": [],
                "memory": [put(0x70008000, bytes.fromhex("f070ff")), put(0x70001000, bytes.fromhex("aabbccdd"))],
                "registers": registers, "stops": {"returned": 0x70008002}, "budget": 4,
                "execution_mode": "fast", "trace_every": 1,
                "dumps": [{"name": "word.data", "address": 0x70001000, "size": 4}]}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)/"run"
            result = run_scenario(spec, ROOT/DEFAULT_BACKEND, directory)["result"]
            self.assertEqual(result["stop"], "returned")
            self.assertEqual((directory/"word.data").read_bytes(), bytes.fromhex("0200ccdd"))
            for name, value in registers.items():
                self.assertEqual(int(result["registers"][REGISTERS[name]], 0), 0x70008002 if name == "pc" else value)

    @unittest.skipUnless((ROOT/SECONDARY).is_file(), "Requires pinned private secondary")
    def test_only_reviewed_native_pc_register_and_value_are_consumed(self):
        secondary = (ROOT/SECONDARY).read_bytes()
        good = {"pc": "0x7bc7a63f", "registers": ["0x2", "0", "0", "0", "0x9c013004"]+["0"]*27}
        event = request(good, secondary)
        self.assertFalse(event["interrupt_delivered"])
        self.assertFalse(event["peer_acknowledgement_supplied"])
        self.assertEqual(event["continuation_pc"], "0x7bc7a641")
        third = {"pc": "0x7bc15408", "registers": ["1", "0", "0", "0", "0x9c013006"]+["0"]*27}
        self.assertEqual(request(third, secondary)["value"], 1)
        for pc, register, value in ((0x7BC7A640, 0x9C013004, 2), (0x7BC7A63F, 0x9C013002, 2),
                                     (0x7BC7A63F, 0x9C013004, 1)):
            bad = {"pc": hex(pc), "registers": [hex(value), "0", "0", "0", hex(register)]+["0"]*27}
            with self.subTest(pc=pc, register=register, value=value), self.assertRaises(ValueError):
                request(bad, secondary)
        with self.assertRaises(ValueError):
            request(good, bytes(len(secondary)))


if __name__ == "__main__":
    unittest.main()
