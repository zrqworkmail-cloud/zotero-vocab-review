"""Render a real frame series of the celebration, straight from the shipped code.

`candy_badge.draw` and `card_motion.badge_pose` are imported from the add-on, so these are
the exact pixels Anki will paint — the HTML the learner sees loops this sequence at the real
980ms. A light-theme frame is included because the cream outline has to survive a white card.
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
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))
os.environ['QT_PLUGIN_PATH'] = os.path.join(BASE, 'PyQt6', 'Qt6', 'plugins')

from PyQt6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QVariantAnimation, \
    QUrl, pyqtSignal, QEvent
from PyQt6.QtGui import (QColor, QCursor, QDesktopServices, QFont, QFontDatabase, QFontInfo,
                         QFontMetrics, QFontMetricsF, QImage, QLinearGradient, QPainter,
                         QPainterPath, QPen, QRadialGradient, QPixmap)
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
from zotero_global_capture import candy_badge, card_motion, motion_view

OUT = os.path.join(os.environ['TEMP'], 'zvr-candy-frames')
os.makedirs(OUT, exist_ok=True)
app = QApplication([])
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'

FRAMES = 16          # 16 frames across 980ms is the real 60fps sequence decimated to 61ms
CARDS = []


def answer_card(theme='dark', word='characteristic'):
    cfg = {'review_auto_word': False, 'review_auto_example_mode': 'off',
           'review_hint_audio': False, 'review_theme': theme, 'review_position': 'center',
           'review_plan_mode': 'fixed', 'review_batch_size': 10, 'model': '四六级单词模板',
           'deck': 'Literature'}
    dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': 'typing', 'word': word,
                           'meaning': 'adj. 典型的，特有的；n. 特征',
                           'example': 'It was a characteristic smile.', 'literature': '',
                           'options': [], '音标': "kærəktə'rɪstɪk"},
                          'center', lambda *_a: None, cfg)
    dialog.resize(510, 630)
    dialog.show()
    for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText(expected)
    dialog.check_input()
    app.processEvents()
    CARDS.append(dialog)
    return dialog


def shoot(name, card, tier, progress):
    base = card.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    pose = card_motion.badge_pose(progress, tier, card_motion.TIMING['badge']['duration'])
    painter = QPainter(base)
    # The anchor comes from the shipped placement rule, never a number copied into this tool:
    # a spike that hardcodes its own placement is how a wrong anchor can look fine for a day.
    # Asking the card for its protected rows makes the mockup move the way the real card does.
    rows = card.celebration_rows()[1] if hasattr(card, 'celebration_rows') else ()
    y, _fit = motion_view.badge_centre(card.height(), tier, card.width() * 0.78, rows)
    candy_badge.draw(painter, QPoint(card.width() // 2, y),
                     card_motion.tier_caption(tier), tier, pose,
                     max_width=card.width() * 0.78)
    painter.end()
    base.save(os.path.join(OUT, '%s.png' % name), 'PNG')


dark = answer_card('dark')
for index in range(FRAMES):
    shoot('t1-%02d' % index, dark, 1, index / float(FRAMES - 1))
for tier in (2, 3, 4):
    shoot('hold-t%d' % tier, dark, tier, 0.55)
light = answer_card('light')
shoot('light-t1', light, 1, 0.55)
shoot('light-t4', light, 4, 0.55)
long_word = answer_card('dark', word='unbelievable')
shoot('t1-longword', long_word, 1, 0.55)
print('frames ->', OUT)
print('pose at 0.00', {k: round(v, 3) for k, v in
                      card_motion.badge_pose(0.0, 1, 980).items() if isinstance(v, float)})
print('pose at 0.55', {k: round(v, 3) for k, v in
                       card_motion.badge_pose(0.55, 1, 980).items() if isinstance(v, float)})
print('pose at 1.00', {k: round(v, 3) for k, v in
                       card_motion.badge_pose(1.0, 1, 980).items() if isinstance(v, float)})
