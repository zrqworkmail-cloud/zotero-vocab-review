"""Independent reads share one round trip; the rating flip stopped paying for 33 of them.

Measured 2026-11-10 against the running AnkiConnect: one flip cost ~3.1 s across 33
sequential calls (collection_plan 19, prepare_question 12, book_progress 2), while one
`multi` carrying 8 of the same searches answered in 219 ms against 642 ms sequentially —
identical results. These tests pin the batching: the independent reads inside one
plan/progress/availability/prepare call travel as a single `multi`, and a transport
without `multi` falls back to the same reads one by one (the older fakes in this suite
speak no `multi`, and must keep passing untouched).
"""
import datetime
import importlib.util
import random
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic_batch', MODULE)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

CFG = {'deck': 'Literature', 'model': 'Words', 'front_field': 'Front', 'back_field': 'Back',
       'study_book': 'literature',
       'study_books': [{'id': 'literature', 'name': '文献单词', 'deck': 'Literature'}]}
BASE = 'deck:"Literature" note:"Words" -is:suspended -is:buried'


class BatchAnki:
    """findCards answers from an exact query->ids table; multi runs its actions in order.

    `multi=False` models a transport that cannot batch (the older fakes raise on it):
    the helper must fall back to the same reads sequentially, not change its answers.
    """

    def __init__(self, answers=None, decks=('Literature',), stats=None, multi=True, cards=None):
        self.answers = answers or {}
        self.decks = list(decks)
        self.stats = stats if stats is not None else {'new_count': 999, 'learn_count': 0, 'review_count': 999}
        self.cards = cards or {}
        self.calls = []
        self.multi = multi

    def __call__(self, action, params):
        self.calls.append((action, params))
        if action == 'multi':
            if not self.multi:
                raise AssertionError('multi unsupported')
            return [self._inner(item['action'], item['params']) for item in params['actions']]
        return self._inner(action, params)

    def _inner(self, action, params):
        if action == 'deckNames':
            return list(self.decks)
        if action == 'getActiveProfile':
            return 'Profile A'
        if action == 'findNotes':
            return []
        if action == 'getDeckStats':
            return {str(index): dict(self.stats, name=deck) for index, deck in enumerate(params['decks'])}
        if action == 'findCards':
            return list(self.answers.get(params['query'], []))
        if action == 'cardsInfo':
            return [self.cards[cid] for cid in params['cards'] if cid in self.cards]
        raise AssertionError(action)

    def multis(self):
        return [params for action, params in self.calls if action == 'multi']


class MultiHelper(unittest.TestCase):
    def test_independent_reads_ride_one_call_in_order(self):
        api = BatchAnki(answers={'q1': [1], 'q2': [2, 3]})
        answers = logic._multi(api, [('findCards', {'query': 'q1'}), ('findCards', {'query': 'q2'})])
        self.assertEqual(answers, [[1], [2, 3]])
        self.assertEqual([action for action, _ in api.calls], ['multi'])

    def test_a_transport_without_multi_falls_back_to_the_same_reads(self):
        api = BatchAnki(answers={'q1': [1], 'q2': [2, 3]}, multi=False)
        answers = logic._multi(api, [('findCards', {'query': 'q1'}), ('findCards', {'query': 'q2'})])
        self.assertEqual(answers, [[1], [2, 3]])
        self.assertEqual([action for action, _ in api.calls], ['multi', 'findCards', 'findCards'])

    def test_a_short_answer_falls_back_instead_of_misaligning(self):
        # Fewer items than actions must not zip one query's ids onto another query.
        def api(action, params):
            if action == 'multi':
                return [[1]]
            return [9]
        self.assertEqual(logic._multi(api, [('findCards', {'query': 'q1'}), ('findCards', {'query': 'q2'})]),
                         [[9], [9]])

    def test_no_actions_ask_nothing(self):
        api = BatchAnki()
        self.assertEqual(logic._multi(api, []), [])
        self.assertEqual(api.calls, [])


