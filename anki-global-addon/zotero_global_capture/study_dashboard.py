"""Render a compact exam countdown and recent study activity."""

import datetime
import html


def activity_counts(rows, selected_ids, today):
    """Return distinct-card totals plus the new/review split for each local day.

    Anki's revlog `type` is 0 for learning (a new card), 1/2 for review/relearning,
    and 3 for a filtered-deck review.  Count distinct cards per bucket so repeated
    learning steps on one day do not inflate the number the learner sees.
    """
    selected = set(selected_ids)
    counts = {}
    for row in rows:
        if len(row) < 2:
            continue
        card_id, reviewed_ms = row[0], row[1]
        if card_id not in selected:
            continue
        day = datetime.datetime.fromtimestamp(reviewed_ms / 1000).date()
        if not 0 <= (today - day).days < 28:
            continue
        buckets = counts.setdefault(day, {'total': set(), 'new': set(), 'review': set()})
        buckets['total'].add(card_id)
        try:
            review_type = int(row[2])
        except (IndexError, TypeError, ValueError):
            review_type = None
        if review_type == 0:
            buckets['new'].add(card_id)
        elif review_type in (1, 2, 3):
            buckets['review'].add(card_id)
    return {day: {'total': len(buckets['total']), 'new': len(buckets['new']),
                  'review': len(buckets['review'])}
            for day, buckets in counts.items()}


def home_cta_html(book_name, dark=False):
    """The centred study button on Anki's deck-browser home screen."""
    palette = ('#202b3d', '#e8eef9', '#aebed7', '#40516a', '#788ef0') if dark else ('#ffffff', '#23314b', '#61718e', '#e1e7f1', '#586bd1')
    bg, fg, muted, border, accent = palette
    label = html.escape(book_name or '未选词书')
    return '''<style>
#zvr-home-start{max-width:420px;margin:14px auto 6px;padding:12px 18px;border:1px solid %s;
 border-radius:14px;background:%s;color:%s;text-align:center;box-sizing:border-box;
 box-shadow:0 10px 24px rgba(0,0,0,.10);font-family:'Segoe UI','Microsoft YaHei',sans-serif}
#zvr-home-start .zvr-home-kicker{font-size:11px;color:%s;letter-spacing:.08em}
#zvr-home-start .zvr-home-title{font-size:17px;line-height:1.25;font-weight:750;margin:2px 0 9px}
#zvr-home-start .zvr-home-button{display:inline-block;border:none;border-radius:999px;padding:8px 20px;
 background:%s;color:#fff;font-size:14px;font-weight:700;cursor:pointer;
 box-shadow:0 6px 14px rgba(0,0,0,.16);transition:background .15s,transform .15s}
#zvr-home-start .zvr-home-button:hover{background:%s;transform:translateY(-1px)}
#zvr-home-start .zvr-home-button:focus{outline:3px solid %s;outline-offset:3px}
#zvr-home-start .zvr-home-hint{font-size:11px;color:%s;margin-top:7px}
</style><section id="zvr-home-start" aria-label="开始学习">
<div class="zvr-home-kicker">单词随身复习</div>
<div class="zvr-home-title">今天从词书开始</div>
<button type="button" class="zvr-home-button" onclick="pycmd('zvr-start-review')">开始学习 · %s</button>
<div class="zvr-home-hint">换词书：工具 → 切换词书</div>
</section>''' % (border, bg, fg, muted, accent, accent, accent, muted, label)


