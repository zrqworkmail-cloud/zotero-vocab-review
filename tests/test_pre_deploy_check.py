"""The pre-deploy gate: source-only files and genuinely new modules.

A rollback snapshot cannot contain a module that did not exist before deployment.
The manifest records those pending files so the gate can distinguish them from a
missing backup, and the rollback recipe removes them explicitly.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'pre_deploy_check', ROOT / 'tools' / 'pre-deploy-check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class PreDeploySnapshot(unittest.TestCase):
    def test_source_only_modules_are_not_deployed(self):
        self.assertIn('kyle_books.py', check.INTENTIONALLY_ABSENT)
        self.assertIn('kyle_enrich.py', check.INTENTIONALLY_ABSENT)

    def test_new_source_files_records_new_modules_and_skips_source_only(self):
        source = {
            'old.py': Path('old.py'),
            'new.py': Path('new.py'),
            'domain/new.py': Path('domain/new.py'),
            'kyle_books.py': Path('kyle_books.py'),
            'kyle_enrich.py': Path('kyle_enrich.py'),
        }
        installed = {'old.py': Path('old.py')}
        self.assertEqual(check.new_source_files(source, installed),
                         ['domain/new.py', 'new.py'])

    def test_apply_records_pending_modules_and_rollback_lists_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / 'repo'
            source = repo / 'anki-global-addon' / 'zotero_global_capture'
            installed = root / 'installed'
            (source / 'domain').mkdir(parents=True)
            installed.mkdir()
            (source / 'old.py').write_text('old', encoding='utf-8')
            (source / 'new.py').write_text('new', encoding='utf-8')
            (source / 'domain' / 'new.py').write_text('domain', encoding='utf-8')
            (source / 'kyle_books.py').write_text('source only', encoding='utf-8')
            (source / 'kyle_enrich.py').write_text('source only', encoding='utf-8')
            (installed / 'old.py').write_text('old', encoding='utf-8')
            (installed / 'config.json').write_text('{}', encoding='utf-8')

            with mock.patch.multiple(check, REPO=repo, SRC=source,
                                     run=(lambda *a, **k: (0, 'head'))), \
                 mock.patch.object(check, 'installed_dir', return_value=installed), \
                 mock.patch.object(check, 'check_counts', return_value={
                     'counts': {'cards': 1}, 'fingerprint': 'abc', 'scope': 'test'}):
                applied = check.create_backup()
                manifest = json.loads(
                    (Path(applied['backup']) / 'manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(manifest['new_files'], ['domain/new.py', 'new.py'])
                backup, rollback = check.check_backup()

            self.assertTrue(backup['ok'])
            self.assertEqual(backup['new_files'], ['domain/new.py', 'new.py'])
            self.assertEqual(backup['missing_from_backup'], [])
            self.assertIn('remove files added by this deployment', '\n'.join(rollback['steps']))


if __name__ == '__main__':
    unittest.main()
