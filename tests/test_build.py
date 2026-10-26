import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('builder', ROOT / 'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
feed_spec = importlib.util.spec_from_file_location('feed', ROOT / 'tools/merge-update-feed.py')
feed = importlib.util.module_from_spec(feed_spec)
feed_spec.loader.exec_module(feed)


class ReleaseBuild(unittest.TestCase):
    def test_package_and_update_feed_agree_and_exclude_local_data(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            package = builder.build_release(ROOT, 'example/project', output)
            with ZipFile(package) as archive:
                self.assertEqual(set(archive.namelist()), set(builder.FILES))
                self.assertIsNone(archive.testzip())
                manifest = json.loads(archive.read('manifest.json'))
                self.assertIn('/example/project/', manifest['applications']['zotero']['update_url'])
                self.assertNotIn(b'verifyInZotero', archive.read('bootstrap.js'))
            updates = json.loads((output / 'updates-beta.json').read_text())
            entry = updates['addons'][manifest['applications']['zotero']['id']]['updates'][0]
            self.assertEqual(entry['version'], manifest['version'])
            self.assertEqual(entry['update_hash'], 'sha256:' + hashlib.sha256(package.read_bytes()).hexdigest())
            self.assertTrue(entry['update_link'].endswith('/' + package.name))
            self.assertEqual(entry['applications']['zotero']['strict_max_version'], '10.0.*')

    def test_repeated_builds_are_identical_and_source_manifest_is_not_changed(self):
        before = (ROOT / 'manifest.json').read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            a = builder.build_release(ROOT, 'example/project', Path(folder) / 'a').read_bytes()
            b = builder.build_release(ROOT, 'example/project', Path(folder) / 'b').read_bytes()
            self.assertEqual(a, b)
        self.assertEqual(before, (ROOT / 'manifest.json').read_bytes())

    def test_invalid_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                builder.build_release(ROOT, '../bad repo', Path(folder))

    def test_feed_merge_preserves_other_versions_and_addons(self):
        with tempfile.TemporaryDirectory() as folder:
            incoming, destination = Path(folder) / 'new.json', Path(folder) / 'existing.json'
            incoming.write_text(json.dumps({'addons': {'test': {'updates': [{'version': '2.0.0'}]}}}))
            destination.write_text(json.dumps({'addons': {'test': {'updates': [{'version': '1.0.0'}]}, 'other': {'updates': []}}}))
            feed.merge_feed(incoming, destination)
            result = json.loads(destination.read_text())['addons']
            self.assertEqual({entry['version'] for entry in result['test']['updates']}, {'1.0.0', '2.0.0'})
            self.assertIn('other', result)


if __name__ == '__main__':
    unittest.main()
