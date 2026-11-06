"""What actually happened to a card at the moment Anki said it was due.

This machine runs FSRS with `desiredRetention = 0.9` (read from the deck config on
2026-11-06). That number is a promise about the future, and the only way to audit it is
Anki's own review log: for every answer that was a real review — the card already carried an
interval of a day or more — how often was the first answer Again? Bucketed by the interval
that was asked for, that is measured retention against promised retention, and it is the
number the plug-in's hand-tuned grading weights can finally be judged next to.

The second table does the same for 已掌握. A suspended card is never tested again, so the
honest summary is not "these are known" but "these were last tested N days ago, and N keeps
growing". Nothing here unsuspends or reschedules anything; it only reads.

Rows come in as plain tuples so all of this is testable without a running Anki — the SQL
lives in the add-on, the arithmetic lives here.
"""
DAY = 86400
BUCKETS = (('≤7 天', 1, 7), ('8–30 天', 8, 30), ('31–90 天', 31, 90), ('>90 天', 91, 10 ** 9))
PARKED_BUCKETS = (('不到 90 天', 0, 90), ('90 天–1 年', 90, 365), ('1–2 年', 365, 730),
                  ('超过 2 年', 730, 10 ** 9), ('从未作答', -1, -1))


def _bucket(value, table):
    # A card with no answer at all is its own row (「从未作答」, marked by low == -1), and it
    # must be routed before any comparison — `None <= 90` is a TypeError, not a miss.
    if value is None:
        for label, low, _high in table:
            if low == -1:
                return label
        return table[-1][0]
    for label, low, high in table:
        if low == -1:
            continue
        if low <= value <= high:
            return label
    return table[-1][0]


def summarize(retention_rows, parked_rows, now=None, promised=0.9):
    """`retention_rows`: (last_ivl, rating) per review answer. `parked_rows`: days since last answer or None.

    A rating of 1 is Anki's Again — the only answer that says "I forgot", so the measured
    retention is `1 - again / answers`. Learning-step answers (interval 0) are not evidence
    about long-term retention and are left out by the caller's SQL, not silently averaged in.
    """
    import datetime
    now = now or datetime.datetime.now()
    buckets = {label: [0, 0] for label, _low, _high in BUCKETS}
    answers = 0
    agains = 0
    for last_ivl, rating in retention_rows:
        if not last_ivl or last_ivl < 1:
            continue
        label = _bucket(int(last_ivl), BUCKETS)
        buckets[label][0] += 1
        answers += 1
        if int(rating) == 1:
            buckets[label][1] += 1
            agains += 1
    parked = {label: 0 for label, _low, _high in PARKED_BUCKETS}
    for days in parked_rows:
        parked[_bucket(days, PARKED_BUCKETS)] += 1
    return {'answers': answers, 'agains': agains,
            'measured': (1.0 - float(agains) / answers) if answers else None,
            'promised': promised,
            'buckets': [(label, buckets[label][0], buckets[label][1]) for label, _l, _h in BUCKETS],
            'parked': [(label, parked[label]) for label, _l, _h in PARKED_BUCKETS],
            'parked_total': sum(parked.values()),
            'generated': now.strftime('%Y-%m-%d %H:%M')}


def render_markdown(summary, limits_text='', grading_text=''):
    """The report body. Written to user_files/reports/, and safe to read once and forget."""
    lines = ['# 复习质量报告 · %s' % summary['generated'], '']
    lines.append('## 1. 到期时点的真实保持率（对照 FSRS 承诺的 %.0f%%）' % (100 * summary['promised']))
    if not summary['answers']:
        lines.append('')
        lines.append('还没有可统计的正式复习答案（间隔 ≥1 天的卡作答记录为 0 条）。学习步长里的作答不算证据，'
                     '所以这里宁可空着，也不把 1 分钟步长的成绩当成长期保持率。')
    else:
        lines.append('')
        lines.append('| 被要求的间隔 | 作答数 | Again 数 | 实测保持率 |')
        lines.append('| --- | --- | --- | --- |')
        for label, total, again in summary['buckets']:
            rate = '—' if not total else '%.0f%%' % (100.0 * (1 - float(again) / total))
            lines.append('| %s | %d | %d | %s |' % (label, total, again, rate))
        lines.append('')
        lines.append('合计 %d 次到期作答，其中 Again %d 次 → **实测保持率 %.0f%%**（承诺 %.0f%%）。' % (
            summary['answers'], summary['agains'], 100 * summary['measured'], 100 * summary['promised']))
        gap = summary['measured'] - summary['promised']
        lines.append('')
        lines.append('读法：实测明显低于承诺，说明 Anki 把间隔拉得比你的记忆能承受的长；实测高于承诺，'
                     '说明你其实可以要更少的复习量。这个差值与插件的建议评分权重无关——那部分是另一张表。')
    lines.append('')
    lines.append('## 2. 「已掌握」= 挂起：这些词最后一次作答距今多久')
    lines.append('')
    lines.append('| 距今 | 卡数 |')
    lines.append('| --- | --- |')
    for label, total in summary['parked']:
        lines.append('| %s | %d |' % (label, total))
    lines.append('')
    lines.append('共 %d 张挂起卡。间隔重复的前提是"到点再测一次"，而挂起把卡移出了排程，所以这张表没有'
                 '"保持率"可算——它只能告诉你这些词已经多久没被检验过。要改变这一点，去设置页把'
                 '「已掌握」按钮改成"按 Easy 评分"；**本工具不会替你取消任何挂起**。' % summary['parked_total'])
    if limits_text:
        lines += ['', '## 3. 每日额度的两套数：Anki 说的 vs 今天实际发生的', '', '```', limits_text, '```',
                  '', '插件用 findCards 挑卡、answerCards 打分，不经过复习队列，所以牌组的 new/day 拦不住它。'
                       '上面出现"今日已引入 > 额度"的行就是这个事实，不是统计错误。']
    if grading_text:
        lines += ['', '## 4. 建议评分 vs 你实际按下的', '', '```', grading_text, '```']
    lines += ['', '数据来源：Anki 的 revlog 与 cards 表，只读；未改动任何排程、挂起状态或牌组配置。']
    return '\n'.join(lines) + '\n'
