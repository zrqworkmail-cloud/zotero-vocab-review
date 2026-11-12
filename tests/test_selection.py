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
# -tag: is part of the token, not a stray minus the tokenizer may drop: the untagged
# subset renders as negations, and an oracle that read them as positive would pass
# exactly the clauses that hide every card.
TOKEN = re.compile(r'\(|\)|\bAND\b|\bOR\b|-?tag:' + QUOTED)


def _tag_atoms(query):
    """Drop the deck/note/stage atoms; keep the boolean shape the tags live in."""
    return OTHER_ATOM.sub(' ', NOTE_TERM.sub(' ', DECK_TERM.sub(' ', query)))


def _tokenize(text):
    tokens = []
    for match in TOKEN.finditer(text):
        piece = match.group(0)
        if piece.startswith('tag:'):
            tokens.append(('tag', match.group(1).replace('\\"', '"')))
        elif piece.startswith('-tag:'):
            tokens.append(('-tag', match.group(1).replace('\\"', '"')))
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
    while position < len(tokens):
        if tokens[position][0] == 'AND':
            right, position = _parse_factor(tokens, position + 1, tags)
        elif tokens[position][0] in ('tag', '-tag', '('):
            # Anki reads juxtaposition as AND ("tag:a tag:b"); dropping the second
            # factor would make every narrowed query match its whole book.
            right, position = _parse_factor(tokens, position, tags)
        else:
            break
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
    if kind == '-tag':
        return name not in tags, position + 1
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


class EyebrowNamesTheDrawnBook(unittest.TestCase):
    """Spec §8: with several 词组 chosen, the card must name the one this card came
    from — not the first in the list, which is what a plain book_label(cfg) prints."""

    def test_the_index_names_the_second_book(self):
        base = cfg(study_selection=[{'book': 'core'}, {'book': 'full'}])
        self.assertEqual(logic.question_book_label(base, {'_selection_index': 1}), '六级全表')

    def test_no_index_falls_back_to_the_legacy_single_book(self):
        self.assertEqual(logic.question_book_label(cfg(study_book='core'), {}), '六级核心')

    def test_an_out_of_range_index_falls_back_rather_than_raising(self):
        base = cfg(study_selection=[{'book': 'core'}], study_book='core')
        self.assertEqual(logic.question_book_label(base, {'_selection_index': 7}), '六级核心')

    def test_no_selection_at_all_reads_empty(self):
        self.assertEqual(logic.question_book_label(cfg(), {'_selection_index': 0}), '')


