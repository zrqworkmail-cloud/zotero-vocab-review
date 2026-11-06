"""Name the exception the letter box's paintEvent dies on (PyQt aborts silently).

Same trick as the badge crash: call what the painter calls, from ordinary Python, so the
traceback prints instead of becoming a 0xC0000409 fastfail.
"""
import io, os, sys, traceback

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                    'tests', 'windows-question-audio.py'))
head = io.open(TEST, encoding='utf-8').read().split('# 1. ')[0]
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), env)
app = env['app']

dialog = env['card']('typing', word='practicable')
dialog.show()
app.processEvents()
box = dialog.letter_boxes[3]
box.setFocus()
app.processEvents()
for name in ('focus_ring', 'pulse_timer'):
    try:
        print('%-12s -> %r' % (name, getattr(dialog, name)(box) if name == 'focus_ring'
                               else getattr(dialog, name)()))
    except BaseException:
        print('%-12s RAISED' % name)
        traceback.print_exc()
try:
    print('cursorRect', box.cursorRect().getRect())
except BaseException:
    traceback.print_exc()
try:
    from PyQt6.QtGui import QImage, QPainter
    image = QImage(38, 40, QImage.Format.Format_ARGB32)
    painter = QPainter(box)
    print('painter active on the real box:', painter.isActive())
    painter.end()
    box.paintEvent(None)
    print('paintEvent(None) survived')
except BaseException:
    print('paintEvent RAISED')
    traceback.print_exc()
os._exit(0)
