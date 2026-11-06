"""Grab the shipped listening and spelling faces, so the redesign is judged on pixels.

The variant sheet re-laid the controls by hand; this one renders whatever the card builds
itself, which is the only way a mockup can be checked against what got implemented.
"""
import io, os

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                    'tests', 'windows-question-audio.py'))
OUT = os.path.join(os.environ.get('TEMP', '.'), 'hint-shipped')
os.makedirs(OUT, exist_ok=True)
head = io.open(TEST, encoding='utf-8').read().split('# 1. ')[0]
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), env)
app = env['app']

for mode in ('listening', 'typing'):
    for face in ('front', 'answer'):
        dialog = env['card'](mode)
        dialog.show()
        app.processEvents()
        if face == 'answer':
            for box, pair in zip(dialog.letter_boxes, dialog.letter_positions):
                box.setText(pair[1])
            dialog.check_input() if dialog.letter_boxes else dialog.reveal(True)
            app.processEvents()
        image = dialog.grab().toImage()
        path = os.path.join(OUT, '%s-%s.png' % (mode, face))
        image.save(path, 'PNG')
        print('%-10s %-7s %dx%d' % (mode, face, image.width(), image.height()))
        dialog.deleteLater()
        app.processEvents()
os._exit(0)
