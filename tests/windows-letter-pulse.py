"""The letter boxes show no caret; the focused box breathes instead (learner 2026-11-06).

Three claims, all pixel-level, because "光标和字母混在一起" is a pixel complaint:

1. **No caret.** Everything inside `cursorRect()` -- the column Qt draws the text cursor in --
   is byte-identical between the focused box and the same box unfocused.
2. **The frame is what blinks.** Two halves of the pulse differ, and every differing pixel
   lies within 3 px of the box's edge.
3. **The hinted letter is readable.** With a Space hint showing, the centre of the box is the
   same in both halves of the blink, and it is not the same as an empty box.

The preamble is exec'd from windows-question-audio.py rather than retyped, so the fixture card
and the stubbed speech cannot drift from that check.
"""
import io, os

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), 'windows-question-audio.py'))
head = io.open(TEST, encoding='utf-8').read().split('# 1. ')[0]
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), env)
app, Qt = env['app'], env['Qt']
from PyQt6.QtCore import QRect


def image_of(widget):
    widget.repaint()
    app.processEvents()
    return widget.grab().toImage()


def region(image, rect):
    return {(x, y): image.pixelColor(x, y) for y in range(rect.top(), rect.bottom())
            for x in range(rect.left(), rect.right())}


def outside_band(image_a, image_b, band):
    """Pixels that differ but are NOT inside the ring band -- the caret's hiding place."""
    left = [(x, y) for y in range(image_a.height()) for x in range(image_a.width())
            if image_a.pixelColor(x, y) != image_b.pixelColor(x, y) and not band.contains(x, y)]
    return left


dialog = env['card']('typing', word='practicable')
box = dialog.letter_boxes[3]
band = box.rect().adjusted(-3, -3, 3, 3)          # the frame and its immediate surround

# 1. No caret: the cursor column is untouched by focus.
box.clearFocus()
app.processEvents()
idle = image_of(box)
box.setFocus()
app.processEvents()
dialog._pulse_step = 0
focused = image_of(box)
caret = QRect(box.cursorRect())
assert caret.width() > 0, ('the caret rect should exist to be proven empty', caret.getRect())
assert region(idle, caret) == region(focused, caret), \
    '聚焦时光标那一列还在画东西'
assert not outside_band(idle, focused, band), \
    ('聚焦只该动边框', outside_band(idle, focused, band)[:6])

# 2. The frame really blinks, and only at the edge.
dialog._pulse_step = 1
bright = image_of(box)
assert bright != focused, '闪动没画任何东西，检查就失去意义'
assert not outside_band(focused, bright, band), \
    ('闪动只该发生在边框上', outside_band(focused, bright, band)[:6])

# 3. The hinted letter sits in the middle and survives the blink.
box.setText('')
box.setPlaceholderText('c')
app.processEvents()
first = image_of(box)
dialog._pulse_step = 4
second = image_of(box)
centre = QRect(11, 9, 16, 22)
assert region(first, centre) == region(second, centre), '提示字母跟着边框一起闪，就是看不清的那种闪'
assert region(first, centre) != region(idle, centre), '提示字母根本没画出来'

# 4. The timer follows the focus and the card, not its own mind.
assert dialog.pulse_timer().isActive(), '聚焦时闪动表必须在跑'
dialog.reveal(True)
app.processEvents()
assert not dialog.pulse_timer().isActive(), ('翻到答案面就该停表', dialog.pulse_timer().isActive())
dialog.hide()
app.processEvents()
assert not dialog.pulse_timer().isActive(), '卡片一隐藏必须停表'
dialog.deleteLater()
env['QTest'].qWait(40)

print('Qt: 字母格不再有文本光标；聚焦的格子用边框呼吸，提示字母稳稳画在正中不受影响')
os._exit(0)
