import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('addon_builder', ROOT / 'anki-global-addon' / 'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class InstallerTests(unittest.TestCase):
    def test_user_files_are_excluded_from_both_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'zotero_global_capture'
            (source / 'user_files').mkdir(parents=True)
            (source / '__init__.py').write_text('')
            (source / 'user_files' / 'private.json').write_text('private')
            old = builder.ROOT, builder.SOURCE, builder.OUTPUT
            try:
                builder.ROOT, builder.SOURCE, builder.OUTPUT = root, source, root / 'dist' / 'addon.zip'
                builder.build()
                for path in (builder.OUTPUT, builder.OUTPUT.with_suffix('.ankiaddon')):
                    with ZipFile(path) as archive:
                        self.assertFalse(any('user_files' in name for name in archive.namelist()))
            finally:
                builder.ROOT, builder.SOURCE, builder.OUTPUT = old

    def test_flat_anki_installer_contains_manifest_and_excludes_runtime_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder.OUTPUT = Path(tmp) / 'zotero_global_capture.zip'
            builder.build()
            installer = builder.OUTPUT.with_suffix('.ankiaddon')
            with ZipFile(installer) as archive:
                names = set(archive.namelist())
                self.assertIsNone(archive.testzip())
                self.assertTrue({'manifest.json', '__init__.py', 'review_logic.py', 'review_popup.py', 'difficulty_store.py'} <= names)
                self.assertEqual(json.loads(archive.read('manifest.json'))['package'], 'zotero_global_capture')
                self.assertFalse(any('difficulty.json' in n or 'meta.json' in n or '__pycache__' in n for n in names))
            self.assertIn(installer.name, (Path(tmp) / 'SHA256SUMS').read_text())
