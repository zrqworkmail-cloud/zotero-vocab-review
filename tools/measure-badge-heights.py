"""Does the badge reach the word row on a SHORT answer face? Measured by pixel diff.

The first pass of this measurement was useless in a way I have to write down: it resized the
card to 687/556/467 and reported identical numbers for all three, because `reveal()` calls
`fit_card_height()`, which snapped the window back to its content. The resize never survived.
So here the height is forced AFTER the flip, and the overlay is re-fitted to the window it is
drawn in — the way the handover does it.

Read-only. Prints, per tier and per height, the topmost pixel the celebration changes and
whether that reaches the answer word.
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
WORD = 'practicable'
MEANING = 'adj. 能实行的；适用的'


def frame(celebrate, tier, height):
    """One rendered answer face, forced to `height` AFTER the flip trimmed it."""
    cfg = dict(CFG, review_motion_celebration=celebrate)
    dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': 'typing', 'word': WORD,
                           'meaning': MEANING, 'example': 'It was a characteristic smile.',
                           'literature': '', 'options': [], 'phonetic': "præktɪkəb(ə)l"},
                          'center', lambda *_a: None, cfg)
    dialog.show()
    dialog.resize(526, 630)
    app.processEvents()
    for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText(expected)
    dialog.reveal(True)
    app.processEvents()
    dialog.resize(526, height)
    app.processEvents()
    if celebrate:
        overlay = dialog.celebration
        overlay.play(tier, cfg)
        overlay.setGeometry(dialog.rect())
        overlay.progress = 0.42
        overlay.update()
        app.processEvents()
    image = dialog.grab().toImage()
    label = dialog.answer_word
    top_left = label.mapTo(dialog, QPoint(0, 0))
    row = QRectF(top_left.x(), top_left.y(), label.width(), label.height())
    natural = dialog.layout().sizeHint().height()
    dialog.deleteLater()
    app.processEvents()
    return image, row, natural


def changed_rows(a, b):
    width, height = a.width(), a.height()
    rows = {}
    for y in range(height):
        n = sum(1 for x in range(width) if a.pixelColor(x, y) != b.pixelColor(x, y))
        if n:
            rows[y] = n
    return rows


requested = [int(arg) for arg in sys.argv[1:]] or [687, 612, 520, 460, 420]
for height in requested:
    for tier in (1, 2, 3, 4):
        plain, row, natural = frame(False, tier, height)
        badge, row, natural = frame(True, tier, height)
        rows = changed_rows(plain, badge)
        if not rows:
            print('height=%d T%d  庆祝没改变任何像素' % (height, tier))
            continue
        top = min(rows)
        in_word = sum(rows.get(y, 0) for y in range(int(row.top()), int(row.bottom()) + 1))
        verdict = '压住单词行 %d px（%d 个像素）' % (
            min(max(rows), row.bottom()) - row.top() if top <= row.bottom() else 0, in_word
        ) if in_word else '干净，徽章最高到 y=%d，单词底 y=%d' % (top, row.bottom())
        print('height=%d(自然高 %d) T%d  徽章最高 y=%-4d  %s'
              % (height, natural, tier, top, verdict))
