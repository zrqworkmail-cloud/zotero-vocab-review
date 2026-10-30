"""The deck+tag scope must not change what an existing user studies.

These are goldens captured from the pre-refactor review_logic on the real saved
config (see AUDIT §9.3). If the scope layer ever drifts, an upgrade would quietly
widen or narrow someone's study set, and the daily plan would start counting a
different pile of cards. Tag quoting is the one deliberate difference, so the
comparison normalises tag:"x" to tag:x.
"""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
spec = importlib.util.spec_from_file_location('review_logic_under_test', ROOT / 'review_logic.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

# The user's config as it was before any scope key existed: a main deck, four
# extra decks (two of which are no longer in the collection), and no tags.
LEGACY = {
    'deck': '系统默认',
    'model': '四六级单词模板',
    'review_main_deck': '四六级核心词汇',
    'review_extra_decks': ['CET6', '六级词汇（补充）', '四六级核心词汇', '文献单词'],
    'review_extra_deck': '四六级单词',
    'review_book': '',
    'review_plan_mode': 'daily',
    'review_daily_goal': 0,
    'review_computer_hours': 7,
    'review_deadline': '2026-12-12',
    'review_batch_size': 6,
    'review_windows_enabled': True,
    'review_windows': [{'enabled': True, 'start': '08:30', 'end': '11:40'},
                       {'enabled': True, 'start': '14:00', 'end': '17:30'},
                       {'enabled': True, 'start': '19:40', 'end': '22:15'}],
    'review_interval_minutes': 15,
}

QUOTED_TAG = re.compile(r'tag:"([^"]+)"')


def canonical(query):
    return QUOTED_TAG.sub(r'tag:\1', query)


class LegacyScopeEquivalence(unittest.TestCase):
    def test_deck_scoped_config_selects_the_same_decks_and_search(self):
        self.assertEqual(logic.review_decks(LEGACY),
                         ['四六级核心词汇', 'CET6', '六级词汇（补充）', '文献单词'])
        self.assertEqual(canonical(logic._search(LEGACY)),
                         'deck:"系统默认" note:"四六级单词模板" -is:suspended -is:buried')
        self.assertEqual(canonical(logic._search(LEGACY, all_decks=True)),
                         'note:"四六级单词模板" -is:suspended -is:buried')
        self.assertFalse(logic.scope_uses_all_decks(LEGACY))

    def test_plan_queries_are_the_same_sixteen(self):
        queries = []
        logic.collection_plan(lambda _action, params: queries.append(params['query']) or [], LEGACY)
        decks = ['CET6', '六级词汇（补充）', '四六级核心词汇', '文献单词']
        tails = ['is:new', 'is:due -is:new', 'rated:1', 'introduced:1']
        self.assertEqual(sorted(canonical(q) for q in queries),
                         sorted(canonical('deck:"%s" note:"四六级单词模板" -is:suspended -is:buried %s' % (d, t))
                                for d in decks for t in tails))

    def test_saved_book_still_means_cross_deck_tag_search(self):
        cfg = dict(LEGACY, review_book='cet6_kyle')
        self.assertEqual(logic.scope_tags(cfg), ['zvr_kyle_cet6'])
        self.assertTrue(logic.scope_uses_all_decks(cfg))
        self.assertEqual(canonical(logic._search(cfg, all_decks=True)),
                         'note:"四六级单词模板" tag:zvr_kyle_cet6 -is:suspended -is:buried')

    def test_a_scope_saved_by_the_new_dialog_round_trips(self):
        cfg = dict(LEGACY, review_scope_decks=['文献单词'], review_scope_tags=['zvr_kyle_cet4', '工作/学习'],
                   review_tags_all=True, review_book='')
        self.assertEqual(logic.review_decks(cfg), ['文献单词'])
        self.assertFalse(logic.scope_uses_all_decks(cfg))
        self.assertEqual(canonical(logic._search(cfg, all_decks=True)),
                         'note:"四六级单词模板" tag:zvr_kyle_cet4 AND tag:工作/学习 -is:suspended -is:buried')
        # The card header strips the zvr_ namespace so it reads as a scope, not a tag id.
        self.assertEqual(logic.scope_label(dict(cfg, review_scope_name='')), '文献单词 · kyle_cet4、工作/学习')


if __name__ == '__main__':
    unittest.main()
