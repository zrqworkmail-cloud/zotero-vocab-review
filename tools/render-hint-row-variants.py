"""Render the listening card's hint row in four shapes, at the real card width.

Why a tool and not a description: five controls have to fit a ~490 px card, and whether a
shape fits is arithmetic, not opinion. Each variant re-lays the *real* QPushButtons under the
shipped stylesheet (so `#primary` and `#secondary` are the same pixels the card draws), then
grabs the whole card — what gets chosen is the card, not a sketch of it.

    python tools/render-hint-row-variants.py

Throwaway by design: nothing here is deployed and the 音标 button is a mock with no handler.
"""
import io, os, sys

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                    'tests', 'windows-question-audio.py'))
OUT = os.path.join(os.environ.get('TEMP', '.'), 'hint-variants')
os.makedirs(OUT, exist_ok=True)
src = io.open(TEST, encoding='utf-8').read()
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(src.split('# 1. ')[0], TEST, 'exec'), env)

app, Qt = env['app'], env['Qt']
QHBoxLayout, QVBoxLayout, QPushButton = env['QHBoxLayout'], env['QVBoxLayout'], env['QPushButton']
WIDTH, HEIGHT = 526, 470


def new_card():
    dialog = env['card']('listening')
    dialog.resize(WIDTH, HEIGHT)
    app.processEvents()
    return dialog


def hint_row(dialog):
    """The card's own hint QHBoxLayout, found by asking which sub-layout holds 检查拼写."""
    main = dialog.layout()
    for index in range(main.count()):
        item = main.itemAt(index)
        inner = item.layout() if item else None
        if inner is None:
            continue
        for step in range(inner.count()):
            if inner.itemAt(step).widget() is dialog.check_button:
                return inner
    raise AssertionError('hint row not found')


def clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)


def quiet(button, label):
    button.setText(label)
    button.setObjectName('secondary')
    return button


def phonetic_button(dialog):
    """The mock 看音标 control: the real widget class, no handler."""
    button = QPushButton('音标', dialog)
    button.setObjectName('secondary')
    button.clicked.connect(lambda: None)
    return button


def shot(dialog, name):
    dialog.show()
    app.processEvents()
    image = dialog.grab().toImage()
    path = os.path.join(OUT, '%s.png' % name)
    image.save(path, 'PNG')
    print('%-22s card %dx%d  min width %d' % (name, image.width(), image.height(),
                                              dialog.layout().totalMinimumSize().width()))
    dialog.deleteLater()
    app.processEvents()


# --- 0: today's row with the fifth button simply dropped in ---------------------------------
dialog = new_card()
row = hint_row(dialog)
clear(row)
row.addWidget(dialog.meaning_hint_button)
row.addWidget(phonetic_button(dialog))
row.addWidget(dialog.check_button)
row.addWidget(dialog.hint_button)
row.addWidget(dialog.answer_button)
shot(dialog, '0-today-plus-one')

# --- A: one row, three groups: aids | the action | giving up --------------------------------
dialog = new_card()
row = hint_row(dialog)
clear(row)
row.setSpacing(2)
for button, label in ((dialog.meaning_hint_button, '释义'), (phonetic_button(dialog), '音标'),
                      (dialog.hint_button, '字母 0/9')):
    row.addWidget(quiet(button, label))
row.addStretch()
dialog.check_button.setMinimumWidth(126)
row.addWidget(dialog.check_button)
row.addStretch()
row.addWidget(quiet(dialog.answer_button, '显示答案'))
shot(dialog, 'A-one-row-groups')

# --- B: aids on their own line, the action centred below -------------------------------------
dialog = new_card()
row = hint_row(dialog)
clear(row)
outer = QVBoxLayout()
outer.setSpacing(4)
aids = QHBoxLayout()
aids.setSpacing(2)
for button, label in ((dialog.meaning_hint_button, '释义'), (phonetic_button(dialog), '音标'),
                      (dialog.hint_button, '字母 0/9')):
    aids.addWidget(quiet(button, label))
aids.addStretch()
aids.addWidget(quiet(dialog.answer_button, '显示答案'))
actions = QHBoxLayout()
actions.addStretch()
dialog.check_button.setMinimumWidth(168)
actions.addWidget(dialog.check_button)
actions.addStretch()
outer.addLayout(aids)
outer.addLayout(actions)
row.addLayout(outer)
shot(dialog, 'B-aids-above')

# --- C: keep the long labels, let style and gaps do the grouping ----------------------------
dialog = new_card()
row = hint_row(dialog)
clear(row)
row.setSpacing(6)
for button, label in ((dialog.meaning_hint_button, '释义提示'), (phonetic_button(dialog), '看音标'),
                      (dialog.hint_button, '增加字母提示')):
    row.addWidget(quiet(button, label))
row.addSpacing(12)
dialog.check_button.setMinimumWidth(104)
row.addWidget(dialog.check_button)
row.addSpacing(12)
row.addWidget(quiet(dialog.answer_button, '显示答案'))
shot(dialog, 'C-long-labels')

# --- D: B, but giving up does not sit among the aids ---------------------------------------
dialog = new_card()
row = hint_row(dialog)
clear(row)
dialog.listening_explanation.hide()          # the row now says what that sentence said
dialog.status.setText('回车重听 · 空格给字母提示')
outer = QVBoxLayout()
outer.setSpacing(4)
aids = QHBoxLayout()
aids.setSpacing(2)
for button, label in ((dialog.meaning_hint_button, '释义'), (phonetic_button(dialog), '音标'),
                      (dialog.hint_button, '字母 0/9')):
    aids.addWidget(quiet(button, label))
aids.addStretch()
actions = QHBoxLayout()
actions.addStretch()
dialog.check_button.setMinimumWidth(168)
actions.addWidget(dialog.check_button)
actions.addStretch()
outer.addLayout(aids)
outer.addLayout(actions)
row.addLayout(outer)
# the two ways out of a card belong together, at the foot
main = dialog.layout()
foot = main.indexOf(dialog.later)
main.takeAt(foot)
footer = QHBoxLayout()
footer.addStretch()
footer.addWidget(quiet(dialog.answer_button, '显示答案'))
footer.addSpacing(20)
footer.addWidget(dialog.later)
footer.addStretch()
main.insertLayout(foot, footer)
shot(dialog, 'D-aids-action-foot')

print('wrote', OUT)
