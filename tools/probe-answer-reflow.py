"""Who resizes the answer face? Trace every window resize during a real reveal.

Read-only with respect to the add-on: the *installed* review_popup.py runs unmodified; this
probe only wraps `ReviewDialog.resize` in memory, so each height change is printed with the
line that asked for it, plus the layout's own heightForWidth and the tallest children at
that moment. That is what "the card grew 477 -> 583 -> 687" needs in order to be explained.
"""
from __future__ import annotations

import ctypes
import os
import sys
import traceback
import types
from pathlib import Path

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32'),
                               os.environ['SystemRoot']])
os.add_dll_directory(os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(BASE))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_PLUGIN_PATH'] = os.path.join(BASE, 'PyQt6', 'Qt6', 'plugins')
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))

from PyQt6.QtCore import QEvent, QObject, QPoint, QRectF, Qt, QTimer, QUrl, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import (QColor, QCursor, QDesktopServices, QFont, QFontDatabase, QFontMetrics,
                         QPainter)
from PyQt6.QtWidgets import (QLayout, QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStyle,
                             QVBoxLayout, QWidget)
from PyQt6.QtTest import QTest

aqt = types.ModuleType('aqt')
aqt.mw = types.SimpleNamespace()
qt = types.ModuleType('aqt.qt')
for name in ('QObject', 'QTimer', 'Qt', 'pyqtSignal', 'QEvent', 'QRectF', 'QVariantAnimation',
             'QUrl', 'QColor', 'QPainter', 'QDesktopServices', 'QMenu', 'QMessageBox', 'QCursor',
             'QFontMetrics', 'QApplication', 'QComboBox', 'QDialog', 'QHBoxLayout', 'QLabel',
             'QLineEdit', 'QPushButton', 'QScrollArea', 'QStyle', 'QSizePolicy', 'QVBoxLayout',
             'QWidget'):
    setattr(qt, name, globals()[name])
sys.modules['aqt'] = aqt
sys.modules['aqt.qt'] = qt

INSTALLED = Path(os.environ.get('APPDATA', str(Path.home()))) / 'Anki2' / 'addons21' / 'zotero_global_capture'
package = types.ModuleType('zotero_global_capture')
package.__path__ = [str(INSTALLED)]
sys.modules['zotero_global_capture'] = package
print('add-on code:', INSTALLED)

from zotero_global_capture.review_popup import ReviewDialog  # noqa: E402

app = QApplication([])
for font in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(font)
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'
aqt.mw.isActiveWindow = lambda: False
aqt.mw.isMinimized = lambda: False

# The live config the machine actually studies with (meta.json, 2026-11-19).
CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_hint_audio': True,
       'review_show_example': True, 'review_theme': 'dark', 'review_position': 'center',
       'review_plan_mode': 'fixed', 'review_batch_size': 10, 'review_mode': 'mixed',
       'model': '四六级单词模板', 'deck': 'Literature'}

MEANING = ('v. 使放松，使宽慰，缓解，使得到调剂；接替，替换，代替\n'
           'n. 变化，调剂；（使）放松，休息；解脱，减轻')
EXAMPLE = ('Drugs helped to ___ the pain.\n'
           'A massage would ___ the tension in your neck.\n'
           'He was ___ed to hear that the exam had been cancelled.')
LITERATURE = ('The medicine did little to ___ the suffering of the patients. '
              'She ___ed herself with the thought that tomorrow would be better.')

EVENTS = []


def tallest(dialog, limit=5):
    rows = []
    for widget in dialog.findChildren(QWidget):
        if not widget.isVisible():
            continue
        rows.append((widget.height(), type(widget).__name__,
                     str(getattr(widget, 'text', lambda: '')())[:26].replace('\n', ' ')
                     or widget.objectName()))
    rows.sort(reverse=True)
    return rows[:limit]


