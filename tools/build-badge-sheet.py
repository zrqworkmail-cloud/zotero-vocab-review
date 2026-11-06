"""Build the review sheet for the celebration badge, with the PNGs inlined as data URIs.

The sheet lives in the chat's visualizations folder so it renders on the Desktop and on
mobile without depending on temp-file access.
"""
import base64
import html
import os

TEMP = os.environ['TEMP']
GROUPS = (
    ('现在的样子（已部署）', [
        ('zvr-motion-frames/tier1.png', 'T1 不可思议 · 药丸 + 彩带'),
        ('zvr-motion-frames/tier4.png', 'T4 不错 · 只有一行字'),
    ]),
    ('新方案 · 一枚朱批（同一张卡，真实尺寸 510×541）', [
        ('zvr-badge-v6/t4-liang-land.png', 'T4 → 良'),
        ('zvr-badge-v6/t3-you-land.png', 'T3 → 优'),
        ('zvr-badge-v6/t2-miao-land.png', 'T2 → 妙'),
        ('zvr-badge-v6/t1-shen-land.png', 'T1 → 神'),
    ]),
    ('进入 / 触底 / 抬起（T1 才有挤出的墨点）', [
        ('zvr-badge-v6/t1-shen-fall.png', '落下 0.10s · 放大 1.26，偏 -6.5°'),
        ('zvr-badge-v6/t1-shen-contact.png', '触底 · 墨点挤出，120ms 内消失'),
        ('zvr-badge-v6/t1-shen-lift.png', '抬起 0.20s · 上浮淡出'),
    ]),
    ('尺寸对照：66 是唯一不压字的宽度', [
        ('zvr-badge-v6/t1-shen-size80.png', '80px · 压住例句框和说明行（否掉）'),
    ]),
)


def data_uri(path):
    with open(path, 'rb') as handle:
        return 'data:image/png;base64,' + base64.b64encode(handle.read()).decode('ascii')


sections = []
for title, items in GROUPS:
    cells = []
    for rel, caption in items:
        source = os.path.join(TEMP, *rel.split('/'))
        if not os.path.exists(source):
            cells.append('<div class="cell"><div class="missing">缺 %s</div><p>%s</p></div>'
                         % (html.escape(rel), html.escape(caption)))
            continue
        cells.append('<div class="cell"><img src="%s" alt="%s"><p>%s</p></div>'
                     % (data_uri(source), html.escape(caption), html.escape(caption)))
    sections.append('<h2>%s</h2><div class="row">%s</div>' % (html.escape(title), ''.join(cells)))

CSS = """
.badge-sheet{font:15px/1.6 "Segoe UI","Microsoft YaHei",sans-serif;color:#e8edf7;
  background:#141a2b;padding:26px 28px 34px;}
.badge-sheet h1{font-size:20px;margin:0 0 4px;letter-spacing:.02em;}
.badge-sheet .lede{color:#9fb0d0;margin:0 0 22px;max-width:76ch;}
.badge-sheet h2{font-size:13px;font-weight:600;color:#8fa3c8;letter-spacing:.10em;
  text-transform:uppercase;margin:26px 0 10px;padding-bottom:6px;border-bottom:1px solid #26304a;}
.badge-sheet .row{display:flex;flex-wrap:wrap;gap:16px;}
.badge-sheet .cell{margin:0;}
.badge-sheet img{display:block;width:298px;height:auto;border-radius:8px;
  border:1px solid #2b3652;background:#1a2238;}
.badge-sheet p{font-size:12.5px;color:#93a6c9;margin:7px 0 0;max-width:298px;}
.badge-sheet .missing{width:298px;height:120px;line-height:120px;text-align:center;
  color:#e2a3a3;border:1px dashed #4a3a4a;border-radius:8px;}
.badge-sheet .notes{margin:24px 0 0;padding:14px 16px;background:#1b2338;border-radius:8px;
  border:1px solid #2b3652;font-size:13.5px;color:#c3cfe6;}
.badge-sheet .notes b{color:#f0d9b5;font-weight:600;}
.badge-sheet .notes ul{margin:8px 0 0;padding-left:20px;}
.badge-sheet li{margin:3px 0;}
"""

NOTES = """
<div class="notes">
  <b>为什么换成一枚朱批</b>
  <ul>
    <li>取的是篆刻白文（红底白字）和老师朱批「良 / 优 / 妙 / 神」：冲击力来自正负形和一个大字，不来自渐变和装饰堆。</li>
    <li>四字印在 66px 里每字只剩 20px，而且右起竖读在屏幕上读不通，所以一档一个字。</li>
    <li>量过卡片：例句框底 348、说明行顶 414，中间只有 66px 空带，正好落在「回答正确」右边；80px 就会压住例句框和说明行。</li>
    <li>「回答正确」由绿色改成纸白：朱砂撞绿像贺卡，强调只留给印章一处。</li>
    <li>彩带和星芒换成落印一瞬被挤出的几点墨，只在触底 120ms 内出现；T1/T2 有，T3/T4 只有印。</li>
    <li>覆盖层不吃鼠标，Enter 随时能走，动画不挡翻页。</li>
  </ul>
</div>
"""

fragment = ('<div class="badge-sheet"><h1>庆祝徽章：从药丸改成一枚朱批</h1>'
            '<p class="lede">全部渲染在真实卡片的像素上（真字体库、真卡片、510×541），'
            '不是示意图。选一个方向，或者说哪里还要改。</p>%s%s</div>'
            % (''.join(sections), NOTES))

TARGET_DIR = os.path.join(os.path.expanduser('~'), '.qoder', 'app', 'chat-session-visualizations',
                          '317372ba-b501-456f-ba0a-c29c4c5f0185', 'visualizations')
os.makedirs(TARGET_DIR, exist_ok=True)
target = os.path.join(TARGET_DIR, 'badge-seal.html')
with open(target, 'w', encoding='utf-8') as handle:
    handle.write(CSS + fragment)
print('wrote', target, os.path.getsize(target), 'bytes')
