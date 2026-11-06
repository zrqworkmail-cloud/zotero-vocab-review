"""Build the candy-style review sheet with the PNGs inlined as data URIs.

Lives in the chat's visualizations folder so it renders on Desktop and on mobile without
depending on temp-file access.
"""
import base64
import html
import os

TEMP = os.environ['TEMP']
GROUPS = (
    ('现在的样子（已部署，你否掉的）', [
        ('zvr-motion-frames/tier1.png', 'T1 · 药丸 + 彩带'),
    ]),
    ('糖果风 · 五种形态（同一张卡，真实尺寸 510×541）', [
        ('zvr-badge-v7/A-wanmei.png', 'A 星芒糖果字：字本身就是糖，奶白描边 + 果酱暗边 + 背后放射'),
        ('zvr-badge-v7/B-wanmei.png', 'B 缎带横幅：深玫红带身，两端卷角'),
        ('zvr-badge-v7/C-wanmei.png', 'C 宝石圆章：金边 + 玫红面 + 顶部釉光'),
        ('zvr-badge-v7/D-wanmei.png', 'D 果冻气泡：半透明泡体，一块大高光'),
        ('zvr-badge-v7/E-wanmei.png', 'E 星星奖牌：圆头五角星，字压在星上'),
    ]),
    ('如果按糖果风，四档就长这样（低档冷色、高档暖色，装饰只加在高档）', [
        ('zvr-badge-v7/F-t4.png', 'T4 不错 · 只有字'),
        ('zvr-badge-v7/F-t3.png', 'T3 很棒 · 短放射'),
        ('zvr-badge-v7/F-t2.png', 'T2 完美 · 满放射 + 一颗星'),
        ('zvr-badge-v7/F-t1.png', 'T1 太棒了 · 满放射 + 三颗星，字最大'),
    ]),
    ('进出编排（T1）', [
        ('zvr-badge-v7/G-fall.png', '落下 0.10s · 放大 1.19、上浮 12px、半透明'),
        ('zvr-badge-v7/G-contact.png', '触底 · 放大到 1.0，星芒张开'),
        ('zvr-badge-v7/G-lift.png', '抬起 0.20s · 上浮 16px 淡出'),
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
.badge-sheet .lede{color:#9fb0d0;margin:0 0 20px;max-width:78ch;}
.badge-sheet h2{font-size:13px;font-weight:600;color:#8fa3c8;letter-spacing:.06em;
  margin:26px 0 10px;padding-bottom:6px;border-bottom:1px solid #26304a;}
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
.badge-sheet li{margin:4px 0;}
.badge-sheet .swatches{display:flex;gap:10px;margin:10px 0 14px;flex-wrap:wrap;}
.badge-sheet .sw{font-size:12px;color:#0e1524;border-radius:6px;padding:6px 10px;font-weight:600;}
"""

SWATCHES = (('#FF5E8F', '糖粉'), ('#B01F4E', '果酱'), ('#FFF6E8', '奶白'),
            ('#FFE066', '柠檬'), ('#56C7FF', '冰蓝'), ('#1A2238', '卡底'))
swatch_html = ''.join('<span class="sw" style="background:%s">%s</span>' % (c, n)
                      for c, n in SWATCHES)

NOTES = """
<div class="notes">
  <b>色板（照消消乐的糖果语言，落在卡片自己的深蓝底上）</b>
  <div class="swatches">%s</div>
  <b>三条要说清的取舍</b>
  <ul>
    <li>糖果风必然比印章大、必然会在那 0.98 秒里盖住「回答正确」和说明行——游戏庆祝就是要把画面占满。动画一结束全部恢复，字还是那些字。</li>
    <li>字用华文琥珀（本机就有，本来就是糖果体），不额外装字体、不打包图片，插件体积不变。</li>
    <li>内置的生图服务这次连不上（endpoint 不健康，试了两次），所以五个形态全是代码画的。好处是四档文字可以随时改、深色浅色主题自适应；如果你要的是贴图级的糖，那得由你提供 PNG 素材，我按素材实现。</li>
  </ul>
</div>
""" % swatch_html

fragment = ('<div class="badge-sheet"><h1>庆祝徽章：开心消消乐糖果风，五个形态</h1>'
            '<p class="lede">全部渲染在真实卡片的像素上（真字体、真卡片、510×541），不是示意图。'
            '选一个形态，或者说要哪几个元素组合。</p>%s%s</div>'
            % (''.join(sections), NOTES))

TARGET_DIR = os.path.join(os.path.expanduser('~'), '.qoder', 'app', 'chat-session-visualizations',
                          '317372ba-b501-456f-ba0a-c29c4c5f0185', 'visualizations')
os.makedirs(TARGET_DIR, exist_ok=True)
target = os.path.join(TARGET_DIR, 'badge-candy.html')
with open(target, 'w', encoding='utf-8') as handle:
    handle.write(CSS + fragment)
print('wrote', target, os.path.getsize(target), 'bytes')
