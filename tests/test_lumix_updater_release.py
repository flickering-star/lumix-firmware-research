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
            for name,data in extra:
                # ZipInfo normalizes the host's path separator on Windows.
                # Preserve the requested raw member name for refusal cases.
                info=zipfile.ZipInfo(name);info.filename=name
                z.writestr(info,data)
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

    def test_nested_model_catalog_and_deltas_are_pinned(self):
        child=json.loads(self.catalog);child['model']='DMC-GM1'
        child=json.dumps(child).encode();parent=json.loads(self.catalog)
        parent.update(models={'DMC-GM5':'.','DMC-GM1':'gm1'},
            model_catalog_sha256={'DMC-GM1':hashlib.sha256(child).hexdigest()})
        raw=json.dumps(parent).encode();digest=hashlib.sha256(raw).hexdigest()
        extra=[(self.prefix+'gm1/catalog.json',child),(self.prefix+'gm1/test.lxdp',self.patch)]
        result=archive_catalog(self.archive(catalog=raw,extra=extra),digest)
        self.assertIn('gm1/test.lxdp',result['patch_files'])
        extra[0]=(self.prefix+'gm1/catalog.json',child+b' ')
        with self.assertRaisesRegex(ValueError,'model catalog differs'):
            archive_catalog(self.archive(catalog=raw,extra=extra),digest)

    def test_profile_specific_restore_delta_is_checked_and_required(self):
        catalog=json.loads(self.catalog);restore=b'profile-specific-restore'
        catalog['restore_components_by_profile']={'gm5-official-0110':{
            'program':dict(file='factory-restore.lxdp',patch_sha256=hashlib.sha256(restore).hexdigest())}}
        raw=json.dumps(catalog).encode();digest=hashlib.sha256(raw).hexdigest()
        result=archive_catalog(self.archive(catalog=raw,extra=[(self.prefix+'factory-restore.lxdp',restore)]),digest)
        self.assertEqual(result['patch_files']['factory-restore.lxdp'],hashlib.sha256(restore).hexdigest())
        with self.assertRaisesRegex(ValueError,'Shipped delta differs'):
            archive_catalog(self.archive(catalog=raw,extra=[(self.prefix+'factory-restore.lxdp',restore+b'changed')]),digest)
        with self.assertRaisesRegex(ValueError,'Shipped delta differs'):
            archive_catalog(self.archive(catalog=raw),digest)


if __name__=='__main__':unittest.main()
