"""Read the current CET written-exam date from the official registration page."""
import datetime
import re
import urllib.request
from html.parser import HTMLParser

CET_URL = 'https://cet-kw.neea.edu.cn/Home/Index'


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
    def handle_data(self, value):
        self.text.append(value)


def parse_cet(page, today=None):
    parser = _Text()
    parser.feed(page)
    text = ' '.join(parser.text)
    match = re.search(r'(20\d{2})\s*年\s*(?:上|下)半年考试时间\s*[:：]\s*笔试\s*[:：]\s*(\d{1,2})\s*[-月]\s*(\d{1,2})', text)
    if not match:
        raise ValueError('官方页面未提供可识别的四六级笔试日期')
    try:
        day = datetime.date(*map(int, match.groups()))
    except ValueError as error:
        raise ValueError('官方页面中的考试日期无效') from error
    if day < (today or datetime.date.today()):
        raise ValueError('官方页面显示的考试日期已过，下一次日期尚未确认')
    return day.isoformat()


def fetch_cet():
    request = urllib.request.Request(CET_URL, headers={'User-Agent': 'Mozilla/5.0 (compatible; AnkiVocabularyReview/1.0)'})
    with urllib.request.urlopen(request, timeout=8) as response:
        page = response.read(1024 * 1024).decode('utf-8', errors='replace')
    return parse_cet(page)
