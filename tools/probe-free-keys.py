"""Which keys are actually free on the spelling face, and what they do today.

The learner wants a keyboard route to the 音标 hint. Space already gives a letter and Enter
already submits, so the candidate has to be a *modified* key -- and every bare letter goes
into the box being typed. This drives the real widget with the full press+release pair and
reports what each key currently does, on the question face and on the answer face.
"""
import io, os

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                    'tests', 'windows-question-audio.py'))
head = io.open(TEST, encoding='utf-8').read().split('# 1. ')[0]
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), env)
app, Qt = env['app'], env['Qt']
QEvent = env['QEvent']
from PyQt6.QtGui import QKeyEvent

MODS = {
    'Space': Qt.KeyboardModifier.NoModifier,
    'Shift+Space': Qt.KeyboardModifier.ShiftModifier,
    'Ctrl+Space': Qt.KeyboardModifier.ControlModifier,
    'Alt+Space': Qt.KeyboardModifier.AltModifier,
    'Shift+Enter': Qt.KeyboardModifier.ShiftModifier,
    'Ctrl+Enter': Qt.KeyboardModifier.ControlModifier,
    'Tab': Qt.KeyboardModifier.NoModifier,
    'F1': Qt.KeyboardModifier.NoModifier,
    'F2': Qt.KeyboardModifier.NoModifier,
    'Backslash': Qt.KeyboardModifier.NoModifier,
    'Slash': Qt.KeyboardModifier.NoModifier,
}
KEYS = {'Space': Qt.Key.Key_Space, 'Shift+Space': Qt.Key.Key_Space,
        'Ctrl+Space': Qt.Key.Key_Space, 'Alt+Space': Qt.Key.Key_Space,
        'Shift+Enter': Qt.Key.Key_Return, 'Ctrl+Enter': Qt.Key.Key_Return,
        'Tab': Qt.Key.Key_Tab, 'F1': Qt.Key.Key_F1, 'F2': Qt.Key.Key_F2,
        'Backslash': Qt.Key.Key_Backslash, 'Slash': Qt.Key.Key_Slash}
SPOKEN = []


def send(widget, name):
    key, mods = KEYS[name], MODS[name]
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication = env['QApplication']
        QApplication.sendEvent(widget, QKeyEvent(kind, key, mods))
    app.processEvents()


def state(dialog):
    return {'字母格': ''.join(box.text() for box in dialog.letter_boxes),
            '提示次数': dialog.hint_uses, '字母提示': dialog.hints,
            '已发音': bool(SPOKEN), '答案面': dialog.answer_shown,
            '焦点': type(dialog.focusWidget()).__name__ if dialog.focusWidget() else None}


for face in ('question', 'answer'):
    print('== %s face ==' % face)
    for name in MODS:
        env['ReviewDialog'].speak_many = lambda self, texts: SPOKEN.extend(texts) or True
        dialog = env['card']('typing', word='practicable')
        for box, pair in list(zip(dialog.letter_boxes, dialog.letter_positions))[:2]:
            box.setText(pair[1])
        if face == 'answer':
            dialog.check_input()
        else:
            dialog.letter_boxes[2].setFocus()
        app.processEvents()
        before = state(dialog)
        target = dialog.focusWidget() or dialog
        send(target, name)
        after = state(dialog)
        verdict = 'nothing' if before == after else ('%s -> %s' % (before, after))
        print('   %-13s %s' % (name, verdict))
        dialog.deleteLater()
        app.processEvents()
os._exit(0)
