import datetime
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'anki-global-addon/zotero_global_capture/study_dashboard.py'
spec = importlib.util.spec_from_file_location('study_dashboard', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StudyDashboardTests(unittest.TestCase):
    def test_auto_plan_shows_separate_progress_without_deadline(self):
        today = datetime.date(2026, 10, 29)
        plan = {'new': 5, 'new_goal': 5, 'new_done': 2, 'new_remaining': 3,
                'review_goal': 8, 'review_done': 3, 'review_remaining': 5, 'due': 5, 'done': 5}
        result = module.dashboard_html(today, '', plan, {}, auto_plan=True)
        for text in ('今日学习计划', '新学', '2 / 5', '复习', '3 / 8', '剩余 3', '剩余 5'):
            self.assertIn(text, result)
        self.assertNotIn('考试倒计时', result)
        with_deadline = module.dashboard_html(today, '2026-11-02', plan, {}, auto_plan=True)
        self.assertIn('考试倒计时', with_deadline)
        self.assertIn('2 / 5', with_deadline)

    def test_book_totals_make_the_tag_counter_impossible_to_confuse(self):
        # Anki's browser counts every note type carrying the tag; the plan counts
        # only the configured model and subtracts what has been studied.
        today = datetime.date(2026, 10, 29)
        plan = {'new': 12, 'new_goal': 40, 'new_done': 40, 'new_remaining': 0,
                'review_goal': 5, 'review_done': 5, 'review_remaining': 0, 'due': 0, 'done': 45,
                'book_total': 481, 'book_learned': 47, 'remaining_new_total': 434}
        result = module.dashboard_html(today, '2026-12-12', plan, {}, auto_plan=True)
        self.assertIn('当前词书共 481 张', result)
        self.assertIn('已学 47', result)
        self.assertIn('剩余新卡 434', result)
        self.assertNotIn('485', result)

    def test_activity_counts_distinct_cards_per_local_day(self):
        today = datetime.date.today()
        now = int(datetime.datetime.combine(today, datetime.time(12)).timestamp() * 1000)
        old = int(datetime.datetime.combine(today - datetime.timedelta(days=28), datetime.time(12)).timestamp() * 1000)
        counts = module.activity_counts([(1, now), (1, now + 1000), (2, now), (3, old)], {1, 3}, today)
        self.assertEqual(counts, {today: 1})

    def test_heatmap_has_weekday_headers_streak_and_adaptive_legend(self):
        today = datetime.date(2026, 10, 29)
        plan = {'new': 3, 'due': 1, 'done': 2}
        history = {today: 2, today - datetime.timedelta(days=1): 4, today - datetime.timedelta(days=2): 1}
        result = module.dashboard_html(today, '2026-11-02', plan, history, True)
        self.assertIn('近 28 天连续 3 天', result)
        self.assertIn('颜色按学习日平均量分级', result)
        self.assertIn('2026-10-29：2 张卡片', result)
        self.assertIn('outline:2px solid', result)
        self.assertEqual(result.count('<i style='), 5)
        yesterday_only = {today - datetime.timedelta(days=1): 2, today - datetime.timedelta(days=2): 1}
        self.assertIn('近 28 天连续 2 天', module.dashboard_html(today, '2026-11-02', plan, yesterday_only))
        full = {today - datetime.timedelta(days=n): 1 for n in range(28)}
        self.assertIn('近 28 天连续 ≥28 天', module.dashboard_html(today, '2026-11-02', plan, full))

    def test_home_cta_is_centred_and_sends_the_start_command(self):
        content = module.home_cta_html('六级全表')
        self.assertIn('id="zvr-home-start"', content)
        self.assertIn("pycmd('zvr-start-review')", content)
        self.assertIn('六级全表', content)
        self.assertIn('margin:28px auto', content)
        self.assertIn('text-align:center', content)
        escaped = module.home_cta_html('<b>词书</b>')
        self.assertIn('&lt;b&gt;词书&lt;/b&gt;', escaped)
        self.assertNotIn('<b>词书</b>', escaped)

    def test_countdown_plan_and_theme(self):
        today = datetime.date(2026, 10, 29)
        plan = {'new': 10, 'introduced': 3, 'due': 4, 'done': 5, 'new_remaining': 2}
        content = module.dashboard_html(today, '2026-11-02', plan, {today: 5}, True)
        self.assertIn('4 天', content)
        self.assertIn('今日建议新词 <b>2</b>', content)
        self.assertIn('待复习 <b>4</b>', content)
        self.assertIn('今日已学习 <b>5</b>', content)
        self.assertEqual(content.count('<span title='), 28)
        self.assertIn('#202b3d', content)
        self.assertEqual(module.dashboard_html(today, '', plan, {}), '')
        self.assertIn('已结束', module.dashboard_html(today, '2026-10-28', plan, {}))


if __name__ == '__main__':
    unittest.main()
