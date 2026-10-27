import importlib.util
import random
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic', MODULE)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)


def card(cid, word, meaning, queue=0, reps=0):
    return {'cardId': cid, 'modelName': 'Words', 'deckName': 'Literature',
            'queue': queue, 'due': cid, 'reps': reps, 'mod': 1,
            'fields': {'Front': {'value': word}, 'Back': {'value': meaning}}}


class FakeAnki:
    def __init__(self):
        self.cards = {1: card(1, 'notion', '概念', 2, 1),
                      2: card(2, 'method', '方法'), 3: card(3, 'signal', '信号'),
                      4: card(4, 'context', '语境'), 5: card(5, 'model', '模型')}
        self.stats = {'name': 'Literature', 'new_count': 2, 'learn_count': 0, 'review_count': 1}
        self.profile = 'Profile A'
        self.answered = []

    def __call__(self, action, params):
        if action == 'getActiveProfile':
            return self.profile
        if action == 'getDeckStats':
            return {'1': dict(self.stats)}
        if action == 'findCards':
            q = params['query']
            if 'cid:' in q:
                cid = int(q.split('cid:')[1].split()[0])
                return [cid] if cid in self.cards else []
            if 'is:due' in q:
                return [1] if self.stats['review_count'] else []
            if 'is:new' in q:
                return [2, 3, 4, 5]
            return list(self.cards)
        if action == 'cardsInfo':
            return [self.cards[cid] for cid in params['cards'] if cid in self.cards]
        if action == 'answerCards':
            self.answered.extend(params['answers'])
            self.cards[params['answers'][0]['cardId']]['reps'] += 1
            return [True]
        raise AssertionError(action)


CFG = {'deck': 'Literature', 'model': 'Words', 'front_field': 'Front', 'back_field': 'Back'}


class ReviewLogicTests(unittest.TestCase):
    def test_due_card_takes_priority_and_choices_are_distinct(self):
        api = FakeAnki()
        question = logic.prepare_question(api, CFG, 'choice', random.Random(3))
        self.assertEqual(question['card_id'], 1)
        self.assertEqual(question['kind'], 'due')
        self.assertEqual(len(question['options']), 4)
        self.assertEqual(len(set(question['options'])), 4)
        self.assertIn('概念', question['options'])

    def test_similar_option_prefixes_fall_back_to_typing(self):
        api = FakeAnki()
        common = '相同释义前缀' * 6
        for cid in (2, 3, 4, 5):
            api.cards[cid]['fields']['Back']['value'] = common + str(cid)
        question = logic.prepare_question(api, CFG, 'choice', random.Random(3))
        self.assertEqual(question['mode'], 'typing')
        self.assertEqual(question['options'], [])

    def test_new_cards_respect_remaining_daily_allowance(self):
        api = FakeAnki()
        api.stats.update(review_count=0, new_count=0)
        self.assertIsNone(logic.prepare_question(api, CFG, 'typing', random.Random(2)))
        api.stats['new_count'] = 1
        question = logic.prepare_question(api, CFG, 'typing', random.Random(2))
        self.assertEqual(question['kind'], 'new')
        self.assertIn(question['card_id'], [2, 3, 4, 5])

    def test_current_anki_reviewer_card_is_not_selected_for_popup(self):
        api = FakeAnki()
        cfg = dict(CFG, _review_exclude_card=1)
        question = logic.prepare_question(api, cfg, 'typing', random.Random(2))
        self.assertEqual(question['kind'], 'new')
        self.assertNotEqual(question['card_id'], 1)

    def test_a_changed_card_is_never_graded_from_a_stale_popup(self):
        api = FakeAnki()
        question = logic.prepare_question(api, CFG, 'typing', random.Random(2))
        api.cards[1]['reps'] += 1
        with self.assertRaisesRegex(ValueError, '变化'):
            logic.submit_review(api, CFG, question, 3)
        self.assertEqual(api.answered, [])

    def test_profile_change_does_not_grade_a_different_collection(self):
        api = FakeAnki()
        question = logic.prepare_question(api, CFG, 'typing', random.Random(2))
        api.profile = 'Profile B'
        with self.assertRaisesRegex(ValueError, '账户'):
            logic.submit_review(api, CFG, question, 3)
        self.assertEqual(api.answered, [])

    def test_skip_does_not_grade_and_valid_grade_is_sent_once(self):
        api = FakeAnki()
        question = logic.prepare_question(api, CFG, 'typing', random.Random(2))
        self.assertEqual(api.answered, [])
        logic.submit_review(api, CFG, question, 3)
        self.assertEqual(api.answered, [{'cardId': 1, 'ease': 3}])
        with self.assertRaisesRegex(ValueError, '变化'):
            logic.submit_review(api, CFG, question, 3)
        self.assertEqual(len(api.answered), 1)

    def test_clean_meaning_removes_capture_metadata(self):
        self.assertEqual(logic.clean_text('<b>概念</b><br><br>Zotero 收录次数：3'), '概念')
        self.assertTrue(logic.answer_matches('  Research  ', 'research'))

    def test_card_style_is_limited_to_the_configured_deck_and_note_type(self):
        self.assertTrue(logic.should_style_card('Literature', 'Words', 'reviewQuestion', CFG))
        self.assertTrue(logic.should_style_card('Literature::Child', 'Words', 'reviewAnswer', CFG))
        self.assertFalse(logic.should_style_card('Other', 'Words', 'reviewQuestion', CFG))
        self.assertFalse(logic.should_style_card('Literature', 'Other', 'reviewQuestion', CFG))
        self.assertFalse(logic.should_style_card('Literature', 'Words', 'previewQuestion', CFG))
        self.assertFalse(logic.should_style_card('Literature', 'Words', 'reviewQuestion', dict(CFG, review_beautify=False)))


if __name__ == '__main__':
    unittest.main()
