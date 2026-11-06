"""The multi-词组 selection: clauses, migration, ordering, and the numbers in the plan.

Steps 1-4 of `docs/superpowers/specs/2026-11-05-multi-book-tag-selection-design.md`.

The fake Anki here answers `findCards` by **evaluating** the query's tag expression against a
small table of (deck, tags) per card. An earlier version pattern-matched `(tag:a OR tag:b)`
with a flat regex and could not see nested groups — a wrong oracle, which makes every clause
test worthless, so the parser below is as much the point of this file as the assertions are.
"""
import ast
import importlib.util
from pathlib import Path
import random
import re
import unittest

SRC = (Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' /
       'review_logic.py')
spec = importlib.util.spec_from_file_location('review_logic', SRC)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

BOOKS = [{'id': 'core', 'name': '六级核心', 'tag': 'zvr_cet6_core'},
         {'id': 'full', 'name': '六级全表', 'tag': 'zvr_cet6_full'},
         {'id': 'lit', 'name': '文献单词', 'deck': 'Literature'}]

# cid -> (deck, tags). Card 1 is in both books; 5 is in 六级全表 with no chosen tag.
CARDS = {1: ('Literature', {'zvr_cet6_core', 'zvr_cet6_full', '高频'}),
         2: ('Literature', {'zvr_cet6_full', '真题'}),
         3: ('CET', {'zvr_cet6_core'}),
         4: ('CET', {'zvr_cet6_full', '学术'}),
         5: ('Literature', {'zvr_cet6_full'})}

QUOTED = r'"((?:[^"\\]|\\.)*)"'
DECK_TERM = re.compile(r'deck:' + QUOTED)
NOTE_TERM = re.compile(r'note:' + QUOTED)
OTHER_ATOM = re.compile(r'-?is:\S+|prop:\S+|rated:\S+|introduced:\S+|cid:\S+')
TOKEN = re.compile(r'\(|\)|\bAND\b|\bOR\b|tag:' + QUOTED)


def _tag_atoms(query):
    """Drop the deck/note/stage atoms; keep the boolean shape the tags live in."""
    return OTHER_ATOM.sub(' ', NOTE_TERM.sub(' ', DECK_TERM.sub(' ', query)))


def _tokenize(text):
    tokens = []
    for match in TOKEN.finditer(text):
        piece = match.group(0)
        if piece.startswith('tag:'):
            tokens.append(('tag', match.group(1).replace('\\"', '"')))
        else:
            tokens.append((piece, None))
    return tokens


# The parser evaluates as it goes and returns booleans. Returning tag names instead made
# `'core' or right` short-circuit the OR, so the oracle saw only the first alternative and
# every clause test quietly under-matched.
def _parse_expr(tokens, position, tags):
    value, position = _parse_term(tokens, position, tags)
    while position < len(tokens) and tokens[position][0] == 'OR':
        right, position = _parse_term(tokens, position + 1, tags)
        value = value or right
    return value, position


def _parse_term(tokens, position, tags):
    value, position = _parse_factor(tokens, position, tags)
    while position < len(tokens) and tokens[position][0] == 'AND':
        right, position = _parse_factor(tokens, position + 1, tags)
        value = value and right
    return value, position


def _parse_factor(tokens, position, tags):
    if position >= len(tokens):
        return True, position
    kind, name = tokens[position]
    if kind == '(':
        value, position = _parse_expr(tokens, position + 1, tags)
        if position < len(tokens) and tokens[position][0] == ')':
            position += 1
        return value, position
    if kind == 'tag':
        return name in tags, position + 1
    return True, position + 1


def tag_expression_holds(query, tags):
    """True when this card's tag set satisfies the query's tag expression."""
    tokens = _tokenize(_tag_atoms(query))
    if not tokens:
        return True
    value, _ = _parse_expr(tokens, 0, tags)
    return bool(value)


