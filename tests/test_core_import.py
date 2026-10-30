import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
package = types.ModuleType('zvr_core_test')
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location('zvr_core_test.core_import', ROOT / 'core_import.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CoreImportTest(unittest.TestCase):
    def test_adds_only_missing_words_and_is_repeatable(self):
        original = module.data
        module.data = lambda: {'cet6': ['existing', 'newword', 'unknown'], 'cet4_overlap': ['newword'],
                               'dictionary': {'newword': {'meaning': '新词', 'phonetic': 'sound'}}}
        notes = [{'noteId': 1, 'fields': {'Front': {'value': 'existing'}}}]
        added = []
        def api(action, params):
            if action == 'getActiveProfile': return 'profile'
            if action == 'modelFieldNames': return ['Front', 'Back', '音标']
            if action == 'findNotes': return [note['noteId'] for note in notes]
            if action == 'notesInfo': return notes
            if action == 'createDeck': return 1
            if action == 'addNote':
                n = params['note']; added.append(n)
                notes.append({'noteId': len(notes)+1, 'fields': {'Front': {'value': n['fields']['Front']}}})
                return len(notes)
            raise AssertionError(action)
        try:
            cfg = {'model': 'Words', 'front_field': 'Front', 'back_field': 'Back'}
            result = module.import_missing(api, cfg, lambda word: {})
            self.assertEqual((result['existing'], result['added'], result['failed']), (1, 1, ['unknown']))
            self.assertEqual(added[0]['tags'], ['zvr_cet6_core', 'zvr_cet4_core'])
            self.assertEqual(module.import_missing(api, cfg, lambda word: {})['added'], 0)
        finally:
            module.data = original

    def test_profile_switch_prevents_addition(self):
        original = module.data
        module.data = lambda: {'cet6': ['newword'], 'cet4_overlap': [], 'dictionary': {'newword': {'meaning': '新词'}}}
        profiles = iter(['one', 'two'])
        def api(action, params):
            if action == 'getActiveProfile': return next(profiles)
            if action == 'modelFieldNames': return ['Front', 'Back']
            if action == 'findNotes': return []
            raise AssertionError(action)
        try:
            with self.assertRaisesRegex(RuntimeError, '账户已切换'):
                module.import_missing(api, {'model': 'Words', 'front_field': 'Front', 'back_field': 'Back'}, lambda w: {})
        finally:
            module.data = original

if __name__ == '__main__': unittest.main()
