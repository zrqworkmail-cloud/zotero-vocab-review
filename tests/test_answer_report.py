"""The answer face's status row: one short line, and the evidence kept one hover away.

The learner's complaint (2026-11-05) was about space, not about the accounting: the line
read 「发音提示 2 次，字母提示 1/12（按位置已给出 5%），错误字母 6 次，检查失败 0 次；建议
"Again"，回车继续，也可按 A–E 自行评分；按 F 看回题目，按 P 回看上一张。」 and wrapped to
two lines. The agreed shape is a short line plus a tooltip, with zero counts never shown.
"""
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'anki-global-addon/zotero_global_capture/review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ShortLine(unittest.TestCase):
    def test_the_line_names_the_suggestion_and_the_keys_and_nothing_else(self):
        short, detail = module.answer_report('发音提示 2 次', incorrect_letters=6,
                                             failed_checks=0, rating='Again')
        self.assertEqual(short, '建议 Again（回车/空格）· A–E 改评 · Shift+F 看题 · P 回看')

    def test_mastered_is_spelled_the_way_the_button_spells_it(self):
        short, _detail = module.answer_report('无提示', rating='Mastered')
        self.assertIn('建议 Mastered', short)

    def test_the_line_fits_one_row_of_the_card(self):
        short, _ = module.answer_report('发音提示 3 次，字母提示 5/14（按位置已给出 31%），'
                                        '释义/例句提示 1 次', incorrect_letters=9,
                                        failed_checks=4, rating='Hard', seconds=12.3,
                                        show_seconds=True)
        # 40 was the old budget; 看题 moved to Shift+F on 2026-11-06 and the longest variant
        # (Mastered) is now 46 characters. The bound is a stand-in for "one row", and the row
        # is measured for real by tests/windows-status-line.py, which checks every variant
        # including Mastered against the label's own height. 48 = the measured 46 plus slack.
        self.assertLessEqual(len(short), 48)


class DetailLine(unittest.TestCase):
    def test_zero_counts_are_never_written(self):
        _short, detail = module.answer_report('无提示', incorrect_letters=0, failed_checks=0,
                                              rating='Easy')
        self.assertNotIn('0', detail)
        self.assertNotIn('错误字母', detail)
        self.assertNotIn('检查失败', detail)

    def test_every_nonzero_count_survives_into_the_tooltip(self):
        _short, detail = module.answer_report('发音提示 2 次，字母提示 1/12（按位置已给出 5%）',
                                              incorrect_letters=6, failed_checks=3,
                                              rating='Again')
        self.assertIn('发音提示 2 次', detail)
        self.assertIn('字母提示 1/12', detail)
        self.assertIn('错误字母 6 次', detail)
        self.assertIn('检查失败 3 次', detail)

    def test_the_clock_shows_only_when_it_is_part_of_the_evidence(self):
        # Spelling needs no clock; the other modes do, because a 9.2 秒 answer is why E
        # was not offered.
        _short, spelling = module.answer_report('无提示', rating='Mastered', seconds=1.1,
                                                show_seconds=False)
        _short, choice = module.answer_report('无提示', rating='Easy', seconds=9.2,
                                              show_seconds=True)
        self.assertNotIn('用时', spelling)
        self.assertIn('用时 9.2 秒', choice)

    def test_a_flawless_answer_still_says_so(self):
        # 「无提示」 is not a zero count — it is the reason the suggestion is Mastered,
        # and an empty tooltip would lose it.
        _short, detail = module.answer_report('无提示', rating='Mastered')
        self.assertEqual(detail, '无提示')


class GradingLog(unittest.TestCase):
    """The line that lets the recommendation be audited: suggestion and press, together."""

    def test_the_line_carries_recommendation_press_mode_and_cueing(self):
        line = module.grading_log_line(3, 1, 'typing',
                                       {'audio_hints': 1, 'other_hints': 0,
                                        'revealed': {2, 5}, 'letters': 9})
        self.assertTrue(line.startswith('review graded: '), line)
        for token in ('suggested=Good', 'chosen=Again', 'mode=typing',
                      'audio=1', 'other=0', 'letters=2', 'boxes=9'):
            self.assertIn(token, line, line)

    def test_a_forced_again_is_marked_as_never_having_been_a_choice(self):
        # A wrong answer is Again whatever button was near, so counting it as an override
        # would blame the pricing for the learner's own misspelling.
        line = module.grading_log_line(1, 1, 'listening', {}, forced=True)
        self.assertIn('forced=again', line)

    def test_a_card_with_no_recommendation_says_dash_rather_than_guessing(self):
        line = module.grading_log_line(None, 4, 'choice', None)
        self.assertIn('suggested=-', line)
        self.assertIn('chosen=Easy', line)
        self.assertNotIn('audio=', line, 'no hint record means nothing to report, not zeros')


if __name__ == '__main__':
    unittest.main()
