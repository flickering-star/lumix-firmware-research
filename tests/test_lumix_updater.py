"""Host workflow refusals: these tests never open USB or use camera firmware."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from zipfile import BadZipFile

from apps.lumix_updater.camera import Inspection
from apps.lumix_updater.download import checked_firmware, sha
from apps.lumix_updater.protocol import (ProtocolError, Service, checksum,
                                         policy_packet, read_packet, read_reply)
from apps.lumix_updater.workflow import Workflow


def inspection(policy=1):
    return Inspection('DMC-GM5', 'offline-test', 0x100, 0x111,
                      policy, policy, bytes(range(16)))


class ProtocolTests(unittest.TestCase):
    def test_read_bounds_reject_without_sending(self):
        for address in (True, -1024, 1, 0xFFFFFC00, 0x100000000):
            with self.subTest(address=address), self.assertRaises(ProtocolError):
                read_packet(address)

    def test_exact_policy_store_is_fixed_halfword(self):
        raw=policy_packet(0)
        self.assertEqual(raw[:4],bytes.fromhex('0800ff9c'))
        self.assertEqual(struct.unpack_from('<IH',raw,4),(0x70A68490,0))
        self.assertEqual(raw[10:14],bytes(4))
        self.assertEqual(raw[-2],sum(raw[1:-2])&255)
        for value in (True,-1,2,65536):
            with self.subTest(value=value), self.assertRaises(ProtocolError):policy_packet(value)

    def test_truncated_corrupt_and_echo_memory_replies_are_refused(self):
        request=read_packet(0x40000000)
        reply=bytearray(request);reply[:4]=bytes.fromhex('0100ff05');reply[-2]=checksum(reply)
        class Echo:
            def exchange(self,*_):return bytes(reply)
        with self.assertRaisesRegex(ProtocolError,'not replaced'):Service(Echo(),{0x40000000}).read(0x40000000)
        for bad in (bytes(reply[:-1]),bytes(reply[:-2])+bytes(2),bytes(1030)):
            with self.subTest(length=len(bad)), self.assertRaises(ProtocolError):read_reply(bad)

    def test_read_allowlist_refuses_before_transport(self):
        class Never:
            def exchange(self,*_):raise AssertionError('Unexpected transport access')
        with self.assertRaises(ProtocolError):Service(Never(),{0x40000000}).read(0x40000400)

    def test_arbitrary_firmware_is_rejected(self):
        for raw in (b'',b'UPD\0'+bytes(2048),b'PK\x03\x04'):
            with self.subTest(length=len(raw)), self.assertRaises((ValueError,BadZipFile)):
                checked_firmware(raw)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.workflow=Workflow(transport_factory=self.no_camera,codec_factory=lambda:object())
        self.workflow.inspection=inspection()
        self.data={'stable':b'candidate-file','luts':b'lut-file','restore':b'stock-file'}

    def tearDown(self):self.temp.cleanup()

    @staticmethod
    def no_camera():raise AssertionError('This host workflow test must never open a camera')

    def fake_build(self,raw,key,codec,choice,**kwargs):
        data=self.data[choice]
        return data,dict(choice=choice,sha256=sha(data),limitations=['Test limitation'])

    def prepare(self,name='ready',choice='stable'):
        with patch('apps.lumix_updater.workflow.load_local',return_value=b'official-input'), \
             patch('apps.lumix_updater.workflow.build',side_effect=self.fake_build):
            return self.workflow.prepare(choice,self.root/name,local_firmware='official.bin')

    def test_preparation_and_card_are_required_before_enable(self):
        for prepared in (False,True):
            if prepared:self.prepare()
            with self.subTest(prepared=prepared), self.assertRaises(ValueError):
                self.workflow.enable(card_inserted_with_power_off=False)

    def test_verified_build_contains_restore_and_limitations_without_private_key(self):
        report=self.prepare()
        self.assertEqual(self.workflow.verify_output().read_bytes(),self.data['stable'])
        root=self.workflow.output
        self.assertEqual((root/'stock-restore/GM5__V11.bin').read_bytes(),self.data['restore'])
        text=(root/'NEXT-STEPS.txt').read_text()
        self.assertIn('service mode',text);self.assertIn('Test limitation',text)
        self.assertIn('stock-restore/GM5__V11.bin',(root/'SHA256SUMS').read_text())
        self.assertNotIn(self.workflow.inspection.key.hex(),(root/'preparation.json').read_text())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),['ready'])
        self.assertFalse(report['automatic_camera_flash'])

    def test_detected_profile_selects_both_candidate_and_restore(self):
        for version,profile in ((0x0110,'gm5-official-0110'),(0x0111,'gm5-factory-0111')):
            with self.subTest(profile=profile):
                self.workflow.inspection=Inspection('DMC-GM5','offline-test',0x100,
                    version,1,1,bytes(range(16)))
                with patch('apps.lumix_updater.workflow.load_local',return_value=b'official-input'), \
                     patch('apps.lumix_updater.workflow.build',side_effect=self.fake_build) as builder:
                    report=self.workflow.prepare('stable',self.root/profile,local_firmware='official.bin')
                self.assertEqual([c.kwargs['camera_profile'] for c in builder.call_args_list],[profile,profile])
                self.assertEqual(report['camera']['profile'],profile)
                self.assertEqual(report['camera']['internal_revision'],f'{version:04x}')

    def test_modified_rom_instructions_do_not_require_usb_write(self):
        self.workflow.inspection=inspection(0)
        report=self.prepare()
        self.assertFalse(report['temporary_flag_needed'])
        self.assertIn('USB is not required',self.workflow.instructions(report))
        self.assertNotIn('Enable this update',self.workflow.instructions(report))

    def test_changed_or_removed_candidate_cannot_enable(self):
        self.prepare();file=self.workflow.output/'GM5__V11.bin'
        for change in ('modified','missing'):
            if change=='modified':file.write_bytes(b'changed')
            else:file.unlink()
            with self.subTest(change=change), self.assertRaisesRegex(ValueError,'changed or is missing'):
                self.workflow.enable(card_inserted_with_power_off=True)

    def test_failed_second_prepare_invalidates_old_readiness(self):
        self.prepare()
        with patch('apps.lumix_updater.workflow.load_local',side_effect=ValueError('bad input')):
            with self.assertRaisesRegex(ValueError,'bad input'):
                self.workflow.prepare('luts',self.root/'second',local_firmware='bad.bin')
        self.assertIsNone(self.workflow.output);self.assertIsNone(self.workflow.manifest)
        self.assertFalse((self.root/'second').exists())
        with self.assertRaises(ValueError):self.workflow.enable(card_inserted_with_power_off=True)

    def test_failed_reread_invalidates_old_readiness(self):
        self.prepare()
        with patch('apps.lumix_updater.workflow.inspect_camera',side_effect=ValueError('disconnected')):
            with self.assertRaisesRegex(ValueError,'disconnected'):self.workflow.inspect()
        self.assertIsNone(self.workflow.inspection);self.assertIsNone(self.workflow.output)
        with self.assertRaises(ValueError):self.workflow.enable(card_inserted_with_power_off=True)

    def test_failed_save_publishes_nothing_and_removes_temporary_files(self):
        original=Path.write_text
        def fail(path,*args,**kwargs):
            if path.name=='NEXT-STEPS.txt':raise OSError('disk full')
            return original(path,*args,**kwargs)
        with patch.object(Path,'write_text',fail):
            with self.assertRaisesRegex(OSError,'disk full'):self.prepare()
        self.assertEqual(list(self.root.iterdir()),[])
        self.assertIsNone(self.workflow.output)

    def test_existing_destination_is_retained(self):
        destination=self.root/'ready';destination.mkdir();(destination/'keep.txt').write_text('keep')
        with self.assertRaises(FileExistsError):self.prepare()
        self.assertEqual((destination/'keep.txt').read_text(),'keep')
        self.assertFalse((destination/'GM5__V11.bin').exists())

    def test_enable_is_explicit_and_uses_original_inspection(self):
        self.prepare()
        with patch('apps.lumix_updater.workflow.enable_update',return_value={'wrote_ram':True}) as enable:
            result=self.workflow.enable(card_inserted_with_power_off=True)
        self.assertTrue(result['wrote_ram']);self.assertTrue(self.workflow.enabled)
        self.assertIs(enable.call_args.args[0],self.workflow.inspection)


if __name__=='__main__':unittest.main()
