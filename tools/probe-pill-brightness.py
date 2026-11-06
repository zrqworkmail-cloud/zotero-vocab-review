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



# Brightness probe: sample the pill's centre pixel through the whole timeline. The live
# capture of `advocate` showed a washed-out pill, and one frame cannot tell "the entrance
# ramp is still running" from "the pill is never opaque" — so measure it.
dialog = answered_card()
overlay = motion_view.Celebration(dialog, 'dark')
overlay.setGeometry(dialog.rect())
overlay.animation.stop()
overlay.tier = 4
overlay.duration = 980
overlay.with_sparks = False
overlay.with_confetti = False
overlay.raise_()
overlay.show()
cx = dialog.width() // 2
cy = motion_view.badge_centre(dialog.height(), overlay.tier, dialog.width() * 0.78)[0]
print('tier 4 pill colour is', overlay.badge_color())
for ms in (0, 60, 120, 180, 260, 400, 600, 780, 900, 970):
    overlay.progress = ms / 980.0
    overlay.update()
    app.processEvents()
    shot = dialog.grab().toImage()
    colour = shot.pixelColor(cx, cy)
    entering = min(1.0, overlay.progress / (260 / 980.0))
    print('  %3dms  centre=%s  entering=%.2f' % (ms, colour.name(), entering))
