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
    def test_both_archives_include_domain_models_and_anki_connect(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output = builder.OUTPUT
            try:
                builder.OUTPUT = Path(tmp) / 'zotero_global_capture.zip'
                builder.build()
                zip_required = {
                    'zotero_global_capture/domain/__init__.py',
                    'zotero_global_capture/domain/models.py',
                    'zotero_global_capture/domain/grading.py',
                    'zotero_global_capture/anki_connect.py',
                    'zotero_global_capture/collection_queries.py',
                    'zotero_global_capture/ports.py',
                    'zotero_global_capture/vocabulary.py',
                    'zotero_global_capture/config_schema.py',
                    'zotero_global_capture/review_request.py',
                }
                installer_required = {
                    'domain/__init__.py',
                    'domain/models.py',
                    'domain/grading.py',
                    'anki_connect.py',
                    'collection_queries.py',
                    'ports.py',
                    'vocabulary.py',
                    'config_schema.py',
                    'review_request.py',
                }
                with ZipFile(builder.OUTPUT) as archive:
                    names = set(archive.namelist())
                    self.assertLessEqual(zip_required, names, sorted(zip_required - names))
                with ZipFile(builder.OUTPUT.with_suffix('.ankiaddon')) as archive:
                    names = set(archive.namelist())
                    self.assertLessEqual(installer_required, names, sorted(installer_required - names))
            finally:
                builder.OUTPUT = old_output

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

    def test_package_excludes_source_only_modules_and_declares_manifest_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output = builder.OUTPUT
            try:
                builder.OUTPUT = Path(tmp) / 'zotero_global_capture.zip'
                builder.build()
                for path in (builder.OUTPUT, builder.OUTPUT.with_suffix('.ankiaddon')):
                    with ZipFile(path) as archive:
                        names = set(archive.namelist())
                        self.assertFalse({'kyle_enrich.py', 'kyle_books.py'} & names)
                with ZipFile(builder.OUTPUT.with_suffix('.ankiaddon')) as archive:
                    manifest = json.loads(archive.read('manifest.json'))
                    self.assertEqual(manifest['human_version'], builder.ADDON_VERSION)
                    self.assertEqual(manifest['min_point_version'], builder.MIN_POINT_VERSION)
                    self.assertEqual(manifest['max_point_version'], builder.MAX_POINT_VERSION)
                self.assertTrue((builder.SOURCE / 'kyle_enrich.py').is_file())
                self.assertTrue((builder.SOURCE / 'kyle_books.py').is_file())
                repository = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(builder.ADDON_VERSION, repository['version'])
            finally:
                builder.OUTPUT = old_output