class FakeAnki:
    """Answers findCards by evaluating the clause against CARDS."""

    def __init__(self, new_decks=('Literature', 'CET'), due_decks=()):
        # `decks` is what Anki reports as existing and is always both; `new_decks` and
        # `due_decks` decide which of them can serve a card today. Conflating them made a
        # "no new cards today" fake report no decks at all.
        self.decks = ['Literature', 'CET']
        self.new_decks = set(new_decks)
        self.due_decks = set(due_decks)
        self.queries = []
        self.stats = {'new_count': 999, 'learn_count': 0, 'review_count': 999}

    def matches(self, query, cid):
        deck, tags = CARDS[cid]
        wanted = [value.replace('\\"', '"') for value in DECK_TERM.findall(query)]
        if wanted and deck not in wanted:
            return False
        notes = NOTE_TERM.findall(query)
        if notes and notes[0] != 'Words':
            return False
        return tag_expression_holds(query, tags)

    def __call__(self, action, params):
        if action == 'deckNames':
            return list(self.decks)
        if action == 'getActiveProfile':
            return 'Profile A'
        if action == 'findNotes':
            return []
        if action == 'getDeckStats':
            return {'1': dict(self.stats, name=params['decks'][0])}
        if action == 'findCards':
            query = params['query']
            self.queries.append(query)
            hits = [cid for cid in sorted(CARDS) if self.matches(query, cid)]
            if 'is:new' in query and '-is:new' not in query:
                return [cid for cid in hits if CARDS[cid][0] in self.new_decks]
            if 'is:due' in query:
                return [cid for cid in hits if CARDS[cid][0] in self.due_decks]
            return hits
        if action == 'cardsInfo':
            return [{'cardId': cid, 'deckName': CARDS[cid][0], 'modelName': 'Words',
                     'fields': {'Front': {'value': 'word%d' % cid},
                                'Back': {'value': '释义%d' % cid}}}
                    for cid in params['cards']]
        raise AssertionError('unhandled action %s' % action)


def cfg(**extra):
    base = {'deck': 'Literature', 'model': 'Words', 'front_field': 'Front', 'back_field': 'Back',
            'study_books': BOOKS, 'review_modes': ['typing'], 'review_plan_mode': 'fixed',
            'review_batch_size': 10}
    return dict(base, **extra)


class SelectionEntries(unittest.TestCase):
    def test_a_single_legacy_book_becomes_one_whole_book_entry(self):
        entries = logic.selection_entries(cfg(study_book='core'))
        self.assertEqual([entry['book']['id'] for entry in entries], ['core'])
        self.assertEqual(entries[0]['tags'], [])

    def test_the_order_in_the_list_is_the_order_studied(self):
        entries = logic.selection_entries(cfg(study_selection=[{'book': 'full'},
                                                               {'book': 'core'}]))
        self.assertEqual([entry['book']['id'] for entry in entries], ['full', 'core'])

    def test_an_unknown_book_is_dropped_not_guessed(self):
        # A dangling id would look selected and study nothing — the §9.12 shape.
        entries = logic.selection_entries(cfg(study_selection=[{'book': 'ghost'},
                                                               {'book': 'core'}]))
        self.assertEqual([entry['book']['id'] for entry in entries], ['core'])

    def test_a_book_listed_twice_keeps_the_first_entry_only(self):
        entries = logic.selection_entries(cfg(study_selection=[
            {'book': 'core', 'tags': ['高频']}, {'book': 'core', 'tags': ['真题']}]))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['tags'], ['高频'])

    def test_empty_selection_is_empty_not_everything(self):
        self.assertEqual(logic.selection_entries(cfg()), [])
        self.assertEqual(logic.selection_entries(cfg(study_book='ghost')), [])


class Clauses(unittest.TestCase):
    def test_whole_book_and_tag_subset(self):
        self.assertEqual(logic.entry_clause({'book': BOOKS[0], 'tags': []}),
                         ' tag:"zvr_cet6_core"')
        self.assertEqual(logic.entry_clause({'book': BOOKS[0], 'tags': ['高频', '真题']}),
                         ' tag:"zvr_cet6_core" AND (tag:"高频" OR tag:"真题")')

    def test_tags_are_a_union_so_checking_more_never_shrinks_the_pool(self):
        api = FakeAnki()
        one = api('findCards', {'query': logic.selection_clause(
            [{'book': BOOKS[1], 'tags': ['高频']}])})
        two = api('findCards', {'query': logic.selection_clause(
            [{'book': BOOKS[1], 'tags': ['高频', '真题']}])})
        self.assertEqual(sorted(one), [1])
        self.assertEqual(sorted(two), [1, 2])

    def test_two_entries_are_or_ed_with_explicit_parentheses(self):
        clause = logic.selection_clause([{'book': BOOKS[0], 'tags': []},
                                         {'book': BOOKS[1], 'tags': ['学术']}])
        self.assertIn('tag:"zvr_cet6_core"', clause)
        self.assertIn('(tag:"zvr_cet6_full" AND (tag:"学术"))', clause)
        # The AND-bearing entry must be parenthesised so the result never relies on Anki
        # binding AND tighter than OR.
        self.assertNotIn(' OR tag:"zvr_cet6_full" AND', clause)

    def test_quotes_in_a_tag_name_are_escaped(self):
        clause = logic.entry_clause({'book': BOOKS[0], 'tags': ['say "hi"']})
        self.assertIn(r'tag:"say \"hi\""', clause)

    def test_search_over_a_selection_covers_every_entry(self):
        api = FakeAnki()
        base = cfg(study_selection=[{'book': 'core'}, {'book': 'full', 'tags': ['真题']}])
        hits = api('findCards', {'query': logic._search(dict(base, deck='Literature'))})
        self.assertIn(1, hits)          # via 六级核心
        self.assertIn(2, hits)          # via 六级全表 + 真题
        self.assertNotIn(5, hits)       # 六级全表 with no chosen tag
        cet = api('findCards', {'query': logic._search(dict(base, deck='CET'))})
        self.assertEqual(cet, [3])      # core only; card 4 is 学术


