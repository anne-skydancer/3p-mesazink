import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import package_support as ps

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root/'source.dll'; self.src.write_bytes(b'new-build')
        self.out = self.root/'out'
        self.capture = patch.object(ps, 'capture', return_value='test-version')
        self.capture.start(); self.addCleanup(self.capture.stop)
    def assemble(self, relocate=None):
        ps.assemble(self.out, [(self.src,'bin/release/test.dll')], {}, {}, relocate)
    def test_newer_stale_destination_replaced_and_hashes_match(self):
        dest=self.out/'bin/release/test.dll'; dest.parent.mkdir(parents=True)
        dest.write_bytes(b'old'); import os; os.utime(dest, (2100000000,2100000000))
        self.assemble(); self.assertEqual(dest.read_bytes(), b'new-build')
        self.assertEqual(ps.verify(self.out)['payload']['bin/release/test.dll'], ps.sha256(self.src))
    def test_version_metadata_does_not_claim_another_dependency_file(self):
        self.out.mkdir()
        shared_version = self.out / 'VERSION.txt'
        shared_version.write_text('soloud-version')
        self.assemble()
        self.assertEqual(shared_version.read_text(), 'soloud-version')
        self.assertEqual((self.out / 'mesazink-version.txt').read_text().strip(), ps.PACKAGE_VERSION)
        self.assertNotIn('VERSION.txt', ps.verify(self.out)['payload'])
        import xml.etree.ElementTree as ET
        strings = [node.text for node in ET.parse(ps.ROOT / 'autobuild.xml').iter('string')]
        self.assertNotIn('VERSION.txt', strings)
        self.assertEqual(strings.count('mesazink-version.txt'), 3)
    def test_repeat_has_new_generation(self):
        self.assemble(); old=ps.verify(self.out)['generation']
        self.assemble(); self.assertNotEqual(old, ps.verify(self.out)['generation'])
    def test_failure_invalidates_prior_success(self):
        self.assemble(); self.src.unlink()
        with self.assertRaises(RuntimeError): self.assemble()
        self.assertFalse((self.out/ps.MARKER).exists())
    def test_compile_failure_cannot_leave_success_marker(self):
        self.assemble(); ps.begin(self.out)
        with self.assertRaises(FileNotFoundError): ps.verify(self.out)
    def test_corruption_rejected(self):
        self.assemble(); (self.out/'bin/release/test.dll').write_bytes(b'corrupt')
        with self.assertRaises(RuntimeError): ps.verify(self.out)
    def test_relocation_records_both_hashes(self):
        def relocate(stage): (stage/'bin/release/test.dll').write_bytes(b'relocated')
        self.assemble(relocate); result=ps.verify(self.out)
        self.assertNotEqual(result['source_hashes'], result['payload'])
        self.assertEqual(result['source_hashes']['bin/release/test.dll'],ps.sha256(self.src))
    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            ps.assemble(self.out,[(self.src,'../bad')],{},{})
    def test_compatible_build_reconfigures_changed_options(self):
        build=self.root/'build';build.mkdir();(build/'build.ninja').touch()
        commands=[]
        with patch.object(ps,'capture', return_value=json.dumps([{'name':'llvm','value':'disabled'}])):
            config=ps.configure(self.root,build,['-Dllvm=disabled'],commands.append)
        self.assertIn('--reconfigure',commands[0]); self.assertIn('-Dllvm=disabled',commands[0])
        self.assertEqual(config['effective']['llvm'],'disabled')
    def test_configuration_mismatch_fails(self):
        with patch.object(ps,'capture',return_value=json.dumps([{'name':'llvm','value':'enabled'}])):
            with self.assertRaises(RuntimeError):
                ps.configure(self.root,self.root/'build',['-Dllvm=disabled'],lambda command:None)
    def test_incompatible_compiler_isolated(self):
        self.assertNotEqual(ps.build_directory(self.root,'build',{'compiler':'a'}),
                            ps.build_directory(self.root,'build',{'compiler':'b'}))

    def test_promotion_rejects_mismatched_recipe(self):
        good={'platform':'linux','version':ps.PACKAGE_VERSION,'revision':ps.MESA_REVISION,'patches':{},'recipe':ps.recipe_identity()}
        other=dict(good,platform='win32',recipe='wrong')
        with patch.object(ps,'verify_archive',side_effect=[good,other]):
            with self.assertRaises(RuntimeError): ps.verify_pair(['linux','windows'])
    def test_promotion_requires_both_platforms(self):
        with patch.object(ps,'verify_archive',return_value={'platform':'linux'}):
            with self.assertRaises(RuntimeError): ps.verify_pair(['linux','also-linux'])
    def test_recipe_ignores_checkout_line_endings(self):
        a=self.root/'a';b=self.root/'b';a.write_bytes(b'a\nb\n');b.write_bytes(b'a\r\nb\r\n')
        self.assertEqual(ps.source_hash(a),ps.source_hash(b))

    def test_subproject_static_library_checked_through_targets(self):
        targets=[{'subproject':'zlib','type':'static library'}]
        with patch.object(ps,'capture',side_effect=['[]',json.dumps(targets)]):
            result=ps.configure(self.root,self.root/'b',['-Dzlib:default_library=static'],lambda c:None)
        self.assertEqual(result['effective']['zlib:default_library'],'static')
        targets[0]['type']='shared library'
        with patch.object(ps,'capture',side_effect=['[]',json.dumps(targets)]):
            with self.assertRaises(RuntimeError):
                ps.configure(self.root,self.root/'b',['-Dzlib:default_library=static'],lambda c:None)

    def archive(self, extra=False):
        import io, tarfile, zstandard
        self.assemble()
        memory=io.BytesIO()
        with tarfile.open(fileobj=memory,mode='w') as tar:
            for path in self.out.rglob('*'):
                if path.is_file(): tar.add(path,arcname=path.relative_to(self.out).as_posix())
            if extra:
                data=b'unexpected';member=tarfile.TarInfo('bin/release/extra.dll');member.size=len(data)
                tar.addfile(member,io.BytesIO(data))
        result=self.root/'package.tar.zst'
        result.write_bytes(zstandard.ZstdCompressor().compress(memory.getvalue()))
        return result
    def test_archive_checks_exact_payload(self):
        package=ps.verify_archive(self.archive())
        self.assertEqual(package['version'],ps.PACKAGE_VERSION)
    def test_archive_rejects_untracked_runtime(self):
        with self.assertRaises(RuntimeError): ps.verify_archive(self.archive(extra=True))

if __name__=='__main__': unittest.main()
