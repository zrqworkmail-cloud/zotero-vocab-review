"""A config saved before books must still study the same cards.

This is the upgrade-safety check the deck+tag refactor also had. What changed is the
machinery, not the range: a saved 词书 has to land on a book whose search clause is
the very tag or deck it used to emit, or upgrading would quietly swap one word list
for another.
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
spec = importlib.util.spec_from_file_location('review_logic_migration', ROOT / 'review_logic.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

BASE = {'deck': '系统默认', 'model': '四六级单词模板'}


def search_for(cfg):
    return logic._search(dict(BASE, **cfg), all_decks=True)


class LegacyValues(unittest.TestCase):
    def test_every_retired_word_book_keeps_its_own_clause(self):
        expected = {'cet6_core': 'zvr_cet6_core', 'cet6_full': 'zvr_cet6_full',
                    'cet4_kyle': 'zvr_kyle_cet4', 'cet6_kyle': 'zvr_kyle_cet6'}
        for legacy, tag in expected.items():
            cfg = dict(BASE, study_book='', review_book=legacy)
            book = logic.study_book(cfg)
            self.assertIsNotNone(book, '%s would be dropped and study the whole deck' % legacy)
            self.assertIn('tag:"%s"' % tag, search_for(cfg), '%s no longer means %s' % (legacy, tag))

    def test_scope_tags_saved_by_the_previous_build_still_resolve(self):
        for tag, book_id in (('zvr_cet6_core', 'cet6_core'), ('zvr_kyle_cet4', 'cet4_full'),
                             ('zvr_cet4_core', 'cet4_core'), ('zvr_kyle_cet6', 'cet6_kyle')):
            cfg = dict(BASE, study_book='', review_scope_tags=[tag])
            self.assertEqual(logic.study_book_id(cfg), book_id, tag)
            self.assertIn('tag:"%s"' % tag, search_for(cfg))

    def test_a_deck_scoped_config_stays_deck_scoped(self):
        # Nothing was ever selected: no tag clause may appear, or the range would empty.
        self.assertNotIn('tag:', search_for({'study_book': '', 'review_book': ''}))

    def test_a_deck_in_the_old_extra_list_does_not_pick_a_book(self):
        # A leftover deck list is not a book choice; guessing one would change what he
        # studies on upgrade. It resolves to nothing and settings asks him to pick.
        cfg = dict(BASE, study_book='', review_book='', review_extra_decks=['文献单词'])
        self.assertIsNone(logic.study_book_id(cfg))

    def test_nothing_is_studied_before_a_book_is_chosen(self):
        # An empty study_book with no legacy value must not silently mean "everything".
        self.assertIsNone(logic.study_book(dict(BASE, study_book='', review_book='',
                                                review_scope_tags=[], review_extra_decks=[])))


class CatalogueShape(unittest.TestCase):
    def test_shipped_books_each_carry_exactly_one_selector(self):
        self.assertTrue(logic.STUDY_BOOKS)
        ids = [book['id'] for book in logic.STUDY_BOOKS]
        self.assertEqual(len(ids), len(set(ids)), 'duplicate book id')
        for book in logic.STUDY_BOOKS:
            self.assertTrue(book['name'])
            self.assertTrue(bool(book.get('tag')) ^ bool(book.get('deck')), book)

    def test_every_migration_target_is_a_real_book(self):
        known = {book['id'] for book in logic.STUDY_BOOKS}
        for source, target in logic.BOOK_MIGRATION.items():
            self.assertIn(target, known, '%s points at a book that does not exist' % source)


if __name__ == '__main__':
    unittest.main()
