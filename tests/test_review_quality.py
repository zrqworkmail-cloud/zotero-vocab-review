"""The quality report's arithmetic, tested without a running Anki.

Two failure modes this file exists to prevent: counting learning-step answers as evidence of
long-term retention (they are a different question), and printing a confident 100% retention
when the sample is empty. Both would make the report lie in the direction that flatters the
plug-in.
"""
import datetime
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
spec = importlib.util.spec_from_file_location('review_quality', ROOT / 'review_quality.py')
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)

NOW = datetime.datetime(2026, 11, 6, 18, 0)


class Retention(unittest.TestCase):
    def test_only_real_reviews_count_as_evidence(self):
        rows = [(0, 1), (0, 3), (3, 3), (3, 1), (40, 1), (400, 3)]
        summary = quality.summarize(rows, [], now=NOW)
        self.assertEqual(summary['answers'], 4, 'the two interval-0 answers are not reviews')
        self.assertEqual(summary['agains'], 2)
        self.assertAlmostEqual(summary['measured'], 0.5)

    def test_each_bucket_is_counted_against_the_interval_that_was_asked_for(self):
        rows = [(5, 3), (10, 1), (60, 3), (200, 3)]
        summary = quality.summarize(rows, [], now=NOW)
        buckets = dict((label, (total, again)) for label, total, again in summary['buckets'])
        self.assertEqual(buckets['≤7 天'], (1, 0))
        self.assertEqual(buckets['8–30 天'], (1, 1))
        self.assertEqual(buckets['31–90 天'], (1, 0))
        self.assertEqual(buckets['>90 天'], (1, 0))

    def test_an_empty_sample_is_reported_empty_not_as_perfect_retention(self):
        summary = quality.summarize([], [], now=NOW)
        self.assertIsNone(summary['measured'], 'no answers means no rate, and 100% would be a lie')
        body = quality.render_markdown(summary)
        self.assertIn('还没有可统计的正式复习答案', body)
        self.assertNotIn('实测保持率', body)


class Parked(unittest.TestCase):
    def test_days_since_the_last_answer_are_bucketed_and_never_touched(self):
        summary = quality.summarize([], [10, 100, 400, 900, None], now=NOW)
        parked = dict(summary['parked'])
        self.assertEqual(parked['不到 90 天'], 1)
        self.assertEqual(parked['90 天–1 年'], 1)
        self.assertEqual(parked['1–2 年'], 1)
        self.assertEqual(parked['超过 2 年'], 1)
        self.assertEqual(parked['从未作答'], 1)
        self.assertEqual(summary['parked_total'], 5)

    def test_the_report_says_it_will_not_unsuspend_anything(self):
        body = quality.render_markdown(quality.summarize([(30, 1)], [100], now=NOW))
        self.assertIn('不会替你取消任何挂起', body)
        self.assertIn('只读', body)


class Body(unittest.TestCase):
    def test_the_promise_and_the_measurement_appear_together(self):
        body = quality.render_markdown(quality.summarize([(30, 3), (30, 1)], [], now=NOW))
        self.assertIn('90%', body, 'the promised retention has to be visible next to the measured one')
        self.assertIn('50%', body)

    def test_the_ceiling_table_is_included_when_supplied(self):
        body = quality.render_markdown(quality.summarize([(30, 3)], [], now=NOW),
                                       limits_text='六级词汇：new/day 50，今日已引入 139')
        self.assertIn('new/day 50', body)
        self.assertIn('不经过复习队列', body)


class Schema(unittest.TestCase):
    """The two column names I got wrong on the first pass, now pinned to the source.

    `revlog` has `ease`, not `rating`, and its timestamp is `id` in milliseconds, not `date`.
    Both mistakes raised only at run time, inside a try/except that turned them into a polite
    message — which is exactly why they belong in a test instead of in a demo.
    """
    SOURCE = (ROOT / '__init__.py').read_text(encoding='utf-8')

    def test_the_review_query_names_the_columns_that_exist(self):
        start = self.SOURCE.index('def write_quality_report')
        body = self.SOURCE[start:start + 3200]
        self.assertIn('select lastIvl, ease from revlog', body)
        self.assertIn('ease between 1 and 4', body,
                      'ease 0 rows are not learner answers; counting them would inflate retention')
        self.assertNotIn('rating from revlog', body)
        self.assertIn('max(id) from revlog', body)
        self.assertNotIn('max(date)', body)
        self.assertIn('86400000', body, 'revlog.id is milliseconds')

    def test_the_ceiling_questions_are_asked_off_the_gui_thread(self):
        # AnkiConnect is served by Anki's own GUI thread. Asking it from the thread that opens
        # the report waits on yourself: measured as `deck limits unavailable: TimeoutError`
        # the first time the menu entry was used. So the loopback calls must live inside the
        # worker, and the answer must be marshalled back with run_on_main.
        start = self.SOURCE.index('def write_quality_report')
        body = self.SOURCE[start:start + 4200]
        self.assertIn('def work():', body)
        self.assertLess(body.index('def work():'), body.index('deck_limits(api'),
                        'AnkiConnect must not be asked from the GUI thread')
        self.assertIn('run_on_main', body)


if __name__ == '__main__':
    unittest.main()
