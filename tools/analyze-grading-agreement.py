"""Does the learner accept the grade the card recommends? The one number that audits our weights.

The recommendation behind 「建议 Hard（回车/空格）」 is priced by hand — 错误字母≥4、检查失败≥2、
按位置加权字母提示、题型乘一个 MODE_WEIGHT. None of those numbers were fitted to anything, so
the honest question is not whether they look reasonable but how often they are overridden.

This reads the plug-in's own runtime log and answers that: override rate overall, the
direction of the overrides (harsher or kinder than we said), and the same split per card
type. A wrong answer is excluded from the override count because Again there was never a
choice.

    python tools/analyze-grading-agreement.py [path/to/runtime.log]
"""
import os
import re
import sys
from collections import Counter, defaultdict

LINE = re.compile(r'^(\d{4}-\d{2}-\d{2}) [\d:]+ review graded: (.*)$')
FIELDS = re.compile(r'(\w+)=(\S+)')
ORDER = ['Again', 'Hard', 'Good', 'Easy']


def parse(text):
    """Every `review graded:` line as a dict, newest order preserved."""
    rows = []
    for chunk in text.splitlines():
        match = LINE.match(chunk.strip())
        if not match:
            continue
        row = dict(FIELDS.findall(match.group(2)))
        row['date'] = match.group(1)
        rows.append(row)
    return rows


def agreement(rows):
    """Counts that separate a real disagreement from a forced rating."""
    scored = [row for row in rows if row.get('suggested', '-') not in ('-',) ]
    forced = [row for row in scored if row.get('forced') == 'again']
    free = [row for row in scored if row.get('forced') != 'again']
    same = [row for row in free if row['suggested'] == row['chosen']]
    harsher = [row for row in free if _rank(row['chosen']) < _rank(row['suggested'])]
    kinder = [row for row in free if _rank(row['chosen']) > _rank(row['suggested'])]
    return {'total': len(rows), 'with_suggestion': len(scored), 'forced': len(forced),
            'free': len(free), 'accepted': len(same), 'overridden': len(harsher) + len(kinder),
            'harsher': len(harsher), 'kinder': len(kinder),
            'by_mode': {mode: _mode_counts(rows_for(rows, mode)) for mode in sorted({row.get('mode', '-') for row in scored})},
            'pairs': Counter('%s→%s' % (row['suggested'], row['chosen']) for row in free if row['suggested'] != row['chosen'])}


def _rank(name):
    return ORDER.index(name) if name in ORDER else -1


def rows_for(rows, mode):
    return [row for row in rows if row.get('mode', '-') == mode]


def _mode_counts(rows):
    free = [row for row in rows if row.get('suggested') != '-' and row.get('forced') != 'again']
    accepted = sum(1 for row in free if row['suggested'] == row['chosen'])
    return {'free': len(free), 'accepted': accepted}


def render(summary):
    lines = ['评分对照（review graded: 行数=%d，其中有建议可对照 %d 行，其中答错强制 Again %d 行）' % (
        summary['total'], summary['with_suggestion'], summary['forced'])]
    free = summary['free']
    if not free:
        lines.append('  还没有可对照的自由评分——继续用卡片答题，或检查日志里是否有 review graded: 行。')
        return '\n'.join(lines)
    lines.append('  你按下与建议一致：%d / %d（%.1f%%）' % (summary['accepted'], free, 100.0 * summary['accepted'] / free))
    lines.append('  推翻建议：%d 次，其中改得更严 %d、改得更松 %d' % (
        summary['overridden'], summary['harsher'], summary['kinder']))
    if summary['pairs']:
        lines.append('  推翻方向明细：' + '、'.join('%s×%d' % (pair, n) for pair, n in summary['pairs'].most_common(8)))
    lines.append('  分题型：')
    for mode, counts in sorted(summary['by_mode'].items()):
        if counts['free']:
            lines.append('    %-10s 接受 %d / %d（%.0f%%）' % (
                mode, counts['accepted'], counts['free'], 100.0 * counts['accepted'] / counts['free']))
    harsher, kinder = summary['harsher'], summary['kinder']
    if free >= 40:
        if kinder and harsher >= 2 * kinder:
            lines.append('  读法：推翻多朝"更严"方向 → 建议定价偏松，权重该往上加。')
        elif harsher and kinder >= 2 * harsher:
            lines.append('  读法：推翻多朝"更松"方向 → 建议定价偏严，你在替我们改分数。')
        else:
            lines.append('  读法：两个方向差不多 → 建议与你的判断大体一致，先别动权重。')
    else:
        lines.append('  读法：样本只有 %d 条，还不够下结论（≥40 条再看方向）。' % free)
    return '\n'.join(lines)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get('TEMP') or os.path.expanduser('~'), 'zotero_global_capture_runtime.log')
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            text = handle.read()
    except OSError as error:
        raise SystemExit('读不到日志 %s：%s' % (path, error))
    print('log: %s' % path)
    print(render(agreement(parse(text))))


main()
