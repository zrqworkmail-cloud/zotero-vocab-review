import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'difficulty_store.py'
spec = importlib.util.spec_from_file_location('difficulty_store', MODULE)
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)

class DifficultyTests(unittest.TestCase):
    def test_assistance_and_errors_increase_and_unassisted_success_reduces(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            store.record(path, 123, 1, 2, 1, 1)
            first = store.load(path)['123']
            self.assertGreater(first, 2)
            store.record(path, 123, 2, 4, 1, 1)
            self.assertGreater(store.load(path)['123'], first)
            store.record(path, 123, 0, 0, 0, 3)
            self.assertEqual(store.load(path)['123'], min(20, first + 10) - 1)

    def test_malformed_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            path.write_text('{broken', encoding='utf-8')
            with self.assertRaises(ValueError):
                store.record(path, 1, 1, 1, 1, 1)
            self.assertEqual(path.read_text(encoding='utf-8'), '{broken')
