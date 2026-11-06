"""「已掌握」的两个语义：把卡挂起（今天的样子），或按 Easy 评分留在排程里。

挂起与间隔重复的原理是相反的：它宣布这个词永远不会再被检验。长间隔模式把同一个决定交给
调度器——Easy 是 Anki 自己的语言，增长系数由它的牌组配置决定，插件不自己编间隔。
默认仍是挂起，因为那 251 张已经挂起的卡是用户的排程状态，改开关不迁移它们。
"""
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic_mastered', MODULE)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

QUESTION = {'card_id': 501, 'word': 'plutocrat'}


class Recorder:
    """A fake AnkiConnect that records what was asked, in order."""

    def __init__(self, confirm=True):
        self.calls = []
        self.confirm = confirm

    def __call__(self, action, params):
        self.calls.append((action, params))
        if action == 'cardsInfo':
            return [{'note': 77}]
        if action == 'suspend':
            return [True]
        if action == 'answerCards':
            return [True] if self.confirm else [False]
        if action == 'addTags':
            return True
        raise AssertionError(action)

    @property
    def actions(self):
        return [action for action, _params in self.calls]


class WhichAction(unittest.TestCase):
    def test_suspend_is_what_a_config_from_before_this_setting_means(self):
        self.assertEqual(logic.mastered_action({}), logic.MASTERED_SUSPEND)
        self.assertEqual(logic.mastered_action({'review_mastered_action': ''}), logic.MASTERED_SUSPEND)
        self.assertEqual(logic.mastered_action({'review_mastered_action': 'nonsense'}),
                         logic.MASTERED_SUSPEND, 'an unknown value must not silently rate')

    def test_easy_is_the_only_spelling_that_switches_to_rating(self):
        self.assertEqual(logic.mastered_action({'review_mastered_action': 'easy'}), logic.MASTERED_RATE)


class SuspendMode(unittest.TestCase):
    def test_the_default_writes_no_rating(self):
        api = Recorder()
        self.assertEqual(logic.mark_mastered(api, {}, QUESTION), 77)
        self.assertEqual(api.actions, ['cardsInfo', 'suspend', 'addTags'])
        self.assertNotIn('answerCards', api.actions, '掌握不是复习结果，默认不许碰调度')

    def test_the_tag_is_what_makes_the_decision_recoverable(self):
        api = Recorder()
        logic.mark_mastered(api, {}, QUESTION)
        tagged = [params for action, params in api.calls if action == 'addTags']
        self.assertEqual(tagged[0]['tags'], logic.MASTERED_TAG)
        self.assertEqual(tagged[0]['notes'], [77])


class RateMode(unittest.TestCase):
    def test_easy_is_handed_to_the_scheduler_and_nothing_is_suspended(self):
        api = Recorder()
        cfg = {'review_mastered_action': 'easy'}
        self.assertEqual(logic.mark_mastered(api, cfg, QUESTION), 77)
        self.assertEqual(api.actions, ['cardsInfo', 'answerCards', 'addTags'])
        self.assertEqual(api.calls[1][1]['answers'], [{'cardId': 501, 'ease': logic.RATE_EASE_FOR_MASTERED}])
        self.assertNotIn('suspend', api.actions, '留在排程里才是这个模式的意义')

    def test_an_unconfirmed_answer_raises_instead_of_claiming_success(self):
        api = Recorder(confirm=False)
        with self.assertRaises(ValueError):
            logic.mark_mastered(api, {'review_mastered_action': 'easy'}, QUESTION)

    def test_the_growth_factor_is_anki_not_the_plugin(self):
        # There is no interval written by us anywhere in this module's mastered path.
        self.assertEqual(logic.RATE_EASE_FOR_MASTERED, 4, 'Easy is the long-interval rating Anki knows')


if __name__ == '__main__':
    unittest.main()