def measure(dialog, tag):
    layout = dialog.layout()
    if layout is None:            # __init__ resizes before it has built the layout
        return {'tag': tag, 'height': dialog.height(), 'sizeHint': None, 'min': None,
                'hfw': None, 'children': []}
    layout.invalidate()
    layout.activate()
    return {
        'tag': tag,
        'height': dialog.height(),
        'sizeHint': layout.sizeHint().height(),
        'min': layout.minimumSize().height(),
        'hfw': layout.heightForWidth(dialog.width()) if layout.hasHeightForWidth() else None,
        'children': tallest(dialog),
    }


class ResizeSpy(QObject):
    """Catch geometry changes that never pass through the Python `resize` override.

    Qt applies a layout's minimum size to a top-level widget on its own (the default
    SetDefaultConstraint), so a reveal can grow the window without the add-on asking.
    Only a Resize event sees both kinds.
    """

    def __init__(self):
        super().__init__()
        self.rows = []
        self.busy = False

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.Resize and isinstance(obj, ReviewDialog)
                and obj.layout() is not None):
            # Deliberately no layout.activate() here: this runs inside the resize, and
            # forcing a layout from there is what a native crash looks like.
            self.rows.append((obj.height(), obj.layout().minimumSize().height(),
                              obj.layout().sizeHint().height()))
        return False


SPY = ResizeSpy()
original = ReviewDialog.resize


def traced(self, *args, **kwargs):
    stack = traceback.extract_stack()[:-1]
    caller = stack[-1]
    before = (self.width(), self.height())
    result = original(self, *args, **kwargs)
    after = (self.width(), self.height())
    if before != after:
        EVENTS.append(measure(self, '%s:%d %s | %d -> %d' % (
            Path(caller.filename).name, caller.lineno, caller.name, before[1], after[1])))
    return result


ReviewDialog.resize = traced


def make(mode='listening', word='relieve'):
    dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': mode, 'word': word,
                           'meaning': MEANING, 'example': EXAMPLE, 'literature': LITERATURE,
                           'options': [], 'phonetic': "rɪ'liːv"},
                          'center', lambda *_a: None, dict(CFG))
    dialog.installEventFilter(SPY)
    dialog.show()
    QTest.qWait(60)
    app.processEvents()
    return dialog


def dump(title, events):
    print('\n== %s ==' % title)
    for row in events:
        print('  %-42s h=%3d sizeHint=%s min=%s hfw=%s' % (
            row['tag'], row['height'], row['sizeHint'], row['min'], row['hfw']))
        for height, kind, text in row['children'][:3]:
            print('        %-4d %-14s %s' % (height, kind, text))


for mode in ('listening', 'typing', 'cloze'):
    EVENTS.clear()
    SPY.rows.clear()
    dialog = make(mode)
    EVENTS.append(measure(dialog, 'birth'))
    dialog.reveal(True)
    app.processEvents()
    for _ in range(6):
        QTest.qWait(30)
        app.processEvents()
    EVENTS.append(measure(dialog, 'settled'))
    dump('%s card: resize calls during reveal' % mode, EVENTS)
    print('  every Resize event: h/min/sizeHint = %s' % (SPY.rows,))
    dialog.close()
    dialog.deleteLater()
    QTest.qWait(30)

# Hypothesis for the live 477 -> 583 -> 687: the 583 is not the add-on asking for a size,
# it is Qt enforcing the layout's *minimum* when the card is shorter than its own content
# (QLayout's default SetDefaultConstraint pushes the minimum onto the top-level widget).
# Squeeze a card below that minimum, poke the layout, and see who moves the window.
EVENTS.clear()
SPY.rows.clear()
squeezed = make('listening')
layout = squeezed.layout()
layout.invalidate()
layout.activate()
minimum = layout.minimumSize().height()
hint = layout.sizeHint().height()
print('\n== squeeze test: layout minimum=%d sizeHint=%d hfw=%s ==' % (
    minimum, hint, layout.heightForWidth(squeezed.width()) if layout.hasHeightForWidth() else None))
squeezed.resize(squeezed.width(), max(200, minimum - 82))
app.processEvents()
print('  squeezed to h=%d' % squeezed.height())
SPY.rows.clear()
layout.invalidate()
layout.activate()
app.processEvents()
print('  after layout activation: h=%d  resize events=%s' % (squeezed.height(), SPY.rows))

