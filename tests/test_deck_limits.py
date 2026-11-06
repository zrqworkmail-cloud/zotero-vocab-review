"""The two numbers that both claim to be "today's limit", measured side by side.

Anki's deck config says new/day=50; the collection said 139 cards had already been introduced
today (measured 2026-11-06). The reason is structural — this plug-in picks cards with
`findCards` and grades them with `answerCards`, so it never passes through the reviewer's
queue where that cap is enforced. The report has to say that plainly instead of letting the
user choose which number to believe, and it must never touch a deck setting to make the two
agree.
"""
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic_limits', MODULE)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

CFG = {'deck': '六级词汇'}
# The deck list is passed in: resolving which decks a 词书 spans is `resolve_book_decks`' job,
# and this function's contract is one row per deck it is handed.
DECKS = ['六级词汇']


def fake_api(per_day=50, introduced=139, new_left=4478, due=225, broken=False, retention=0.9):
    def api(action, params):
        if action == 'deckNames':
            return ['六级词汇']
        if action == 'getDeckConfig':
            if broken:
                raise RuntimeError('Anki is busy')
            return {'name': '系统默认', 'new': {'perDay': per_day, 'delays': [1.0, 10.0]},
                    'rev': {'perDay': 500}, 'desiredRetention': retention}
        if action == 'multi':
            counts = [introduced, new_left, due]
            return [[7] * n for n in counts]
        raise AssertionError(action)
    return api


class Limits(unittest.TestCase):
    def test_both_numbers_are_reported_for_the_same_deck(self):
        item = logic.deck_limits(fake_api(), CFG, DECKS)[0]
        self.assertEqual(item['new_per_day'], 50)
        self.assertEqual(item['introduced_today'], 139)
        self.assertEqual(item['new_left'], 4478)
        self.assertEqual(item['due'], 225)

    def test_the_promised_retention_travels_with_the_row(self):
        # The report measures against this number, and it lives in the deck config — the
        # Python-side deck dict does not carry it, so a row without it would silently fall
        # back to a made-up 90%.
        item = logic.deck_limits(fake_api(retention=0.85), CFG, DECKS)[0]
        self.assertEqual(item['desired_retention'], 0.85)
        self.assertEqual(logic.deck_limits(fake_api(retention=None), CFG, DECKS)[0]['desired_retention'], None)

    def test_the_overshoot_is_named_as_the_cap_not_binding_rather_than_a_counting_error(self):
        line = logic.render_deck_limits(logic.deck_limits(fake_api(), CFG, DECKS))
        self.assertIn('new/day 50', line)
        self.assertIn('今日已引入 139', line)
        self.assertIn('额度拦不住', line, line)

    def test_a_deck_that_stays_under_its_cap_is_not_accused(self):
        line = logic.render_deck_limits(logic.deck_limits(fake_api(introduced=20), CFG, DECKS))
        self.assertNotIn('额度拦不住', line)
        self.assertIn('今日已引入 20', line)

    def test_a_failing_config_read_leaves_the_row_instead_of_failing_the_report(self):
        item = logic.deck_limits(fake_api(broken=True), CFG, DECKS)[0]
        self.assertEqual(item['new_per_day'], 0)
        self.assertEqual(item['introduced_today'], 139, 'the searches are still trustworthy')
        self.assertIn('六级词汇', logic.render_deck_limits([item]))


if __name__ == '__main__':
    unittest.main()
