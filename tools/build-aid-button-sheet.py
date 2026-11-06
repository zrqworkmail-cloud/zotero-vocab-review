"""Sheet for the aid-button variants, so the choice is made on pixels."""
import base64, io, os

SRC = os.path.join(os.environ.get('TEMP', '.'), 'aid-buttons')
DEST_DIR = os.path.join(os.path.expanduser('~'), '.qoder', 'app', 'chat-session-visualizations',
                        '317372ba-b501-456f-ba0a-c29c4c5f0185', 'visualizations')
os.makedirs(DEST_DIR, exist_ok=True)
DEST = os.path.join(DEST_DIR, 'aid-button-variants.html')

ROWS = [
    ('A-outline', 'A 描边小按钮', '卡片默认按钮的样子，矮一号（padding 5x11、12 px 字）。'
     '和主动作的差别就剩"填不填充"，扫一眼能分出"这是工具 / 这是提交"。每个 71x28 px，'
     '三个连排 213 px，行内余量很大，不会把卡片撑宽。', '推荐'),
    ('B-filled', 'B 浅底键帽', '去掉边框、底色比卡片亮一档，最像"键"。代价是三个提示和检查拼写'
     '都成了实心块，主次要靠颜色深浅来分，深色主题下这个差别比描边更难读。', '可接受'),
    ('C-underlined', 'C 下划线文字', '最轻的一种，仍然表明可点（实测这套 Qt 认 text-decoration）。'
     '代价是答案面的例句来源里已经在用下划线链接，同一张卡上"下划线"就有两个意思。', '有歧义'),
]


def data_url(name):
    with open(os.path.join(SRC, '%s.png' % name), 'rb') as handle:
        return 'data:image/png;base64,' + base64.b64encode(handle.read()).decode()


parts = ['''<style>.aidsheet{margin:-28px -32px -60px;padding:26px 32px 54px;background:#12172a;
color:#dbe3f4;font:14px/1.7 'Segoe UI','Microsoft YaHei',sans-serif}
.aidsheet h1{font-size:19px;margin:0 0 6px}.aidsheet p.lead{color:#8d9bb8;margin:0 0 22px;max-width:920px}
.aidsheet .row{display:flex;gap:24px;padding:18px 0;border-top:1px solid #232c47}
.aidsheet .row.pick{background:linear-gradient(90deg,#182348,transparent 60%);border-radius:10px}
.aidsheet img{width:372px;height:auto;border:1px solid #2a3554;border-radius:10px}
.aidsheet .text{max-width:520px}.aidsheet h2{font-size:15px;margin:0 0 8px;color:#eaf0ff}
.aidsheet .tag{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:999px;
font-size:11px;background:#2b3a6b;color:#c9d6ff;vertical-align:2px}
.aidsheet .row.pick .tag{background:#5668ca;color:#fff}</style>
<div class="aidsheet"><h1>提示那三个控件，怎么让人看出能点</h1>
<p class="lead">三张都是在真机上跑的听写题卡片，只有提示那三个控件的样式被换掉；检查拼写、'
'页脚两条退路、格子边框呼吸都保持现在的样子。</p>''']

for name, title, body, tag in ROWS:
    pick = ' class="row pick"' if tag == '推荐' else ' class="row"'
    parts.append('<div%s><img alt="%s" src="%s"><div class="text"><h2>%s<span class="tag">%s'
                 '</span></h2><div>%s</div></div></div>'
                 % (pick, title, data_url(name), title, tag, body))
parts.append('</div>')
io.open(DEST, 'w', encoding='utf-8').write(''.join(parts))
print(DEST, os.path.getsize(DEST))