# The live card sat at 477 (its question face) when the answer arrived. Put a card in that
# exact state, reveal it, and watch whether Qt lands on an intermediate height of its own
# before the add-on's fit: that is the 583 in 477 -> 583 -> 687.
EVENTS.clear()
SPY.rows.clear()
short = make('listening')
short.resize(short.width(), 477)
app.processEvents()
print('\n== reveal from the live 477 px question face: start h=%d minimum=%d ==' % (
    short.height(), short.layout().minimumSize().height()))
SPY.rows.clear()
short.reveal(True)
app.processEvents()
for _ in range(4):
    QTest.qWait(25)
    app.processEvents()
print('  resize events (h, min, sizeHint): %s' % (SPY.rows,))
print('  python-level resizes: %s' % ([row['tag'] for row in EVENTS],))
print('  final h=%d sizeHint=%d' % (short.height(), short.layout().sizeHint().height()))

print('\n== who sets the floor: per-row minimum / sizeHint on the answer face ==')
rows = []
layout = short.layout()
for index in range(layout.count()):
    item = layout.itemAt(index)
    widget = item.widget()
    if widget is None:
        rows.append((item.minimumSize().height(), '<%s>' % type(item).__name__, '-', '-'))
        continue
    text = str(getattr(widget, 'text', lambda: '')())[:30].replace('\n', ' ')
    rows.append((widget.minimumSizeHint().height(), type(widget).__name__,
                 text or widget.objectName(), widget.sizeHint().height()))
for minimum, kind, text, hint in rows:
    print('  min=%3d hint=%3s  %-16s %s' % (minimum, hint, kind, text))
print('  layout minimum=%d sizeHint=%d' % (layout.minimumSize().height(), layout.sizeHint().height()))
inner = short.answer_scroll.widget()
if inner is not None and inner.layout() is not None:
    print('  answer_scroll content: minimum=%d sizeHint=%d (scroll floor %d)' % (
        inner.layout().minimumSize().height(), inner.sizeHint().height(),
        short.answer_scroll.minimumHeight()))

# Name the step: wrap the reveal's own sub-calls and print the layout minimum / window height
# after each. A height that changes with no resize call in sight is Qt enforcing the minimum.
EVENTS.clear()
watched = make('listening')
watched.resize(watched.width(), 477)
app.processEvents()
print('\n== step by step through reveal (start h=%d min=%d hint=%d) ==' % (
    watched.height(), watched.layout().minimumSize().height(),
    watched.layout().sizeHint().height()))


def wrap(name):
    original_method = getattr(watched, name)

    def call(*args, **kwargs):
        before = watched.height()
        result = original_method(*args, **kwargs)
        layout_now = watched.layout()
        label = str(args[0])[:14].replace('\n', ' ') if args else ''
        print('  %-16s %-14s h %3d -> %3d  min=%3d hint=%3d' % (
            name, label, before, watched.height(),
            layout_now.minimumSize().height(), layout_now.sizeHint().height()))
        return result

    setattr(watched, name, call)


for method in ('hide_front', 'add_detail', 'show_relations', 'fit_card_height',
               'ensure_row_fits'):
    wrap(method)
watched.reveal(True)
app.processEvents()
print('  settled h=%d' % watched.height())

# Replay the tail of reveal() one widget at a time on a fresh card held at 477, so the step
# that raises the floor - and with it the window - can be named.
replay = make('listening')
replay.resize(replay.width(), 477)
app.processEvents()
print('\n== replay of the reveal tail from h=%d ==' % replay.height())


def step(label, action):
    action()
    app.processEvents()
    print('  %-26s h=%3d min=%3d hint=%3d' % (
        label, replay.height(), replay.layout().minimumSize().height(),
        replay.layout().sizeHint().height()))


step('hide_front', replay.hide_front)
step('book_chip.show', replay.book_chip.show)
for heading, text in (('解释', MEANING), ('例句 1', EXAMPLE), ('权威例句', LITERATURE)):
    step('add_detail %s' % heading, lambda h=heading, t=text: replay.add_detail(h, t, audio=True))
