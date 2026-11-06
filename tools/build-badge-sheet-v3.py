"""Build the animated review sheet: the real 16-frame sequence, looped at the real 980ms.

The frames come out of `tools/render-candy-frames.py`, which calls the shipped
`candy_badge.draw` and `card_motion.badge_pose`, so the loop is the same arithmetic Anki
will run — not a hand-drawn approximation of it.
"""
import base64
import io
import json
import os

from PIL import Image

TEMP = os.path.join(os.environ['TEMP'], 'zvr-candy-frames')
FRAMES = 16
DISPLAY_WIDTH = 320      # the sheet shows it at 288; 320 keeps it sharp on a phone


def uri(name):
    """Embed a downscaled JPEG. The full-size PNGs blow the 1 MB fragment limit."""
    with Image.open(os.path.join(TEMP, name)) as source:
        scaled = source.convert('RGB').resize(
            (DISPLAY_WIDTH, int(source.height * DISPLAY_WIDTH / source.width)),
            Image.LANCZOS)
        buffer = io.BytesIO()
        scaled.save(buffer, 'JPEG', quality=82, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


sequence = [uri('t1-%02d.png' % index) for index in range(FRAMES)]
holds = [(uri('hold-t%d.png' % tier), 'T%d %s' % (tier, label))
         for tier, label in ((2, 'PERFECT · 完美'), (3, 'GREAT · 很棒'), (4, 'NICE · 不错'))]
themes = [(uri('light-t1.png'), '浅色主题'), (uri('light-t4.png'), '浅色 · 最低档')]
wide = uri('t1-longword.png')

CSS = """
.candy-review{font:15px/1.6 "Segoe UI","Microsoft YaHei",sans-serif;color:#e8edf7;
  background:#141a2b;padding:26px 28px 34px;}
.candy-review h1{font-size:20px;margin:0 0 4px;}
.candy-review .lede{color:#9fb0d0;margin:0 0 18px;max-width:80ch;}
.candy-review h2{font-size:13px;font-weight:600;color:#8fa3c8;letter-spacing:.06em;
  margin:26px 0 10px;padding-bottom:6px;border-bottom:1px solid #26304a;}
.candy-review .row{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start;}
.candy-review figure{margin:0;}
.candy-review img{display:block;width:288px;height:auto;border-radius:8px;
  border:1px solid #2b3652;background:#1a2238;}
.candy-review figcaption{font-size:12.5px;color:#93a6c9;margin:7px 0 0;max-width:288px;}
.candy-review .stage{position:relative;width:288px;height:306px;border-radius:8px;
  border:1px solid #2b3652;overflow:hidden;background:#1a2238;}
.candy-review .stage img{position:absolute;inset:0;width:100%;height:100%;opacity:0;
  transition:opacity .04s linear;}
.candy-review .stage img.on{opacity:1;}
.candy-review .controls{margin:10px 0 0;display:flex;gap:10px;align-items:center;}
.candy-review button{font:inherit;font-size:13px;padding:6px 14px;border-radius:6px;
  border:1px solid #3a4768;background:#1f2942;color:#dce6fb;cursor:pointer;}
.candy-review button:hover{background:#28345a;}
.candy-review .rate{font-size:12.5px;color:#93a6c9;}
.candy-review .notes{margin:24px 0 0;padding:14px 16px;background:#1b2338;border-radius:8px;
  border:1px solid #2b3652;font-size:13.5px;color:#c3cfe6;}
.candy-review .notes ul{margin:8px 0 0;padding-left:20px;}
.candy-review .notes li{margin:4px 0;}
.candy-review .notes b{color:#f0d9b5;}
"""

JS = """
(function(){
  var frames=%s;
  var stage=document.getElementById('candy-stage');
  frames.forEach(function(src,index){
    var img=document.createElement('img');
    img.src=src; img.dataset.index=index;
    if(index===0){img.className='on';}
    stage.appendChild(img);
  });
  var images=[].slice.call(stage.images);
  var timer=null, index=0;
  // 980ms for the whole celebration, 16 frames -> 61ms a frame.
  function step(){
    index=(index+1)%%frames.length;
    images.forEach(function(img,i){img.classList.toggle('on', i===index);});
  }
  function start(){ stop(); timer=setInterval(step, 61); }
  function stop(){ if(timer){clearInterval(timer); timer=null;} }
  document.getElementById('candy-play').addEventListener('click', function(){
    if(timer){stop(); this.textContent='播放';} else {start(); this.textContent='暂停';}
  });
  document.getElementById('candy-once').addEventListener('click', function(){
    stop(); document.getElementById('candy-play').textContent='播放';
    var i=0;
    images.forEach(function(img){img.classList.remove('on');});
    images[0].classList.add('on');
    var one=setInterval(function(){
      i++; if(i>=frames.length){clearInterval(one); return;}
      images.forEach(function(img,j){img.classList.toggle('on', j===i);});
    }, 61);
  });
  start();
})();
""" % json.dumps(sequence)

holds_html = ''.join('<figure><img src="%s"><figcaption>%s</figcaption></figure>'
                     % (src, label) for src, label in holds)
themes_html = ''.join('<figure><img src="%s"><figcaption>%s</figcaption></figure>'
                      % (src, label) for src, label in themes)

HTML = CSS + """
<div class="candy-review">
  <h1>庆祝动效：金色立体字，按你给的参考图做</h1>
  <p class="lede">下面这段循环就是插件真正会跑的 16 帧，时长 980 毫秒——帧是从
  <code>candy_badge.draw</code> + <code>card_motion.badge_pose</code> 直接渲染在真实卡片像素上的，
  不是手绘示意图。</p>

  <h2>T1 不可思议 / UNBELIEVABLE · 完整进出循环</h2>
  <div class="row">
    <div>
      <div class="stage" id="candy-stage"></div>
      <div class="controls">
        <button id="candy-play">暂停</button>
        <button id="candy-once">只放一遍</button>
        <span class="rate">980ms = 260 进 + 520 停 + 200 出</span>
      </div>
    </div>
    <figure><img src="__WIDE__"><figcaption>12 个字母自动缩号，宽不过卡片的 78%</figcaption></figure>
  </div>

  <h2>另外三档（静止帧）</h2>
  <div class="row">__HOLDS__</div>

  <h2>浅色主题</h2>
  <div class="row">__THEMES__</div>

  <div class="notes">
    <b>照参考图做的地方</b>
    <ul>
      <li>字是主体：金色三段渐变面 + 向右下挤出的洋红侧壁 + 一整圈奶白描边（面和侧壁共用一条轮廓，所以像贴纸而不像带阴影的字）。</li>
      <li>背后放射光、四角星闪光、上方三星、下方缎带压宝石——都是参考图里那几件东西。</li>
      <li>档位阶梯：T1 三星+放射+5 闪光+宽光晕；T2 三星+放射；T3 只有放射；T4 只有字+缎带+宝石。缎带里的中文（不可思议/完美/很棒/不错）保留。</li>
    </ul>
    <b>透明处理</b>
    <ul>
      <li>覆盖层是透明图层，不是面板：四周完全不吃像素，卡片上的字照常能读。</li>
      <li>光晕和放射的渐变最后一站强制 alpha=0，并且画的时候缩放的是画笔而不是形状——之前把圆形渐变塞进扁椭圆，边界停在 74% 处，卡面上露出一圈紫边。</li>
      <li>闸门里加了硬检查：把徽章画进带 alpha 的图，六个边角像素必须等于 0，字心必须不透明，整张卡被画到的面积必须小于半张。四个档位都跑。</li>
    </ul>
    <b>动效</b>
    <ul>
      <li>进：从 0.28 倍、偏 −14°、透明，弹冲到 1.14 倍再落回 1.0；缎带比字晚到（字先砸下来，缎带随后滑入）。</li>
      <li>出：末 200ms 放大到 1.08、转正 3°、淡到 0，不是硬切。</li>
      <li>覆盖层不吃鼠标、不设焦点，Enter 随时翻页；换卡即停，不会留到下一张。</li>
    </ul>
  </div>
</div>
""".replace('__WIDE__', wide).replace('__HOLDS__', holds_html).replace('__THEMES__', themes_html)

TARGET_DIR = os.path.join(os.path.expanduser('~'), '.qoder', 'app', 'chat-session-visualizations',
                          '317372ba-b501-456f-ba0a-c29c4c5f0185', 'visualizations')
os.makedirs(TARGET_DIR, exist_ok=True)
target = os.path.join(TARGET_DIR, 'badge-candy-live.html')
with open(target, 'w', encoding='utf-8') as handle:
    handle.write(HTML + '<script>' + JS + '</script>')
print('wrote', target, os.path.getsize(target), 'bytes')
