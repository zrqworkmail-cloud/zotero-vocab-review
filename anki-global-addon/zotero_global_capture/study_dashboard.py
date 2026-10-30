"""Render a compact exam countdown and recent study activity."""

import datetime
import html


def activity_counts(rows, selected_ids, today):
    selected = set(selected_ids)
    counts = {}
    for card_id, reviewed_ms in rows:
        if card_id not in selected:
            continue
        day = datetime.datetime.fromtimestamp(reviewed_ms / 1000).date()
        if 0 <= (today - day).days < 28:
            counts.setdefault(day, set()).add(card_id)
    return {day: len(cards) for day, cards in counts.items()}


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
    active = [count for day, count in activity.items() if first_day <= day <= today and count > 0]
    average = sum(active) / len(active) if active else 1
    colors = (['#29354a', '#344c6b', '#496b9c', '#687fd2', '#9aaeff'] if dark else
              ['#e5eaf2', '#d1ddf9', '#a9bbf2', '#7c93e0', '#536bd0'])
    squares = []
    for offset in range(27, -1, -1):
        day = today - datetime.timedelta(days=offset)
        count = activity.get(day, 0)
        level = 0 if not count else 1 if count < average * 0.5 else 2 if count < average else 3 if count < average * 2 else 4
        outline = ';outline:2px solid %s;outline-offset:1px' % accent if day == today else ''
        squares.append('<span title="%s：%d 张卡片" aria-label="%s：%d 张卡片" style="background:%s%s"></span>' %
                       (day.isoformat(), count, day.isoformat(), count, colors[level], outline))
    streak = 0
    cursor = today if activity.get(today, 0) else today - datetime.timedelta(days=1)
    while cursor >= first_day and activity.get(cursor, 0):
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
        plan_content = ('<div class="zvr-small">今日学习计划 · 已完成 / 目标</div>'
                        '<div class="zvr-plan">新学 <b>%d / %d</b> <span>剩余 %d</span><br>'
                        '复习 <b>%d / %d</b> <span>剩余 %d</span></div>'
                        '<div class="zvr-small">当前范围剩余新卡 %d 张；按所选牌组和笔记类型统计。</div>' %
                        (new_done, new_goal, new_remaining, review_done, review_goal, plan['review_remaining'],
                         plan.get('remaining_new_total', 0)))
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
#zvr-study-dashboard .zvr-grid span{height:15px;border-radius:4px}
#zvr-study-dashboard .zvr-legend{display:flex;align-items:center;gap:4px;margin-top:8px;font-size:11px;color:%s}
#zvr-study-dashboard .zvr-legend i{display:block;width:12px;height:12px;border-radius:3px}
@media(max-width:700px){#zvr-study-dashboard{position:static;width:min(100%%,280px);margin:16px auto}}
</style><aside id="zvr-study-dashboard" aria-label="考试与学习计划">
%s%s
<div class="zvr-small">近 28 天学习记录 · 近 28 天连续 %s 天</div>
<div class="zvr-weekdays">%s</div><div class="zvr-grid">%s</div>
<div class="zvr-legend">少 %s 多 <span>· 颜色按学习日平均量分级</span></div></aside>''' % (
        bg, fg, border, muted, accent, muted, muted, countdown, plan_content,
        streak_text, weekday_labels, ''.join(squares), legend)
