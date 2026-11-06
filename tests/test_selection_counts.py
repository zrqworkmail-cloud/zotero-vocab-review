"""The data layer behind the 词组 picker: which tags really sit on a book's cards.

The picker must list tags the book actually carries, and it must get them in one batched call
— 30 tags searched one by one is 30 round trips inside the settings dialog, which is the one
place the plug-in is not allowed to feel slow. Counts overlap on purpose (a card carries the
book tag, a word-list tag and sometimes 已掌握), so they are labels for a checkbox, never a
number to sum.
"""
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic_counts', MODULE)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

BOOK = {'id': 'cet6_full', 'name': '六级全表', 'tag': 'zvr_cet6_full'}


def fake_api(tags, cards, record=None):
    """`cards` maps a tag name to the card ids that tag has inside the book.

    `multi` answers with the plain result of each action (measured against the running
    AnkiConnect 2026-11-06: item 0 was `[1633419520615]`, a list of ids, not a
    `[result, error]` pair). Treating the item as a pair is not merely wrong, it is
    ambiguous: a tag with exactly two cards is also a two-element list, and that is the
    shape that would have crashed the picker.
    """
    def api(action, params):
        if record is not None:
            record.append(action)
        if action == 'getTags':
            if isinstance(tags, Exception):
                raise tags
            return list(tags)
        if action == 'multi':
            answers = []
            for inner in params['actions']:
                # The book clause itself is a tag:"…" term, so the tag being asked about is
                # the LAST one in the query.
                query = inner['params']['query']
                wanted = query.rstrip().split('tag:"')[-1].rstrip('"')
                answers.append(cards.get(wanted, []))
            return answers
        raise AssertionError(action)
    return api


class TagCounts(unittest.TestCase):
    def test_only_tags_that_really_appear_are_listed(self):
        api = fake_api(['zvr_cet6_full', 'zvr_kyle_cet6', 'zvr_mastered', 'highlight_red'],
                       {'zvr_cet6_full': list(range(10)), 'zvr_kyle_cet6': list(range(4)),
                        'zvr_mastered': list(range(2)), 'highlight_red': []})
        self.assertEqual(logic.book_tag_counts(api, {}, BOOK),
                         [('zvr_cet6_full', 10), ('zvr_kyle_cet6', 4), ('zvr_mastered', 2)])

    def test_the_whole_tag_vocabulary_is_asked_for_in_one_batch(self):
        # One getTags and one multi. A per-tag findCards loop is 30 round trips and was the
        # reason this counting is done when a row expands rather than for every row up front.
        seen = []
        api = fake_api(['a', 'b', 'c'], {'a': [1], 'b': [2, 3]}, record=seen)
        logic.book_tag_counts(api, {}, BOOK)
        self.assertEqual(seen, ['getTags', 'multi'])

    def test_a_book_without_a_scope_clause_asks_nothing(self):
        seen = []
        api = fake_api(['a'], {'a': [1]}, record=seen)
        self.assertEqual(logic.book_tag_counts(api, {}, {'id': 'x', 'name': '空'}), [])
        self.assertEqual(seen, [])

    def test_a_failed_lookup_leaves_the_picker_empty_instead_of_raising(self):
        api = fake_api(RuntimeError('Anki is busy'), {})
        self.assertEqual(logic.book_tag_counts(api, {}, BOOK), [])

    def test_a_tag_with_exactly_two_cards_counts_two(self):
        # The regression this exists for: reading multi's answer as a [result, error] pair
        # makes a two-card tag look like a pair, and the count then comes out of len(int).
        api = fake_api(['pair'], {'pair': [11, 22]})
        self.assertEqual(logic.book_tag_counts(api, {}, BOOK), [('pair', 2)])

    def test_a_quoted_tag_name_is_escaped_before_it_reaches_the_search(self):
        queries = []

        def api(action, params):
            if action == 'getTags':
                return ['we"ird']
            queries.append(params['actions'][0]['params']['query'])
            return [[1, 2]]        # one plain result: two card ids
        self.assertEqual(logic.book_tag_counts(api, {}, BOOK), [('we"ird', 2)])
        self.assertIn('tag:"we\\"ird"', queries[0])


class UntaggedRow(unittest.TestCase):
    def test_the_untagged_row_excludes_every_listed_tag(self):
        # （无标签）is a first-class choice: on a word-list book most cards carry nothing but
        # the book tag, and without this row they would vanish from the picker.
        queries = []

        def api(action, params):
            queries.append(params['query'])
            return [1, 2, 3]
        self.assertEqual(logic.book_untagged_count(api, BOOK, ['a', 'b']), 3)
        self.assertEqual(queries, [' tag:"zvr_cet6_full" -tag:"a" -tag:"b"'])

    def test_a_book_without_a_scope_asks_nothing(self):
        seen = []

        def api(action, params):
            seen.append(action)
            return []
        self.assertEqual(logic.book_untagged_count(api, {'id': 'x', 'name': '空'}, ['a']), 0)
        self.assertEqual(seen, [])

    def test_a_failed_lookup_answers_zero(self):
        def api(action, params):
            raise RuntimeError('Anki is busy')
        self.assertEqual(logic.book_untagged_count(api, BOOK, ['a']), 0)


class EntryClauses(unittest.TestCase):
    def test_a_tag_subset_widens_when_a_second_tag_is_checked(self):
        # Union, never intersection: checking one more box must not shrink the pool.
        whole = logic.entry_clause({'book': BOOK, 'tags': []})
        one = logic.entry_clause({'book': BOOK, 'tags': ['zvr_mastered']})
        two = logic.entry_clause({'book': BOOK, 'tags': ['zvr_mastered', 'zvr_kyle_cet6']})
        self.assertIn('OR', two)
        self.assertNotIn('OR', one)
        self.assertTrue(whole.strip().startswith('tag:"zvr_cet6_full"'), whole)

    def test_each_entry_is_parenthesised_once_it_carries_an_and(self):
        # Without the explicit parentheses the result reads `tag:A OR tag:B AND (tag:x)` and
        # is only correct because Anki binds AND tighter than OR — a coincidence, not a design.
        clause = logic.selection_clause([
            {'book': BOOK, 'tags': []},
            {'book': {'id': 'cet4', 'name': '四级', 'tag': 'zvr_cet4'}, 'tags': ['a', 'b']}])
        self.assertIn('(tag:"zvr_cet4"', clause.replace('( tag:', '(tag:'), clause)
        self.assertEqual(clause.count(' OR '), 2, clause)


if __name__ == '__main__':
    unittest.main()
