"""Where does the badge actually paint? Diff the same card with the celebration off and on.

Why not colour: a first attempt looked for the badge's gold pixels and "found" the badge
covering the answer word in 8/8 live captures. Those pixels were **ClearType fringes** —
Windows draws the left and right edges of a glyph in warm and cool colours, and a warm
(238,206,149) edge reads exactly like gold. Colour heuristics cannot locate a gold object on
a card full of subpixel-rendered text.

So this renders one card twice at the live size — once with the celebration switch off, once
with it on and driven to its largest pose — and the difference IS the badge, in pixels, with
no guessing about what colour it is.

Read-only. Writes PNGs under /tmp and prints numbers.
"""
import os
import sys
import types

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32')])
os.add_dll_directory(os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(BASE))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_PLUGIN_PATH'] = os.path.join(BASE, 'PyQt6', 'Qt6', 'plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))

from PyQt6.QtCore import QObject, QPoint, QEvent, QRectF, Qt, QTimer, QVariantAnimation, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFontDatabase, QDesktopServices, QFontMetrics, QPainter
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStyle,
                             QVBoxLayout, QWidget)

aqt = types.ModuleType('aqt')
aqt.mw = types.SimpleNamespace()
qt = types.ModuleType('aqt.qt')
for name in ('QObject', 'QTimer', 'Qt', 'pyqtSignal', 'QEvent', 'QRectF', 'QVariantAnimation',
             'QUrl', 'QColor', 'QPainter', 'QDesktopServices', 'QMenu', 'QMessageBox', 'QCursor',
             'QFontMetrics', 'QApplication', 'QComboBox', 'QDialog', 'QHBoxLayout', 'QLabel',
             'QLineEdit', 'QPushButton', 'QScrollArea', 'QStyle', 'QVBoxLayout', 'QWidget'):
    setattr(qt, name, globals()[name])
sys.modules['aqt'] = aqt
sys.modules['aqt.qt'] = qt
package = types.ModuleType('zotero_global_capture')
package.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                                 'anki-global-addon', 'zotero_global_capture'))]
sys.modules['zotero_global_capture'] = package

from zotero_global_capture.review_popup import ReviewDialog
from zotero_global_capture import motion_view

app = QApplication([])
for font in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(font)
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'
aqt.mw.isActiveWindow = lambda: False
aqt.mw.isMinimized = lambda: False

CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_theme': 'dark',
       'review_position': 'center', 'review_plan_mode': 'fixed', 'review_batch_size': 10,
       'model': '四六级单词模板', 'deck': 'Literature',
       'review_motion_hop': True, 'review_motion_celebration': True}
CARD = (int(os.environ.get('ZVR_W', 526)), int(os.environ.get('ZVR_H', 687)))
                           # the live captures reported 526x687; the two-way
                           # fitting now makes answer faces much shorter
# Which tier to measure comes from argv: rendering several tiers in one process
# segfaults, so the honest way to compare them is one process each.
TIER = int(sys.argv[1]) if len(sys.argv) > 1 else 1
WORDS = [('practicable', 'adj. 能实行的；适用的')]


def build(word, meaning):
    dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': 'typing', 'word': word,
                           'meaning': meaning, 'example': 'It was a characteristic smile.',
                           'literature': '这是一条文学例句。', 'options': [],
                           'phonetic': "præktɪkəb(ə)l"},
                          'center', lambda *_a: None, dict(CFG))
    dialog.show()
    dialog.resize(*CARD)
    app.processEvents()
    for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText(expected)
    return dialog


def paint(dialog, celebrate):
    cfg = dict(CFG, review_motion_celebration=celebrate)
    dialog.cfg = cfg
    dialog.reveal(True)
    app.processEvents()
    if celebrate:
        overlay = dialog.celebration
        overlay.play(TIER, cfg)
        overlay.progress = 0.42              # the largest pose, where it covers the most
        overlay.update()
        app.processEvents()
    image = dialog.grab().toImage()
    return image


def diff(a, b):
    """The bounding box of pixels that only exist when the celebration is on."""
    width, height = a.width(), a.height()
    top = bottom = left = right = None
    for y in range(height):
        line_changed = False
        for x in range(0, width, 1):
            if a.pixelColor(x, y) != b.pixelColor(x, y):
                line_changed = True
                if left is None or x < left:
                    left = x
                right = x
        if line_changed:
            if top is None:
                top = y
            bottom = y
    return QRectF(left or 0, top or 0, (right or 0) - (left or 0) + 1,
                  (bottom or 0) - (top or 0) + 1) if top is not None else None


def word_row_rect(dialog):
    label = dialog.answer_word
    top_left = label.mapTo(dialog, QPoint(0, 0))
    return QRectF(top_left.x(), top_left.y(), label.width(), label.height())


for word, meaning in WORDS:
    dialog = build(word, meaning)
    plain = paint(dialog, False)
    dialog.deleteLater()
    app.processEvents()
    dialog = build(word, meaning)
    with_badge = paint(dialog, True)
    row = word_row_rect(dialog)
    box = diff(plain, with_badge)
    plain.save('/tmp/plain-%s.png' % word)
    with_badge.save('/tmp/badge-%s.png' % word)
    if box is None:
        print('%-16s 庆祝没有改变任何像素——开关或渲染没生效，先修探针' % word)
        continue
    overlap = box.intersects(row)
    print('%-16s 徽章实际覆盖 y %d-%d (x %d-%d)，单词行 y %d-%d → %s'
          % (word, box.top(), box.bottom(), box.left(), box.right(),
             row.top(), row.bottom(),
             '压住 %d px' % (min(box.bottom(), row.bottom()) - max(box.top(), row.top()))
             if overlap else '干净，相距 %d px' % (box.top() - row.bottom())))
    dialog.deleteLater()
    app.processEvents()
