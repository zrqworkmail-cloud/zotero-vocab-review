"""Build the review sheet for the hint-row variants (throwaway, mockup only).

Each card image is the real widget grabbed at the real width, so the only thing being judged
here is the arrangement. The minimum width printed under each is the layout's own arithmetic,
measured by tools/render-hint-row-variants.py.
"""
import base64, io, os

SRC = os.path.join(os.environ.get('TEMP', '.'), 'hint-variants')
DEST_DIR = os.path.join(os.path.expanduser('~'), '.qoder', 'app', 'chat-session-visualizations',
                        '317372ba-b501-456f-ba0a-c29c4c5f0185', 'visualizations')
os.makedirs(DEST_DIR, exist_ok=True)
DEST = os.path.join(DEST_DIR, 'hint-row-variants.html')

ROWS = [
    ('0-today-plus-one', '现状 + 直接塞第五个按钮',
     '五个等大的框并排，主动作「检查拼写」夹在中间，和三个可选捷径同权重；「显示答案」是"放弃这次作答"，却紧贴「检查拼写」，误点就把这题判成 Again。',
     478, '基准，不是候选'),
    ('A-one-row-groups', 'A 一排三组：提示 · 动作 · 放弃',
     '提示缩成两字并降成文字态，主动作是唯一的实心块。一行的代价：视线要在文字里找那个蓝框，而且蓝框偏右，在一张对称的卡上看着像没排好。',
     438, '省高度，但主次靠颜色硬撑'),
    ('B-aids-above', 'B 提示贴着字母格，动作独占一行居中',
     '提示是"给上面那些格子用的工具"，所以放在格子下面；实心按钮单独一行、居中，跟卡片本来就居中的单词和格子同一条轴。显示答案仍在提示行右端。',
     376, '最省宽度；放弃动作和提示混在同一行'),
    ('C-long-labels', 'C 保留长标签，只靠样式和缝隙分组',
     '文字一个不改，学习成本最低。代价是四个灰色长词连成一排像页脚，而且需要 521 px——卡片一窄就得加宽。',
     521, '改动最小，最挤'),
    ('D-aids-action-foot', 'D（推荐）B 的骨架 + 两条退路挪到页脚',
     '提示行只管工具；实心「检查拼写」单独居中；「显示答案」和「稍后再说」这两条"不做了"的路一起放到最底下，都是文字态，离主动作最远。上面那句"点击下方释义提示查看中文"删掉了——按钮自己说清楚了，底部只留一行按键提示。',
     376, '推荐'),
]


def data_url(name):
    with open(os.path.join(SRC, '%s.png' % name), 'rb') as handle:
        return 'data:image/png;base64,' + base64.b64encode(handle.read()).decode()


parts = ['''<style>
.hintsheet{margin:-28px -32px -60px;padding:28px 32px 60px;background:#12172a;color:#dbe3f4;
font:14px/1.65 'Segoe UI','Microsoft YaHei',sans-serif}
.hintsheet h1{font-size:19px;margin:0 0 6px;letter-spacing:.5px}
.hintsheet p.lead{color:#8d9bb8;margin:0 0 26px;max-width:900px}
.hintsheet .row{display:flex;gap:26px;padding:20px 0;border-top:1px solid #232c47;align-items:flex-start}
.hintsheet .row.pick{background:linear-gradient(90deg,#182348,transparent 60%);border-radius:10px}
.hintsheet img{width:392px;height:auto;border:1px solid #2a3554;border-radius:10px;display:block}
.hintsheet .text{max-width:520px}
.hintsheet h2{font-size:15px;margin:0 0 8px;color:#eaf0ff}
.hintsheet .tag{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:999px;font-size:11px;
background:#2b3a6b;color:#c9d6ff;vertical-align:2px}
.hintsheet .row.pick .tag{background:#5668ca;color:#fff}
.hintsheet small{display:block;margin-top:8px;color:#7f8cab;font-size:12px}
</style><div class="hintsheet">
<h1>听写题题目面：提示排怎么排</h1>
<p class="lead">每张图都是真控件在真机宽度 526 px 下抓出来的，只有布局被改过；「音标」按钮目前是样片，没有接逻辑。下面那个宽度数字是布局自己算出来的最小宽度，不是我估的。</p>''']

for name, title, body, width, tag in ROWS:
    pick = ' class="row pick"' if tag == '推荐' else ' class="row"'
    parts.append('<div%s><img alt="%s" src="%s"><div class="text"><h2>%s<span class="tag">%s</span></h2>'
                 '<div>%s</div><small>布局最小宽度 %d px（卡片现在 526 px）</small></div></div>'
                 % (pick, title, data_url(name), title, tag, body, width))

parts.append('</div>')
io.open(DEST, 'w', encoding='utf-8').write(''.join(parts))
print(DEST, os.path.getsize(DEST), 'bytes')
