import importlib.util
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'domain' / 'models.py'
spec = importlib.util.spec_from_file_location('domain_models', MODULE)
models = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = models
spec.loader.exec_module(models)


class BookModels(unittest.TestCase):
    def test_book_round_trip(self):
        book = models.Book.from_mapping({'id': 'cet6', 'name': '六级', 'tag': 'zvr_cet6'})
        self.assertEqual(book, models.Book(id='cet6', name='六级', tag='zvr_cet6'))
        self.assertEqual(book.to_mapping(), {'id': 'cet6', 'name': '六级', 'deck': '', 'tag': 'zvr_cet6'})

    def test_book_is_frozen(self):
        book = models.Book(id='cet6', name='六级')
        with self.assertRaises(FrozenInstanceError):
            book.name = '四级'

    def test_selection_entry_trims_tags_and_keeps_order(self):
        entry = models.SelectionEntry.from_mapping(
            {'book': {'id': 'cet6', 'name': '六级'}, 'tags': [' zvr_core ', '', 'zvr_full']}
        )
        self.assertEqual(entry.tags, ('zvr_core', 'zvr_full'))
        self.assertEqual(
            entry.to_mapping(),
            {'book': {'id': 'cet6', 'name': '六级'}, 'tags': ['zvr_core', 'zvr_full']},
        )
        self.assertEqual(models.SelectionEntry.from_mapping(entry.to_mapping()), entry)

    def test_note_draft_defaults_are_independent(self):
        first = models.NoteDraft(front='notion', back='概念')
        second = models.NoteDraft(front='method', back='方法')
        self.assertEqual(first.fields, {})
        self.assertIsNot(first.fields, second.fields)


if __name__ == '__main__':
    unittest.main()
