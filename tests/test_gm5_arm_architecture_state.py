"""Native bank changes and NEON state must survive separate probe stages."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from gm5_arm_emulator import BACKUP,run_scenario,scenario,restored_scenario,ARM_SIZE

AVAILABLE=all(importlib.util.find_spec(name)for name in ("unicorn","capstone"))


@unittest.skipUnless(AVAILABLE and (ROOT/BACKUP).is_file(),"Requires pinned ARM environment and private source")
class ArmArchitectureStateTests(unittest.TestCase):
    def test_native_fiq_irq_initialization_and_banks_survive_a_new_cpu(self):
        with tempfile.TemporaryDirectory()as temporary:
            spec=scenario("native_arm_bank_initializer",0x1A16E8,thumb=False)
            spec["registers"]["cpsr"]=0x93
            result=run_scenario(spec,Path(temporary)/"initialized")["result"]
            self.assertEqual(result["stop"],"returned")
            self.assertEqual(int(result["registers"]["sp"],0),0x7000E000)
            banks=result["banked_registers"]
            self.assertNotEqual(int(banks["fiq"]["sp"],0),0)
            self.assertEqual(int(banks["irq"]["sp"],0)-int(banks["fiq"]["sp"],0),0x400)
            # Exact native CPSR mode-change instructions, plus a MOV to observe
            # the IRQ stack and a return using the original Supervisor LR.
            code=bytes.fromhex("9200a0e300f021e10d10a0e19300a0e300f021e11eff2fe1")
            resume=scenario("observe_restored_irq_bank",0x70008000,thumb=False)
            resume["registers"]["cpsr"]=0x93
            resume["banked_registers"]=banks
            resume["memory"]=[{"address":0x70008000,"hex":code.hex()}]
            restored=run_scenario(resume,Path(temporary)/"restored")["result"]
            self.assertEqual(restored["stop"],"returned")
            self.assertEqual(restored["registers"]["r1"],banks["irq"]["sp"])
            self.assertEqual(restored["banked_registers"]["fiq"],banks["fiq"])
            self.assertEqual(restored["banked_registers"]["irq"],banks["irq"])
            self.assertEqual(int(restored["registers"]["sp"],0),0x7000E000)

    def test_native_fp_enable_and_neon_memory_clear_survive_state_restore(self):
        with tempfile.TemporaryDirectory()as temporary:
            spec=scenario("native_fp_enable",0x318,thumb=False)
            spec["registers"]["cpsr"]=0x93
            spec["native_fp_setup_profile"]=True
            spec["stops"]={"fp_ready":0x338}
            ready=run_scenario(spec,Path(temporary)/"enabled")["result"]
            self.assertEqual((ready["stop"],ready["instructions_started"]),("fp_ready",8))
            self.assertEqual(int(ready["floating_point_registers"]["fpexc"],0),0x40000000)
            for size in (127,128):
                results,traces=[],[]
                for mode in ("run","step"):
                    clear=scenario("native_neon_memory_clear",0x18A8,thumb=False)
                    clear["execution_mode"]=mode
                    clear["registers"].update(cpsr=0x93,r0=0x70001010,r1=size)
                    clear["floating_point_registers"]=dict(ready["floating_point_registers"])
                    for index in range(4):clear["floating_point_registers"][f"d{index}"]=hex(0x1122334455667788+index)
                    clear["memory"]=[{"address":0x70001000,"hex":(b"\xa5"*160).hex()}]
                    clear["dumps"]=[{"name":"buffer.data","address":0x70001000,"size":160}]
                    if size==128 and mode=="run":
                        clear["dumps"] += [{"name":"image.data","address":0,"size":ARM_SIZE},
                                           {"name":"scratch.data","address":0x70000000,"size":0x10000}]
                    directory=Path(temporary)/f"clear{size}_{mode}"
                    result=run_scenario(clear,directory)["result"]
                    self.assertEqual(result["stop"],"returned")
                    self.assertEqual((directory/"buffer.data").read_bytes(),b"\xa5"*16+bytes(size)+b"\xa5"*(144-size))
                    self.assertEqual(int(result["registers"]["sp"],0),0x7000E000)
                    for index in range(4):self.assertEqual(int(result["floating_point_registers"][f"d{index}"],0),0x1122334455667788+index)
                    results.append(result);traces.append((directory/"trace.jsonl").read_bytes())
                    if size==128 and mode=="run":
                        resumed=restored_scenario("exact_stopped_cpu_resume",directory)
                        resumed["stops"]={"restored_at_return":0x7000FFF0}
                        resumed_result=run_scenario(resumed,Path(temporary)/"resume")["result"]
                        self.assertEqual(resumed_result["stop"],"restored_at_return")
                        self.assertEqual(resumed_result["instructions_started"],0)
                        for field in ("registers","banked_registers","floating_point_registers"):
                            self.assertEqual(resumed_result[field],result[field])
                self.assertEqual(results[0],results[1]);self.assertEqual(traces[0],traces[1])
            disabled=scenario("native_neon_disabled_control",0x18A8,thumb=False)
            disabled["registers"].update(cpsr=0x93,r0=0x70001010,r1=128)
            failed=run_scenario(disabled,Path(temporary)/"disabled")["result"]
            self.assertEqual(failed["stop"],"cpu_exception")
            self.assertEqual(int(failed["pc"],0),0x18AC)

    def test_unreviewed_privileged_instructions_and_bad_state_are_refused(self):
        with tempfile.TemporaryDirectory()as temporary:
            for name,entry,patch in (("other_native",0x268,None),
                                      ("conditional",0x70008000,"d50f071e"),
                                      ("modified_profile",0x318,"500f11ee")):
                spec=scenario(name,entry,thumb=False)
                spec["native_fp_setup_profile"]=True
                if patch:spec["memory"]=[{"address":entry,"hex":patch}]
                result=run_scenario(spec,Path(temporary)/name)["result"]
                self.assertEqual(result["stop"],"unmodeled_system_instruction")
                self.assertEqual(result["instructions_started"],0)
            for name,fields in (("bank",{"banked_registers":{"monitor":{"sp":1}}}),
                                ("register",{"banked_registers":{"irq":{"r0":1}}}),
                                ("cpacr",{"floating_point_registers":{"cpacr":0xF00000}}),
                                ("fp",{"floating_point_registers":{"d0":1<<64}})):
                spec=scenario(name,0x23D22);spec.update(fields)
                with self.subTest(name=name),self.assertRaises(ValueError):run_scenario(spec,Path(temporary)/name)


if __name__=="__main__":unittest.main()