def dashboard_html(today, deadline, plan, activity, dark=False, auto_plan=False):
    if not deadline and not auto_plan:
        return ''
    days = None
    try:
        if deadline:
            days = (datetime.date.fromisoformat(deadline) - today).days
    except ValueError:
        if not auto_plan:
            return ''
    day_text = str(days) if days is not None and days >= 0 else '已结束'
    palette = ('#202b3d', '#e8eef9', '#aebed7', '#40516a', '#788ef0') if dark else ('#ffffff', '#23314b', '#61718e', '#e1e7f1', '#586bd1')
    bg, fg, muted, border, accent = palette
    first_day = today - datetime.timedelta(days=27)
    weekdays = '一二三四五六日'
    weekday_labels = ''.join('<span>%s</span>' % weekdays[(first_day.weekday() + n) % 7] for n in range(7))
    def activity_total(entry):
        if isinstance(entry, dict):
            return int(entry.get('total') or 0)
        return int(entry or 0)

    active = [activity_total(activity.get(day, 0)) for day in activity
              if first_day <= day <= today and activity_total(activity.get(day, 0)) > 0]
    average = sum(active) / len(active) if active else 1
    colors = (['#29354a', '#344c6b', '#496b9c', '#687fd2', '#9aaeff'] if dark else
              ['#e5eaf2', '#d1ddf9', '#a9bbf2', '#7c93e0', '#536bd0'])
    squares = []
    for offset in range(27, -1, -1):
        day = today - datetime.timedelta(days=offset)
        entry = activity.get(day, {'total': 0, 'new': 0, 'review': 0})
        count = activity_total(entry)
        if isinstance(entry, dict):
            new_count = int(entry.get('new') or 0)
            review_count = int(entry.get('review') or 0)
            detail = '%s：新学 %d 个单词 · 复习 %d 个单词' % (day.isoformat(), new_count, review_count)
        else:
            detail = '%s：%d 张卡片' % (day.isoformat(), count)
        level = 0 if not count else 1 if count < average * 0.5 else 2 if count < average else 3 if count < average * 2 else 4
        outline = ';outline:2px solid %s;outline-offset:1px' % accent if day == today else ''
        column = (27 - offset) % 7
        classes = ['zvr-cell']
        if offset >= 21:
            classes.append('zvr-top')
        if column < 2:
            classes.append('zvr-left')
        elif column > 4:
            classes.append('zvr-right')
        squares.append('<button type="button" class="%s" title="%s" data-tip="%s" '
                       'aria-label="%s" style="background:%s%s"></button>' %
                       (' '.join(classes), html.escape(detail), html.escape(detail),
                        html.escape(detail), colors[level], outline))
    streak = 0
    cursor = today if activity_total(activity.get(today, 0)) else today - datetime.timedelta(days=1)
    while cursor >= first_day and activity_total(activity.get(cursor, 0)):
        streak += 1
        cursor -= datetime.timedelta(days=1)
    streak_text = ('≥%d' % streak if streak == 28 else str(streak))
    legend = ''.join('<i style="background:%s"></i>' % color for color in colors)
    new_remaining = plan.get('new_remaining', max(0, plan['new'] - plan.get('introduced', 0)))
    due = max(0, plan['due'])
    done = max(0, plan['done'])
    countdown = ('<div class="zvr-small">考试倒计时 · %s</div><div class="zvr-days">%s%s</div>' %
                 (html.escape(deadline), day_text, ' 天' if days >= 0 else '')) if days is not None else ''
    if auto_plan:
        new_done = max(0, plan['new_done'])
        new_goal = max(0, plan['new_goal'])
        review_done = max(0, plan['review_done'])
        review_goal = max(0, plan['review_goal'])
        book_total = int(plan.get('book_total') or 0)
        book_learned = int(plan.get('book_learned') or 0)
        remaining_new = plan.get('remaining_new_total', 0)
        # The tag counter in Anki's browser includes every note type; the plan counts
        # only the configured model and excludes what has already been studied. Say
        # both numbers here so 485 (tag) and 434 (new left) cannot look like a bug.
        scope = (('当前词书共 %d 张 · 已学 %d · 剩余新卡 %d 张（只统计所选笔记类型）'
                  % (book_total, book_learned, remaining_new)) if book_total else
                 ('当前范围剩余新卡 %d 张；按所选牌组和笔记类型统计。' % remaining_new))
        plan_content = ('<div class="zvr-small">今日学习计划 · 已完成 / 目标</div>'
                        '<div class="zvr-plan">新学 <b>%d / %d</b> <span>剩余 %d</span><br>'
                        '复习 <b>%d / %d</b> <span>剩余 %d</span></div>'
                        '<div class="zvr-small">%s</div>' %
                        (new_done, new_goal, new_remaining, review_done, review_goal, plan['review_remaining'],
                         scope))
    else:
        plan_content = '<div class="zvr-plan">今日建议新词 <b>%d</b>　待复习 <b>%d</b><br>今日已学习 <b>%d</b> 张卡片</div>' % (new_remaining, due, done)
    return '''<style>
#zvr-study-dashboard{position:fixed;right:18px;bottom:18px;z-index:4;width:280px;box-sizing:border-box;
 background:%s;color:%s;border:1px solid %s;border-radius:16px;padding:16px;text-align:left;
 box-shadow:0 10px 30px rgba(0,0,0,.14);font-family:'Segoe UI','Microsoft YaHei',sans-serif}
#zvr-study-dashboard .zvr-small{font-size:12px;color:%s}
#zvr-study-dashboard .zvr-days{font-size:40px;line-height:1.15;font-weight:750;color:%s}
#zvr-study-dashboard .zvr-plan{font-size:13px;line-height:1.9;margin:8px 0}
#zvr-study-dashboard .zvr-weekdays,#zvr-study-dashboard .zvr-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:5px}
#zvr-study-dashboard .zvr-weekdays{font-size:11px;text-align:center;margin-top:8px;color:%s}
#zvr-study-dashboard .zvr-grid{margin-top:4px}
#zvr-study-dashboard .zvr-grid .zvr-cell{position:relative;display:block;width:100%%;height:15px;padding:0;
 border:0;border-radius:4px;font:inherit;cursor:pointer;appearance:none}
#zvr-study-dashboard .zvr-grid .zvr-cell:hover,#zvr-study-dashboard .zvr-grid .zvr-cell:focus{z-index:3}
#zvr-study-dashboard .zvr-grid .zvr-cell::after{content:attr(data-tip);position:absolute;left:50%%;
 bottom:calc(100%% + 7px);transform:translateX(-50%%);z-index:20;min-width:180px;max-width:245px;
 padding:7px 9px;border:1px solid rgba(255,255,255,.14);border-radius:8px;background:#101827;
 color:#f8fafc;font-size:11px;font-weight:500;line-height:1.45;text-align:left;white-space:normal;
 box-shadow:0 8px 20px rgba(0,0,0,.28);opacity:0;visibility:hidden;pointer-events:none;
 transition:opacity .12s ease,visibility .12s ease}
#zvr-study-dashboard .zvr-grid .zvr-cell:hover::after,#zvr-study-dashboard .zvr-grid .zvr-cell:focus::after{
 opacity:1;visibility:visible}
#zvr-study-dashboard .zvr-grid .zvr-cell.zvr-top::after{top:calc(100%% + 7px);bottom:auto}
#zvr-study-dashboard .zvr-grid .zvr-cell.zvr-left::after{left:0;transform:none}
#zvr-study-dashboard .zvr-grid .zvr-cell.zvr-right::after{left:auto;right:0;transform:none}
#zvr-study-dashboard .zvr-legend{display:flex;align-items:center;gap:4px;margin-top:8px;font-size:11px;color:%s}
#zvr-study-dashboard .zvr-legend i{display:block;width:12px;height:12px;border-radius:3px}
@media(max-width:700px){#zvr-study-dashboard{position:static;width:min(100%%,280px);margin:16px auto}}
</style><aside id="zvr-study-dashboard" aria-label="考试与学习计划">
%s%s
<div class="zvr-small">近 28 天学习记录 · 近 28 天连续 %s 天</div>
<div class="zvr-weekdays">%s</div><div class="zvr-grid" role="group" aria-label="近 28 天每日新学与复习单词数">%s</div>
<div class="zvr-legend">少 %s 多 <span>· 颜色按学习日平均量分级</span></div></aside>''' % (
        bg, fg, border, muted, accent, muted, muted, countdown, plan_content,
        streak_text, weekday_labels, ''.join(squares), legend)
