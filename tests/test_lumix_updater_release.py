"""Reject changed or unexpected files in the desktop release archives."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from lumix_updater_release_check import archive_catalog


class DesktopArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.patch=b'bounded-test-patch'
        part=dict(file='test.lxdp',patch_sha256=hashlib.sha256(self.patch).hexdigest())
        self.catalog=json.dumps(dict(schema=1,model='DMC-GM5',
            choices={name:dict(components=dict(program=part)) for name in ('stable','luts','restore')})).encode()
        self.digest=hashlib.sha256(self.catalog).hexdigest()
        self.prefix='App/_internal/apps/lumix_updater/patches/'

    def tearDown(self):self.temp.cleanup()

    def archive(self,*,catalog=None,patch=None,extra=()):
        p=self.root/'package.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr(self.prefix+'catalog.json',self.catalog if catalog is None else catalog)
            z.writestr(self.prefix+'test.lxdp',self.patch if patch is None else patch)
            for name,data in extra:z.writestr(name,data)
        return p

    def test_actual_shipped_catalog_and_delta_are_checked(self):
        result=archive_catalog(self.archive(),self.digest)
        self.assertEqual(result['catalog_sha256'],self.digest)
        self.assertEqual(result['patch_files'],{'test.lxdp':hashlib.sha256(self.patch).hexdigest()})

    def test_crc_valid_catalog_or_delta_replacement_is_refused(self):
        for kwargs in (dict(catalog=self.catalog+b' '),dict(patch=self.patch+b'changed')):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                archive_catalog(self.archive(**kwargs),self.digest)

    def test_undeclared_patch_file_is_refused(self):
        with self.assertRaisesRegex(ValueError,'Undeclared'):
            archive_catalog(self.archive(extra=[(self.prefix+'old-patch.lxdp',b'old')]),self.digest)

    def test_camera_binary_or_unsafe_member_is_refused(self):
        for name in ('App/GM5__V11.bin','App/flash.AHX','../outside.txt','/absolute.txt','App\\other.txt'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                archive_catalog(self.archive(extra=[(name,b'test')]),self.digest)


if __name__=='__main__':unittest.main()
