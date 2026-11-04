"""The book model: one named view is the whole scope.

These replace the deck+tag scope tests, which pinned a contract that no longer
exists. What has to hold now: a book is a tag where the lists nest and a deck where
they do not, the queries it generates are the same whether or not a deck is also
pinned, and a config saved before books still lands on a sensible one.
"""
import importlib.util
import random
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
spec = importlib.util.spec_from_file_location('review_logic_books', ROOT / 'review_logic.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

CATALOGUE = [
    {'id': 'core', 'name': '六级核心', 'tag': 'zvr_cet6_core'},
    {'id': 'full', 'name': '六级全表', 'tag': 'zvr_cet6_full'},
    {'id': 'lit', 'name': '文献单词', 'deck': '文献单词'},
]
BASE = {'deck': '文献单词', 'model': '四六级单词模板', 'front_field': '正面', 'back_field': '解释',
        'study_books': CATALOGUE}


class Catalogue(unittest.TestCase):
    def test_the_shipped_catalogue_names_every_book(self):
        self.assertTrue(logic.STUDY_BOOKS)
        for book in logic.STUDY_BOOKS:
            self.assertTrue(book['name'])
            self.assertTrue(bool(book.get('tag')) ^ bool(book.get('deck')),
                            '%s needs exactly one of tag/deck' % book)

    def test_config_can_supply_books_without_editing_the_source(self):
        # The old 词书 dropdown was hardcoded, which is how it drifted from reality.
        self.assertEqual([book['id'] for book in logic.study_books(dict(BASE))], ['core', 'full', 'lit'])
        self.assertEqual([book['id'] for book in logic.study_books({})],
                         [book['id'] for book in logic.STUDY_BOOKS])

    def test_an_unknown_selection_is_not_a_book(self):
        self.assertIsNone(logic.study_book(dict(BASE, study_book='nope')))
        self.assertEqual(logic.book_label(dict(BASE, study_book='nope')), '')


class Queries(unittest.TestCase):
    def test_a_tag_book_searches_by_tag_and_still_pins_the_deck(self):
        cfg = dict(BASE, study_book='core')
        search = logic._search(dict(cfg, deck='CET6'))
        self.assertIn('deck:"CET6"', search)
        self.assertIn('tag:"zvr_cet6_core"', search)
        self.assertIn('-is:suspended -is:buried', search)

    def test_a_deck_book_does_not_repeat_its_own_deck(self):
        search = logic._search(dict(BASE, study_book='lit'))
        self.assertEqual(search.count('deck:'), 1, search)

    def test_tag_with_spaces_and_quotes_survives(self):
        clause = logic.book_clause({'id': 'x', 'name': 'x', 'tag': 'has space'})
        self.assertEqual(clause, ' tag:"has space"')
        self.assertEqual(logic.book_clause({'id': 'x', 'name': 'x', 'tag': 'say"this'}), ' tag:"say\\"this"')

    def test_no_book_selected_studies_nothing(self):
        self.assertEqual(logic.book_label(dict(BASE)), '')
        self.assertEqual(logic.review_decks(dict(BASE)), [])


class Migration(unittest.TestCase):
    def test_a_saved_book_id_survives(self):
        self.assertEqual(logic.study_book_id(dict(BASE, study_book='full')), 'full')

    def test_legacy_values_resolve_against_the_catalogue_in_force(self):
        # A migrated id that this config does not offer must resolve to nothing, not
        # to a dangling book that would quietly study an empty range.
        self.assertIsNone(logic.study_book_id(dict(BASE, study_book='', review_book='cet6_core')))
        self.assertIsNone(logic.study_book_id(dict(BASE, study_book='', review_scope_tags=['zvr_kyle_cet4'])))
        self.assertIsNone(logic.study_book_id(dict(BASE, study_book='', review_scope_tags=['zvr_cet6_core'])))

    def test_real_catalogue_maps_every_old_word_book_onto_a_new_one(self):
        for legacy in ('cet6_core', 'cet6_full', 'cet4_kyle', 'cet6_kyle'):
            found = logic.study_book_id(dict(BASE, study_books=logic.STUDY_BOOKS, study_book='',
                                             review_book=legacy))
            self.assertIsNotNone(found, 'legacy %s would be silently dropped' % legacy)


class Decks(unittest.TestCase):
    def test_a_tag_book_spans_every_deck_holding_the_tag(self):
        seen = []
        def api(action, params):
            if action == 'deckNames':
                return ['A', 'B', 'Empty']
            seen.append(params['query'])
            return [] if 'Empty' in params['query'] else [1]
        cfg = dict(BASE, study_book='core')
        self.assertEqual(logic.resolve_book_decks(api, cfg), ['A', 'B'])
        self.assertTrue(all('tag:"zvr_cet6_core"' in query for query in seen))

    def test_the_deck_list_is_cached_per_book(self):
        calls = []
        def api(action, params):
            calls.append(action)
            return ['A'] if action == 'deckNames' else [1]
        cfg = dict(BASE, study_book='core')
        logic.resolve_book_decks(api, cfg)
        before = len(calls)
        logic.resolve_book_decks(api, cfg)
        self.assertEqual(len(calls), before, 'a second resolve should reuse the cache')
        cfg['study_book'] = 'lit'
        logic.resolve_book_decks(api, cfg)
        self.assertGreater(len(calls), before, 'switching books must not reuse the old decks')


class Progress(unittest.TestCase):
    def test_progress_counts_the_book_and_how_many_were_answered(self):
        seen = []
        def api(action, params):
            seen.append(params['query'])
            return [1, 2] if params['query'].endswith(' prop:reps>0') else [1, 2, 3, 4]
        self.assertEqual(logic.book_progress(api, dict(BASE, study_book='core')), (2, 4))
        self.assertIn('tag:"zvr_cet6_core"', seen[0])
        self.assertIn('note:"四六级单词模板"', seen[0])
        self.assertTrue(seen[1].endswith(' prop:reps>0'), seen[1])
        self.assertNotIn('prop:reps:', seen[1], 'Anki rejects the colon form as a parse error')

    def test_no_book_is_zero_and_does_not_scan_the_collection(self):
        calls = []
        self.assertEqual(logic.book_progress(lambda *args, **kwargs: calls.append(args) or [1], dict(BASE)), (0, 0))
        self.assertEqual(calls, [])


class Availability(unittest.TestCase):
    def test_each_deck_quota_caps_what_the_book_can_show(self):
        # The real failure: a book with thousands of new cards offered nothing
        # because both of its decks had already spent the day's new limit.
        def api(action, params):
            if action == 'deckNames':
                return ['A', 'B']
            if action == 'getDeckStats':
                deck = params['decks'][0]
                return {'1': {'name': deck, 'new_count': 0 if deck == 'A' else 7,
                              'learn_count': 0, 'review_count': 0}}
            query = params['query']
            if query.endswith(' is:new'):
                return list(range(100))
            if query.endswith(' is:due'):
                return []
            return [1]
        self.assertEqual(logic.book_availability(api, dict(BASE, study_book='core')), (7, 0))

    def test_due_is_capped_by_the_decks_learn_and_review_quotas(self):
        def api(action, params):
            if action == 'deckNames':
                return ['文献单词']
            if action == 'getDeckStats':
                return {'1': {'name': '文献单词', 'new_count': 5, 'learn_count': 2, 'review_count': 3}}
            query = params['query']
            if query.endswith(' is:new'):
                return list(range(12))
            if query.endswith(' is:due'):
                return list(range(2))
            return []
        self.assertEqual(logic.book_availability(api, dict(BASE, study_book='lit')), (5, 2))


class Questions(unittest.TestCase):
    def test_an_empty_book_says_so_instead_of_staying_silent(self):
        def api(action, params):
            if action == 'getActiveProfile':
                return 'P'
            if action == 'deckNames':
                return ['A']
            return []
        with self.assertRaises(ValueError) as caught:
            logic.prepare_question(api, dict(BASE, study_book='core'), 'choice', random.Random(1))
        self.assertIn('词书', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