class PlanBatching(unittest.TestCase):
    def test_collection_plan_reads_travel_as_two_batches(self):
        api = BatchAnki(answers={BASE + ' is:new': [1, 2, 3], BASE + ' is:due -is:new': [4],
                                 BASE + ' rated:1': [4], BASE + ' introduced:1': [4],
                                 BASE + ' is:due': [4]},
                        stats={'new_count': 2, 'learn_count': 0, 'review_count': 1})
        plan = logic.collection_plan(api, dict(CFG, review_daily_goal=10), datetime.datetime(2026, 11, 10, 9, 0))
        self.assertEqual([action for action, _ in api.calls if action in ('findCards', 'getDeckStats')], [],
                         'stage searches and deck stats must ride the batches, one round trip each')
        multis = api.multis()
        self.assertEqual(len(multis), 2, 'one batch for the plan counts, one for availability')
        self.assertEqual([item['params']['query'] for item in multis[0]['actions']],
                         [BASE + ' is:new', BASE + ' is:due -is:new', BASE + ' rated:1', BASE + ' introduced:1'])
        self.assertEqual([item['action'] for item in multis[1]['actions']],
                         ['getDeckStats', 'findCards', 'findCards'])
        self.assertEqual(plan['remaining_new_total'], 3)
        self.assertEqual((plan['available_new'], plan['available_due']), (2, 1))

    def test_book_progress_counts_share_one_round_trip(self):
        base = 'note:"Words" deck:"Literature" -is:suspended -is:buried'
        api = BatchAnki(answers={base: [1, 2, 3, 4], base + ' prop:reps>0': [1, 2]})
        self.assertEqual(logic.book_progress(api, dict(CFG)), (2, 4))
        self.assertEqual([action for action, _ in api.calls], ['multi'])

    def test_book_availability_shares_one_batch(self):
        api = BatchAnki(answers={BASE + ' is:new': [1, 2, 3], BASE + ' is:due': [4, 5]},
                        stats={'new_count': 2, 'learn_count': 1, 'review_count': 1})
        self.assertEqual(logic.book_availability(api, dict(CFG)), (2, 2))
        self.assertEqual([action for action, _ in api.calls if action in ('findCards', 'getDeckStats')], [])
        multis = api.multis()
        self.assertEqual(len(multis), 1)
        self.assertEqual([item['action'] for item in multis[0]['actions']],
                         ['getDeckStats', 'findCards', 'findCards'])

    def test_deck_probes_for_a_tag_book_share_one_batch(self):
        book = {'id': 'cet', 'name': 'CET', 'tag': 'zvr_cet6_core'}
        queries = ['deck:"%s" note:"Words" tag:"zvr_cet6_core" -is:suspended -is:buried' % deck
                   for deck in ('CET', 'Literature')]
        api = BatchAnki(answers={queries[0]: [1], queries[1]: []}, decks=['Literature', 'CET'])
        decks = logic._book_decks_for(api, dict(CFG), book)
        self.assertEqual(decks, ['CET'])
        self.assertEqual([action for action, _ in api.calls], ['deckNames', 'multi'])


class PrepareBatching(unittest.TestCase):
    def test_prepare_question_batches_stats_and_the_ids_tagged_pair(self):
        cards = {1: {'cardId': 1, 'modelName': 'Words', 'deckName': 'Literature',
                     'fields': {'Front': {'value': 'notion'}, 'Back': {'value': '概念'}}},
                 2: {'cardId': 2, 'modelName': 'Words', 'deckName': 'Literature',
                     'fields': {'Front': {'value': 'method'}, 'Back': {'value': '方法'}}}}
        api = BatchAnki(answers={BASE + ' is:new': [1, 2],
                                 BASE + ' (is:new or is:due -is:new) '
                                        '(tag:anki_global_capture or tag:zotero_vocab_review)': [1]},
                        stats={'new_count': 2, 'learn_count': 0, 'review_count': 0}, cards=cards)
        question = logic.prepare_question(api, dict(CFG), 'typing', random.Random(1))
        self.assertIsNotNone(question)
        self.assertEqual([action for action, _ in api.calls if action in ('findCards', 'getDeckStats')], [],
                         'stats and the ids/tagged pair must ride batches')
        multis = api.multis()
        stats_batches = [batch for batch in multis
                         if [item['action'] for item in batch['actions']][:1] == ['getDeckStats']]
        self.assertEqual(len(stats_batches), 1, multis)
        self.assertGreater(len(stats_batches[0]['actions']), 1,
                           'statistics must share the candidate batch, not stand alone')
        self.assertTrue(any(item['action'] == 'findCards' for item in stats_batches[0]['actions']), multis)


if __name__ == '__main__':
    unittest.main()