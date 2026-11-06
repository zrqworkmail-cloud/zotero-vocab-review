"""Minimal repro attempt: build, focus a box, grab the whole dialog, delete, repeat.

The two crashing checks each build several cards in one process and grab the dialog; the
passing one builds a single card and grabs one box. This walks exactly that difference.
"""
import io, os, sys

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                    'tests', 'windows-question-audio.py'))
head = io.open(TEST, encoding='utf-8').read().split('# 1. ')[0]
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), env)
app, QTest = env['app'], env['QTest']

steps = []


def mark(text):
    steps.append(text)
    print(text)
    sys.stdout.flush()


for round_number in range(3):
    mark('round %d: build' % round_number)
    dialog = env['card']('typing', word='practicable')
    mark('round %d: focus a box' % round_number)
    dialog.letter_boxes[3].setFocus()
    app.processEvents()
    mark('round %d: add_hint' % round_number)
    dialog.add_hint()
    app.processEvents()
    mark('round %d: grab dialog' % round_number)
    image = dialog.grab().toImage()
    mark('round %d: %dx%d, reveal' % (round_number, image.width(), image.height()))
    dialog.reveal(True)
    app.processEvents()
    mark('round %d: grab answer face' % round_number)
    dialog.grab().toImage()
    mark('round %d: F look-back' % round_number)
    QTest.keyClick(dialog, env['Qt'].Key.Key_F)
    app.processEvents()
    mark('round %d: grab front again' % round_number)
    dialog.grab().toImage()
    mark('round %d: deleteLater' % round_number)
    dialog.deleteLater()
    app.processEvents()
    QTest.qWait(40)
    app.processEvents()
mark('all rounds survived')
os._exit(0)
