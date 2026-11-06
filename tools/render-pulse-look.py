"""Look at the shipped result: a focused letter box holding a Space hint, both blink halves.

Magnified so the frame and the centred glyph can be judged as pixels rather than described.
"""
import io, os

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                    'tests', 'windows-question-audio.py'))
OUT = os.path.join(os.environ.get('TEMP', '.'), 'pulse-look')
os.makedirs(OUT, exist_ok=True)
head = io.open(TEST, encoding='utf-8').read().split('# 1. ')[0]
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), env)
app = env['app']
from PyQt6.QtCore import QPoint, QRect

dialog = env['card']('typing', word='practicable')
dialog.show()
app.processEvents()
for box, pair in list(zip(dialog.letter_boxes, dialog.letter_positions))[:3]:
    box.setText(pair[1])
dialog.letter_boxes[3].setFocus()
app.processEvents()
dialog.add_hint()
app.processEvents()

for step in (0, 1):
    dialog._pulse_step = step
    for box in dialog.letter_boxes:
        box.update()
    app.processEvents()
    dialog.repaint()
    app.processEvents()
    image = dialog.grab().toImage()
    top = dialog.letter_boxes[3].mapTo(dialog, QPoint(0, 0))
    crop = image.copy(QRect(top.x() - 46, top.y() - 6, 130, 52)).scaled(130 * 5, 52 * 5)
    path = os.path.join(OUT, 'step%d.png' % step)
    crop.save(path, 'PNG')
    print('wrote', path)
os._exit(0)
