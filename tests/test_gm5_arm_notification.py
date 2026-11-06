"""The profiled ARM store changes memory only; unknown requests are refused."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"tools"))
from gm5_arm_emulator import ARM_IMAGE,run_scenario,scenario
from gm5_arm_notifications import request

AVAILABLE=all(importlib.util.find_spec(name)for name in("unicorn","capstone"))


class ArmNotificationTests(unittest.TestCase):
    @unittest.skipUnless(AVAILABLE and (ROOT/ARM_IMAGE).is_file(),"Requires ARM backend and retained private input")
    def test_actual_thumb_strh_preserves_cpu_flags_and_register_banks(self):
        with tempfile.TemporaryDirectory()as temporary:
            spec=scenario("native_arm_notification_store_semantics",0x70008000)
            spec["registers"].update(r0=0x70001000,r1=0x22330001,r4=0x12345678,cpsr=0xA0000013)
            spec["banked_registers"]={"irq":{"sp":0x11223344,"lr":0x55667788,"spsr":0x20000013}}
            spec["memory"]=[{"address":0x70008000,"hex":"018000bf"},{"address":0x70001000,"hex":"aabbccdd"}]
            spec["stops"]={"store_completed":0x70008002};spec["budget"]=2
            spec["dumps"]=[{"name":"word.data","address":0x70001000,"size":4}]
            directory=Path(temporary)/"native";r=run_scenario(spec,directory)["result"]
            self.assertEqual((r["stop"],r["instructions_started"]),("store_completed",1))
            self.assertEqual((directory/"word.data").read_bytes(),bytes.fromhex("0100ccdd"))
            for name,value in spec["registers"].items():
                expected=0x70008002 if name=="pc"else value|0x20 if name=="cpsr"else value
                self.assertEqual(int(r["registers"][name],0),expected)
            for name,value in spec["banked_registers"]["irq"].items():self.assertEqual(int(r["banked_registers"]["irq"][name],0),value)

    @unittest.skipUnless((ROOT/ARM_IMAGE).is_file(),"Requires pinned private ARM image")
    def test_only_pinned_native_pc_bytes_and_operands_are_recorded(self):
        image=(ROOT/ARM_IMAGE).read_bytes()
        good={"pc":"0x23f68","registers":{"cpsr":"0x33","r0":"0x9c013006","r1":"0x1"}}
        event=request(good,image);self.assertEqual(event["continuation_pc"],"0x23f6a")
        self.assertFalse(event["interrupt_delivered"]);self.assertFalse(event["peer_acknowledgement_supplied"])
        other=copy.deepcopy(good);other["pc"]="0x23bd0";request(other,image)
        for field,value in (("pc","0x23f66"),("r0","0x9c013008"),("r1","2"),("cpsr","0x13")):
            bad=copy.deepcopy(good)
            if field=="pc":bad[field]=value
            else:bad["registers"][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):request(bad,image)
        with self.assertRaises(ValueError):request(good,bytes(len(image)))


if __name__=="__main__":unittest.main()
