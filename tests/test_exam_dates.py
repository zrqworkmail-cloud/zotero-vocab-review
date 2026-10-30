import datetime
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'anki-global-addon/zotero_global_capture/exam_dates.py'
spec = importlib.util.spec_from_file_location('exam_dates', path)
exam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exam)


class ExamDateTests(unittest.TestCase):
    def test_official_page_extracts_written_date_only(self):
        html = '<h4>2026年下半年考试时间：</h4><li>笔试：12-12</li><li>口语：11-21</li>'
        self.assertEqual(exam.parse_cet(html, datetime.date(2026, 10, 28)), '2026-12-12')

    def test_missing_invalid_and_expired_dates_fail_closed(self):
        for page in ('日期待定', '2026年下半年考试时间：笔试：13-99', '2025年下半年考试时间：笔试：12-12'):
            with self.assertRaises(ValueError):
                exam.parse_cet(page, datetime.date(2026, 10, 28))