class Ordering(unittest.TestCase):
    def test_an_exhausted_entry_hands_over_to_the_next(self):
        api = FakeAnki(new_decks=('CET',))     # 'lit' can serve nothing
        base = cfg(study_selection=[{'book': 'lit'}, {'book': 'core'}])
        question = logic.prepare_question(api, base, 'typing', random.Random(1))
        self.assertEqual(question['_selection_index'], 1)
        self.assertEqual(question['review_deck'], 'CET')

    def test_the_first_usable_entry_wins_when_both_have_cards(self):
        api = FakeAnki()
        base = cfg(study_selection=[{'book': 'core'}, {'book': 'full'}])
        question = logic.prepare_question(api, base, 'typing', random.Random(1))
        self.assertEqual(question['_selection_index'], 0)

    def test_nothing_anywhere_returns_none_rather_than_the_last_entry(self):
        api = FakeAnki(new_decks=(), due_decks=())
        base = cfg(study_selection=[{'book': 'core'}, {'book': 'full'}])
        self.assertIsNone(logic.prepare_question(api, base, 'typing', random.Random(1)))

    def test_due_only_still_reaches_the_due_queue_of_a_later_entry(self):
        # The break/continue trap one level up: skipping new cards must not skip the loop.
        api = FakeAnki(new_decks=(), due_decks=('CET',))
        base = cfg(study_selection=[{'book': 'lit'}, {'book': 'core'}])
        question = logic.prepare_question(api, base, 'typing', random.Random(1), due_only=True)
        self.assertIsNotNone(question)
        self.assertEqual(question['kind'], 'due')
        self.assertEqual(question['_selection_index'], 1)

    def test_a_book_with_no_decks_is_skipped_not_fatal(self):
        api = FakeAnki()
        api.decks = ['CET']                    # 'lit' spans no existing deck
        base = cfg(study_selection=[{'book': 'lit'}, {'book': 'core'}])
        question = logic.prepare_question(api, base, 'typing', random.Random(1))
        self.assertEqual(question['_selection_index'], 1)


class PlanAcrossEntries(unittest.TestCase):
    def test_the_plan_counts_the_whole_selection_not_just_the_first_book(self):
        api = FakeAnki()
        base = cfg(study_selection=[{'book': 'core'}, {'book': 'full'}])
        plan = logic.collection_plan(api, base)
        self.assertEqual(plan['remaining_new_total'], 5)

    def test_the_summary_names_every_book(self):
        summary = logic.selection_summary(cfg(study_selection=[{'book': 'core'},
                                                               {'book': 'full'}]))
        self.assertEqual(summary, '六级核心、六级全表')
        self.assertEqual(logic.selection_summary(cfg(study_book='core')), '六级核心')

    def test_end_of_session_says_selection_not_book_when_several_are_chosen(self):
        plan = {'new_remaining': 0, 'due': 0, 'remaining_new_total': 0, 'available_new': 0}
        said = logic.end_of_session_reason(plan, False, book_label=logic.selection_summary(
            cfg(study_selection=[{'book': 'core'}, {'book': 'full'}])), elsewhere_due=7)
        self.assertIn('六级核心、六级全表', said)
        self.assertIn('7 张到期卡不在所选词组内', said)


class NoShadowedDefinitions(unittest.TestCase):
    """A second `def resolve_book_decks` silently replaced the first for a whole session.

    Python keeps the last definition and nothing complained, so the new multi-entry cache
    was dead code while the old single-book body still ran. Top-level names are checked per
    module so an insertion like that cannot hide again.
    """

    def test_no_module_defines_the_same_name_twice(self):
        for name in ('review_logic.py', 'card_motion.py', 'motion_view.py', 'candy_badge.py',
                     'input_mode.py', 'review_popup.py'):
            tree = ast.parse((SRC.parent / name).read_text(encoding='utf-8'))
            seen = [node.name for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
            duplicates = sorted({n for n in seen if seen.count(n) > 1})
            self.assertEqual(duplicates, [], '%s redefines %s' % (name, duplicates))


if __name__ == '__main__':
    unittest.main()
