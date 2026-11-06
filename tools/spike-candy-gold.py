"""Render the shipped `candy_badge` + `badge_pose` on the real answer face, and prove the
transparent parts are actually transparent.

Nothing here reimplements the add-on: it imports `candy_badge.draw` and
`card_motion.badge_pose` from the source tree, so what the sheet shows is what Anki will
paint. Two checks run on the saved pixels:

* the four tiers at their hold frame, plus the entrance/exit frames the pose function
  actually returns;
* a byte-for-byte comparison of the card far away from the badge, plain versus celebrated —
  any difference means something is filling a rectangle instead of fading to alpha 0.
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
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'anki-global-addon',
                                    'zotero_global_capture'))
package.__path__ = [ROOT]
sys.modules['zotero_global_capture'] = package

from zotero_global_capture.review_popup import ReviewDialog
from zotero_global_capture import candy_badge, card_motion

OUT = os.path.join(os.environ['TEMP'], 'zvr-candy-gold')
os.makedirs(OUT, exist_ok=True)
app = QApplication([])
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'

CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_hint_audio': False,
       'review_theme': 'dark', 'review_position': 'center', 'review_plan_mode': 'fixed',
       'review_batch_size': 10, 'model': '四六级单词模板', 'deck': 'Literature'}
CARDS = []


def answer_card():
    dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': 'typing',
                           'word': 'characteristic', 'meaning': 'adj. 典型的，特有的；n. 特征',
                           'example': 'It was a characteristic smile.', 'literature': '',
                           'options': [], '音标': "kærəktə'rɪstɪk"},
                          'center', lambda *_a: None, CFG)
    dialog.resize(510, 630)
    dialog.show()
    for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText(expected)
    dialog.check_input()
    app.processEvents()
    CARDS.append(dialog)
    return dialog


def render(name, tier, progress):
    card = answer_card()
    base = card.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    plain = card.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    pose = card_motion.badge_pose(progress, tier)
    centre = QPoint(card.width() // 2, int(card.height() * 0.60))
    painter = QPainter(base)
    word = card_motion.tier_caption(tier)
    max_width = card.width() * 0.78
    pixel = fit_pixel(word, max_width, candy_badge.WORD_PIXEL)
    candy_badge.draw(painter, centre, word, tier, pose, max_width=max_width)
    painter.end()
    path = os.path.join(OUT, '%s.png' % name)
    base.save(path, 'PNG')
    untouched = check_untouched(plain, base, card)
    print('rendered %-18s scale %.2f angle %+5.1f opacity %.2f glow %.2f ribbon %.2f '
          'edge-clean=%s' % (name, pose['scale'], pose['angle'], pose['opacity'], pose['glow'],
                             pose['ribbon'], untouched))
    return path


def fit_pixel(word, max_width, cap):
    """Shrink the face until the whole word fits inside the card — UNBELIEVABLE is 12 letters."""
    pixel = cap
    while pixel > 18:
        metrics = QFontMetrics(candy_badge.display_font(pixel))
        if metrics.horizontalAdvance(word) <= max_width:
            return pixel
        pixel -= 1
    return pixel


def check_untouched(plain, painted, card):
    """Every pixel in the top 22% and bottom 8% must be byte-identical to the plain card."""
    for y in list(range(0, int(card.height() * 0.22))) + \
            list(range(int(card.height() * 0.92), card.height() - 1)):
        for x in range(0, card.width() - 1, 7):
            if plain.pixelColor(x, y) != painted.pixelColor(x, y):
                return 'DIFFERS at %d,%d' % (x, y)
    return True


for tier in (4, 3, 2, 1):
    render('t%d-hold' % tier, tier, 0.55)
for progress, suffix in ((0.06, 'a'), (0.16, 'b'), (0.30, 'c'), (0.94, 'd')):
    render('t1-%s' % suffix, 1, progress)
