"""Does the caret really sit on top of the hinted letter? Crop one box and look.

The learner reports that a Space hint is hard to read because the caret and the given letter
mix together. `next_hint_index` hands the hint to the first box after the last correct letter
-- which is the box that has focus -- and the hint is drawn as *placeholder text*, so the two
occupy the same pixel column by construction. This renders one such box, magnified, with the
caret on and with it hidden, so the claim can be seen instead of argued.
"""
import io, os

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                    'tests', 'windows-question-audio.py'))
OUT = os.path.join(os.environ.get('TEMP', '.'), 'caret-crop')
os.makedirs(OUT, exist_ok=True)
head = io.open(TEST, encoding='utf-8').read().split('# 1. ')[0]
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), env)
app, Qt = env['app'], env['Qt']
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QPainter

dialog = env['card']('typing', word='practicable')
dialog.show()
app.processEvents()
boxes = dialog.letter_boxes
for box, pair in list(zip(boxes, dialog.letter_positions))[:3]:
    box.setText(pair[1])
boxes[3].setFocus()
app.processEvents()
dialog.add_hint()
app.processEvents()
target = boxes[3]
print('hinted index lands on the focused box?',
      target is boxes[3], 'placeholder=', repr(target.placeholderText()),
      'focus=', dialog.focusWidget() is target)

for name, visible in (('caret-on', True), ('caret-off', False)):
    target.setCursorVisible(visible)
    target.repaint()
    app.processEvents()
    image = dialog.grab().toImage()
    top = target.mapTo(dialog, env['QPoint'](0, 0))
    rect = QRect(top.x(), top.y(), target.width(), target.height())
    crop = image.copy(rect)
    zoom = crop.scaled(crop.width() * 7, crop.height() * 7)
    path = os.path.join(OUT, '%s.png' % name)
    zoom.save(path, 'PNG')
    print('wrote', path, zoom.width(), 'x', zoom.height())
os._exit(0)