step('result_label.show', replay.result_label.show)
step('answer_scroll.show', replay.answer_scroll.show)
step('grade_widget.show', replay.grade_widget.show)
step('later.hide', replay.later.hide)
step('fit_card_height', replay.fit_card_height)

# The proposed fix: drop the window's minimum height before the answer face is shown, so Qt
# has no floor to enforce and only the final fit_card_height() moves the window. The question
# is whether QLayout's SetDefaultConstraint writes the minimum back on the next activation.
gated = make('listening')
gated.resize(gated.width(), 477)
app.processEvents()
print('\n== proposed fix: setMinimumHeight(0) before the answer face ==')
print('  before: h=%d minimumHeight=%d layout-min=%d' % (
    gated.height(), gated.minimumHeight(), gated.layout().minimumSize().height()))
gated.hide_front()
gated.setMinimumHeight(0)
app.processEvents()
print('  after hide_front + setMinimumHeight(0): h=%d minimumHeight=%d layout-min=%d' % (
    gated.height(), gated.minimumHeight(), gated.layout().minimumSize().height()))
for heading, text in (('解释', MEANING), ('例句 1', EXAMPLE), ('权威例句', LITERATURE)):
    gated.add_detail(heading, text, audio=True)
step('result_label.show', gated.result_label.show)
step('answer_scroll.show', gated.answer_scroll.show)
step('grade_widget.show', gated.grade_widget.show)
step('later.hide', gated.later.hide)
print('  minimumHeight now=%d (did Qt write it back?)' % gated.minimumHeight())
step('fit_card_height', gated.fit_card_height)
print('  final h=%d minimumHeight=%d' % (gated.height(), gated.minimumHeight()))

# The durable version: stop the layout from imposing its minimum on the window at all
# (Qt's default SetDefaultConstraint is the thing that resized the window behind our back).
loose = make('listening')
loose.resize(loose.width(), 477)
app.processEvents()
loose.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
print('\n== alternative: layout SetNoConstraint before the answer face ==')
print('  before: h=%d minimumHeight=%d layout-min=%d' % (
    loose.height(), loose.minimumHeight(), loose.layout().minimumSize().height()))
loose.hide_front()
app.processEvents()
for heading, text in (('解释', MEANING), ('例句 1', EXAMPLE), ('权威例句', LITERATURE)):
    loose.add_detail(heading, text, audio=True)
step('result_label.show', loose.result_label.show)
step('answer_scroll.show', loose.answer_scroll.show)
step('grade_widget.show', loose.grade_widget.show)
step('later.hide', loose.later.hide)
print('  minimumHeight now=%d' % loose.minimumHeight())
step('fit_card_height', loose.fit_card_height)
print('  final h=%d sizeHint=%d' % (loose.height(), loose.layout().sizeHint().height()))


# Same measurement, but on the real reveal() path: the change is monkeypatched in memory,
# so what is measured is the add-on's own sequence with one line altered.
def reveal_with(label, setup):
    card = make('listening')
    card.resize(card.width(), 477)
    app.processEvents()
    original_reveal = ReviewDialog.reveal

    def patched(self, correct):
        if not self.answer_shown:
            setup(self)
        return original_reveal(self, correct)

    ReviewDialog.reveal = patched
    try:
        SPY.rows.clear()
        card.reveal(True)
        app.processEvents()
        for _ in range(4):
            QTest.qWait(25)
            app.processEvents()
        print('\n== real reveal, %s ==' % label)
        print('  resize events (h, layout-min, sizeHint): %s' % (SPY.rows,))
        print('  final h=%d sizeHint=%d minimumHeight=%d' % (
            card.height(), card.layout().sizeHint().height(), card.minimumHeight()))
    finally:
        ReviewDialog.reveal = original_reveal


reveal_with('baseline, no change', lambda dialog: None)
reveal_with('setMinimumHeight(0)', lambda dialog: dialog.setMinimumHeight(0))
reveal_with('layout SetNoConstraint',
            lambda dialog: dialog.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint))

