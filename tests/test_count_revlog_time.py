"""Self-check for tools/count-revlog-time.py.

The tool itself is read-only against AnkiConnect; these tests stay offline and
exercise the parsing, candidate-window, batching, and reporting logic that the
CLI wraps.
"""
import contextlib
import importlib.util
import io
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'count_revlog_time', ROOT / 'tools' / 'count-revlog-time.py')
counter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = counter
SPEC.loader.exec_module(counter)


def review(review_id, card_id=None, time_ms=0):
    return counter.Review(
        review_id=review_id,
        card_id=review_id if card_id is None else card_id,
        time_ms=time_ms,
    )


class ParseSince(unittest.TestCase):
    def test_iso_offset_epoch_seconds_and_epoch_milliseconds_agree(self):
        expected = 1794907009000
        iso_ms, iso_local = counter.parse_since('2026-11-17T17:16:49+08:00')
        self.assertEqual(iso_ms, expected)
        self.assertEqual(iso_local.utcoffset(), timedelta(hours=8))
        self.assertEqual(counter.parse_since('1794907009000')[0], expected)
        self.assertEqual(counter.parse_since('1794907009')[0], expected)

    def test_naive_local_time_uses_the_machine_timezone(self):
        naive = datetime.strptime('2026-11-17 17:16:49', '%Y-%m-%d %H:%M:%S')
        expected = int(naive.astimezone().timestamp() * 1000)
        self.assertEqual(counter.parse_since('2026-11-17 17:16:49')[0], expected)

    def test_invalid_since_is_rejected(self):
        with self.assertRaises(ValueError):
            counter.parse_since('not-a-date')


class ChooseReviews(unittest.TestCase):
    def test_window_expands_until_limit_is_available(self):
        one = [review(1)]
        enough = [review(10), review(20), review(30)]
        with mock.patch.object(
                counter, 'reviews_in_window', side_effect=[one, enough]) as fetch:
            rows, days = counter.choose_reviews(
                3, None, None, datetime.now().astimezone(), 'http://test', 1)
        self.assertEqual(fetch.call_args_list, [mock.call(1, 'http://test', 1),
                                                mock.call(7, 'http://test', 1)])
        self.assertEqual(days, 7)
        self.assertEqual([row.review_id for row in rows], [30, 20, 10])

    def test_since_filters_old_entries_before_applying_limit(self):
        now = datetime(2026, 11, 17, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        since = datetime(2026, 11, 16, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        rows = [review(99), review(200), review(300)]
        with mock.patch.object(counter, 'reviews_in_window', return_value=rows):
            selected, days = counter.choose_reviews(
                2, 150, since, now, 'http://test', 1)
        self.assertEqual(days, 2)
        self.assertEqual([row.review_id for row in selected], [300, 200])


class FetchReviews(unittest.TestCase):
    def test_cards_are_batched_and_time_zero_is_preserved(self):
        calls = []

        def fake_connect(action, params, url, timeout):
            calls.append(list(params['cards']))
            return {
                str(card_id): [{'id': card_id * 10,
                                'time': 0 if card_id == 501 else 7}]
                for card_id in params['cards']
            }

        with mock.patch.object(counter, 'connect', side_effect=fake_connect):
            rows = counter.fetch_reviews(range(1, 502), 'http://test', 1)

        self.assertEqual([len(batch) for batch in calls], [500, 1])
        self.assertEqual(len(rows), 501)
        self.assertEqual(next(row for row in rows if row.card_id == 501).time_ms, 0)
        self.assertEqual(next(row for row in rows if row.card_id == 1).time_ms, 7)


class Report(unittest.TestCase):
    def test_report_counts_zero_nonzero_cards_and_shortfall(self):
        rows = [review(3, card_id=30, time_ms=0),
                review(2, card_id=20, time_ms=1200),
                review(1, card_id=10, time_ms=0)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            counter.print_report(rows, 4, 1, None)
        text = output.getvalue()
        for line in ('total=3', 'zero=2', 'nonzero=1', 'distinct_cards=3',
                     'time_ms_min=0', 'time_ms_max=1200', 'shortfall=1'):
            self.assertIn(line, text)

    def test_main_wires_since_and_returns_zero(self):
        rows = [review(3, time_ms=0), review(2, time_ms=1200)]
        output = io.StringIO()
        with mock.patch.object(counter, 'choose_reviews', return_value=(rows, 1)) as choose, \
                contextlib.redirect_stdout(output):
            code = counter.main(['--limit', '2', '--since',
                                 '2026-11-17T17:16:49+08:00'])
        self.assertEqual(code, 0)
        self.assertEqual(choose.call_args.args[0], 2)
        self.assertEqual(choose.call_args.args[1], 1794907009000)
        self.assertIn('zero=1', output.getvalue())
        self.assertIn('nonzero=1', output.getvalue())


if __name__ == '__main__':
    unittest.main()