class UntaggedAnki(FakeAnki):
    """Adds the two calls the untagged expansion needs: the tag vocabulary and `multi`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.actions = []
        self.batches = []

    def __call__(self, action, params):
        self.actions.append(action)
        if action == 'getTags':
            return sorted({tag for _, tags in CARDS.values() for tag in tags})
        if action == 'multi':
            self.batches.append(params['actions'])
            return [self('findCards', inner['params']) for inner in params['actions']]
        return super().__call__(action, params)

    def vocabulary_batches(self):
        # `multi` now has two users: the tag-vocabulary count and the read batching on the
        # review path. A vocabulary batch is one findCards per tag with no stage filters;
        # every read batch carries -is:suspended. The action name alone stopped telling
        # them apart on 2026-11-10, so the oracle reads the payload, not the name.
        return [batch for batch in self.batches
                if batch and all(item['action'] == 'findCards' and
                                 '-is:suspended' not in item['params'].get('query', '')
                                 for item in batch)]


class UntaggedSelection(unittest.TestCase):
    """（无标签）is a first-class choice (spec §9): checking only it studies the cards
    that carry nothing but the book's own tag. The sentinel travels in `tags` and is
    expanded against the book's real tag vocabulary at query time, so it never goes
    stale the way a saved exclusion list would."""

    def test_the_sentinel_is_the_row_label(self):
        self.assertEqual(logic.UNTAGGED, '（无标签）')

    def test_untagged_only_renders_as_explicit_negations(self):
        clause = logic.entry_clause({'book': BOOKS[1], 'tags': [logic.UNTAGGED],
                                     '_untagged_exclude': ['高频', '真题']})
        self.assertEqual(clause, ' tag:"zvr_cet6_full" AND (-tag:"高频" AND -tag:"真题")')

    def test_untagged_joins_real_tags_as_a_union_operand(self):
        clause = logic.entry_clause({'book': BOOKS[1], 'tags': ['高频', logic.UNTAGGED],
                                     '_untagged_exclude': ['高频', '真题', '学术']})
        self.assertEqual(clause, ' tag:"zvr_cet6_full" AND (tag:"高频" OR '
                                 '(-tag:"高频" AND -tag:"真题" AND -tag:"学术"))')

    def test_an_unresolved_sentinel_widens_to_the_whole_book(self):
        # No vocabulary attached (a pure caller, or the lookup failed): showing the whole
        # book is the honest failure — silently hiding the untagged cards is not.
        self.assertEqual(logic.entry_clause({'book': BOOKS[1], 'tags': [logic.UNTAGGED]}),
                         ' tag:"zvr_cet6_full"')
        self.assertEqual(logic.entry_clause({'book': BOOKS[1], 'tags': [logic.UNTAGGED],
                                             '_untagged_exclude': []}),
                         ' tag:"zvr_cet6_full"')

    def test_the_sentinel_entry_is_parenthesised_inside_a_selection(self):
        clause = logic.selection_clause([
            {'book': BOOKS[0], 'tags': []},
            {'book': BOOKS[1], 'tags': [logic.UNTAGGED], '_untagged_exclude': ['高频']}])
        self.assertIn('(tag:"zvr_cet6_full" AND (-tag:"高频"))', clause)

    def test_only_untagged_counts_the_cards_with_nothing_but_the_book_tag(self):
        # Card 5 is the only 六级全表 card with no other tag. If the expansion negated the
        # book's own tag too, this would come back 0 — the whole row would silently vanish.
        api = UntaggedAnki()
        base = cfg(study_selection=[{'book': 'full', 'tags': [logic.UNTAGGED]}])
        self.assertEqual(logic.book_progress(api, base)[1], 1)

    def test_adding_a_real_tag_widens_the_untagged_pool(self):
        api = UntaggedAnki()
        alone = cfg(study_selection=[{'book': 'full', 'tags': [logic.UNTAGGED]}])
        mixed = cfg(study_selection=[{'book': 'full', 'tags': [logic.UNTAGGED, '高频']}])
        self.assertEqual(logic.book_progress(api, alone)[1], 1)
        self.assertEqual(logic.book_progress(api, mixed)[1], 2)   # card 5 plus card 1

    def test_prepare_question_draws_the_untagged_card(self):
        api = UntaggedAnki()
        base = cfg(study_selection=[{'book': 'full', 'tags': [logic.UNTAGGED]}])
        question = logic.prepare_question(api, base, 'typing', random.Random(1))
        self.assertEqual(question['card_id'], 5)
        self.assertEqual(question['_selection_index'], 0)

    def test_no_sentinel_means_no_vocabulary_calls(self):
        api = UntaggedAnki()
        base = cfg(study_selection=[{'book': 'full', 'tags': ['高频']}])
        logic.book_progress(api, base)
        self.assertNotIn('getTags', [call for call in api.actions])
        self.assertEqual(api.vocabulary_batches(), [])

    def test_the_vocabulary_is_fetched_once_per_cfg_view(self):
        api = UntaggedAnki()
        base = cfg(study_selection=[{'book': 'full', 'tags': [logic.UNTAGGED]}])
        view = logic._expand_untagged(api, base)
        logic.book_progress(api, view)
        self.assertEqual(api.actions.count('getTags'), 1)
        self.assertEqual(len(api.vocabulary_batches()), 1)


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
