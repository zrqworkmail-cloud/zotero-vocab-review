"""Render the real celebration widget to PNG frames, so the look can be judged without
racing a one-second animation on the desktop.

This is not a mockup: it drives the shipped `motion_view.Celebration` widget inside a real
`ReviewDialog`, with the shipped dark theme, and grabs the composited pixels. It answers two
questions at once:

1. What does each tier's badge actually look like?
2. Is the overlay a see-through layer, or an opaque box that hides the card behind it?
   The check samples pixels far from the badge and compares them with the same pixels taken
   with no overlay at all. Equal means the card shows through.

Throwaway verification tool; the images go to %TEMP%/zvr-motion-frames/.
"""
import os
import sys
import tempfile
import types

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32'),
                               os.environ['SystemRoot']])
for _d in (os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE)):
    os.add_dll_directory(_d)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_PLUGIN_PATH'] = os.path.join(BASE, 'PyQt6', 'Qt6', 'plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))

from PyQt6.QtCore import (QObject, QTimer, Qt, pyqtSignal, QEvent, QEasingCurve, QRectF,
                         QVariantAnimation, QUrl, QPoint)
from PyQt6.QtGui import (QCursor, QFont, QFontDatabase, QFontMetrics, QColor, QPainter,
                         QDesktopServices, QImage)
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QMessageBox, QPushButton, QScrollArea, QStyle, QVBoxLayout, QWidget)

aqt = types.ModuleType('aqt')
aqt.mw = types.SimpleNamespace()
qt = types.ModuleType('aqt.qt')
for name in ('QObject', 'QTimer', 'Qt', 'pyqtSignal', 'QEasingCurve', 'QEvent', 'QRectF',
             'QVariantAnimation', 'QUrl', 'QColor', 'QPainter', 'QDesktopServices', 'QMenu',
             'QMessageBox', 'QCursor', 'QFontMetrics', 'QApplication', 'QComboBox', 'QDialog',
             'QHBoxLayout', 'QLabel', 'QLineEdit', 'QPushButton', 'QScrollArea', 'QStyle',
             'QVBoxLayout', 'QWidget'):
    setattr(qt, name, globals()[name])
sys.modules['aqt'] = aqt
sys.modules['aqt.qt'] = qt
package = types.ModuleType('zotero_global_capture')
package.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                                 'anki-global-addon', 'zotero_global_capture'))]
sys.modules['zotero_global_capture'] = package

from zotero_global_capture.review_popup import ReviewDialog, popup_style   # noqa: E402
from zotero_global_capture import motion_view                              # noqa: E402

app = QApplication([])
for font_file in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(font_file)
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'
aqt.mw.isActiveWindow = lambda: False
aqt.mw.isMinimized = lambda: False

OUT = os.path.join(os.environ['TEMP'], 'zvr-motion-frames')
os.makedirs(OUT, exist_ok=True)

CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_hint_audio': False,
       'review_theme': 'dark', 'review_position': 'center', 'review_plan_mode': 'fixed',
       'review_batch_size': 10, 'review_motion': 'full',
       'model': '四六级单词模板', 'deck': 'Literature'}
QUESTION = {'kind': 'due', 'card_id': 7, 'mode': 'typing', 'word': 'characteristic',
            'meaning': 'adj. 典型的，特有的；n. 特征', 'example': 'It was a characteristic smile.',
            'literature': '', 'options': [], '音标': "kærəktə'rɪstɪk"}


def card():
    dialog = ReviewDialog(dict(QUESTION), 'center', lambda *_a: None, CFG)
    dialog.resize(510, 630)   # match the real card height, not a guess
    dialog.show()
    app.processEvents()
    return dialog


def answered_card():
    """The state the celebration actually fires in: a flawless spelling, answer face up.

    Rendering the question face instead would show the badge over the letter boxes, which is
    not what the learner sees, and would have made the first review of these frames useless.
    """
    dialog = card()
    for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText(expected)
    dialog.check_input()
    app.processEvents()
    return dialog


def frame(dialog, tier, progress, path):
    """Paint the overlay at a fixed point in the timeline and grab the whole card."""
    overlay = motion_view.Celebration(dialog, 'dark')
    overlay.setGeometry(dialog.rect())
    overlay.animation.stop()
    overlay.tier = tier
    overlay.duration = 980
    overlay.with_sparks = tier in (1, 2)
    overlay.with_confetti = tier == 1
    overlay.progress = progress
    overlay.raise_()
    overlay.show()
    app.processEvents()
    dialog.grab().save(path, 'PNG')
    return overlay


# 1. One frame per tier at the moment the badge is fully in.
paths = {}
for tier in (1, 2, 3, 4):
    dialog = answered_card()
    path = os.path.join(OUT, 'tier%d.png' % tier)
    frame(dialog, tier, 0.45, path)
    paths[tier] = path
    print('rendered', path)

# 2. The same tier at three points in time, to show the entrance and the exit.
dialog = answered_card()
for label, progress in (('in', 0.12), ('hold', 0.45), ('out', 0.93)):
    path = os.path.join(OUT, 'tier1-%s.png' % label)
    frame(dialog, 1, progress, path)
    print('rendered', path)

# 3. The transparency question: pixels far from the badge must be identical with and
#    without the overlay.
plain = answered_card()
bare_path = os.path.join(OUT, 'no-overlay.png')
plain.grab().save(bare_path, 'PNG')
covered = frame(plain, 1, 0.45, os.path.join(OUT, 'with-overlay.png'))

before = QImage(bare_path)
after = QImage(os.path.join(OUT, 'with-overlay.png'))
# Sample points must avoid the badge itself. The point that matters is the word band: with
# the badge moved to the lower third, the word and its 音标 must be pixel-identical.
w, h = plain.width(), plain.height()
corner_samples = [(10, 10), (w - 10, 10), (10, h - 10), (w - 10, h - 10),
                  (w // 2, int(h * 0.22)), (20, int(h * 0.5))]
diffs = []
for x, y in corner_samples:
    if x < before.width() and y < before.height():
        a = before.pixelColor(x, y)
        b = after.pixelColor(x, y)
        diffs.append(((x, y), a.name(), b.name(), a == b))
print('sampled pixels far from the badge:')
for row in diffs:
    print('  ', row)
print('ALL EQUAL (see-through, and the word band untouched):',
      all(row[3] for row in diffs))
print('images in', OUT)
