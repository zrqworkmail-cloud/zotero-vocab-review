"""Design spike v5 — one 朱批 character, not four.

What v4 taught (looked at the pixels, not the code):
- A 四字印 in a 88px square is 20px per glyph and the traditional right-column-first order
  reads as garbage to a modern eye ("思不可议"). Authenticity bought nothing here.
- The teacher-mark tradition does the same job with one character: 朱批「良」「优」. One big
  glyph in 华文琥珀 is more legible AND more forceful at the same footprint.
- The circular "chips" at 3-4% of the side looked like a bitten sticker, and the ink flecks
  looked like dirt. Both removed: an impression is uneven in colour, not shredded.

So: 白文 / 朱文 / 花丸, one character, sitting at the right-hand end of 「回答正确」 where the
card is measurably empty (tools/probe-card-geometry.py), verdict recoloured to 纸色 so 朱砂
never fights the green.
"""
import math
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

OUT = os.path.join(os.environ['TEMP'], 'zvr-badge-v5')
os.makedirs(OUT, exist_ok=True)
app = QApplication([])
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'

CINNABAR = QColor('#C03028')
CINNABAR_DEEP = QColor('#96231D')
PAPER = QColor('#F7F2E8')
SEAL_FONT = 'STHupo'
print('seal font resolves ->', QFontInfo(QFont(SEAL_FONT, 40)).family())

CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_hint_audio': False,
       'review_theme': 'dark', 'review_position': 'center', 'review_plan_mode': 'fixed',
       'review_batch_size': 10, 'model': '四六级单词模板', 'deck': 'Literature'}

CARDS = []  # keep every card alive: deleteLater() mid-loop segfaults the next grab


def answer_card(verdict, recolour):
    dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': 'typing',
                           'word': 'characteristic',
                           'meaning': 'adj. 典型的，特有的；n. 特征',
                           'example': 'It was a characteristic smile.', 'literature': '',
                           'options': [], '音标': "kærəktə'rɪstɪk"},
                          'center', lambda *_a: None, CFG)
    dialog.resize(510, 630)
    dialog.show()
    for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText(expected)
    dialog.check_input()
    dialog.result_label.setText(verdict)
    if recolour:
        dialog.result_label.setStyleSheet('color: #F7F2E8;')
    app.processEvents()
    CARDS.append(dialog)
    return dialog


def seal_path(size, radius, nicks):
    """方印，边上有几处极浅的崩口——钤印不干净，但没有被咬过的洞。"""
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    for fx, fy, fr in nicks:
        bite = QPainterPath()
        bite.addEllipse(QPointF(fx * size, fy * size), fr * size, fr * size * 0.62)
        path = path.subtracted(bite)
    return path


NICKS = ((0.00, 0.42, 0.016), (1.00, 0.30, 0.014), (0.38, 1.00, 0.013), (0.72, 0.00, 0.012))


def fit_font(family, pixel_size, text, box_width, box_height):
    font = QFont(family)
    font.setBold(True)
    size = int(pixel_size)
    while size > 6:
        font.setPixelSize(size)
        metrics = QFontMetrics(font)
        if metrics.horizontalAdvance(text) <= box_width and metrics.height() <= box_height:
            return font
        size -= 1
    font.setPixelSize(6)
    return font


def ink_wash(painter, size):
    """受力不匀：手压下去，靠里的一角墨淡，外侧沉。"""
    soak = QRadialGradient(QPointF(size * 0.34, size * 0.28), size * 1.15)
    soak.setColorAt(0.0, QColor(255, 255, 255, 30))
    soak.setColorAt(0.55, QColor(0, 0, 0, 0))
    soak.setColorAt(1.0, QColor(0, 0, 0, 40))
    painter.setBrush(soak)


def draw_baiwen(painter, centre, size, mark, press=1.0):
    lift = 1.0 + 0.42 * (1.0 - press)
    painter.save()
    painter.translate(centre.x(), centre.y())
    painter.rotate(-6.5 + 4.5 * (1.0 - press))
    painter.scale(lift, lift)
    painter.translate(-size / 2, -size / 2)
    body = seal_path(size, size * 0.045, NICKS)
    ink = QColor(CINNABAR)
    ink.setAlphaF(0.88 + 0.12 * press)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    painter.drawPath(body)
    ink_wash(painter, size)
    painter.drawPath(body)
    font = fit_font(SEAL_FONT, size * 0.62, mark, size * 0.74, size * 0.74)
    painter.setFont(font)
    painter.setPen(PAPER)
    painter.drawText(QRectF(0, 0, size, size), int(Qt.AlignmentFlag.AlignCenter), mark)
    painter.restore()


def draw_zhuwen(painter, centre, size, mark, press=1.0):
    """朱文：框是红的，字也是红的，底留空——在深色卡面上比白文轻一档。"""
    lift = 1.0 + 0.42 * (1.0 - press)
    painter.save()
    painter.translate(centre.x(), centre.y())
    painter.rotate(-6.5 + 4.5 * (1.0 - press))
    painter.scale(lift, lift)
    painter.translate(-size / 2, -size / 2)
    frame = QPen(CINNABAR)
    frame.setWidthF(max(2.5, size * 0.075))
    frame.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(frame)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(seal_path(size, size * 0.045, NICKS))
    font = fit_font(SEAL_FONT, size * 0.52, mark, size * 0.62, size * 0.62)
    painter.setFont(font)
    painter.setPen(CINNABAR)
    painter.drawText(QRectF(0, 0, size, size), int(Qt.AlignmentFlag.AlignCenter), mark)
    painter.restore()


def draw_hanamaru(painter, centre, size, mark, press=1.0):
    """花丸加朱批：一支笔的圈，笔锋压过起点。"""
    lift = 1.0 + 0.24 * (1.0 - press)
    painter.save()
    painter.translate(centre.x(), centre.y())
    painter.rotate(-4.0)
    painter.scale(lift, lift)
    pen = QPen(CINNABAR)
    pen.setWidthF(max(2.5, size * 0.062))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    ring = QPainterPath()
    ring.addEllipse(QRectF(-size * 0.44, -size * 0.42, size * 0.88, size * 0.84))
    painter.drawPath(ring)
    tail = QPainterPath()
    tail.moveTo(size * 0.28, -size * 0.46)
    tail.cubicTo(size * 0.46, -size * 0.30, size * 0.42, -size * 0.10, size * 0.22, -size * 0.20)
    painter.drawPath(tail)
    font = fit_font(SEAL_FONT, size * 0.50, mark, size * 0.60, size * 0.58)
    painter.setFont(font)
    painter.setPen(CINNABAR)
    painter.drawText(QRectF(-size * 0.30, -size * 0.29, size * 0.60, size * 0.58),
                     int(Qt.AlignmentFlag.AlignCenter), mark)
    painter.restore()


DRAWERS = {'baiwen': draw_baiwen, 'zhuwen': draw_zhuwen, 'hanamaru': draw_hanamaru}


def shoot(verdict, mark, variant, size, centre, press, recolour, name):
    card = answer_card(verdict, recolour)
    base = card.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(base)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    DRAWERS[variant](painter, QPoint(centre[0], centre[1]), size, mark, press)
    painter.end()
    base.save(os.path.join(OUT, '%s.png' % name), 'PNG')
    print('rendered', name)


for variant in ('baiwen', 'zhuwen', 'hanamaru'):
    shoot('回答正确', '神', variant, 84, (398, 372), 1.0, True, '%s-shen-land' % variant)
    shoot('回答正确', '神', variant, 84, (398, 372), 0.55, True, '%s-shen-press' % variant)
shoot('回答正确', '良', 'baiwen', 84, (398, 372), 1.0, True, 'baiwen-liang-land')
shoot('回答正确', '妙', 'baiwen', 84, (398, 372), 1.0, True, 'baiwen-miao-land')
shoot('回答正确', '神', 'baiwen', 104, (398, 366), 1.0, True, 'baiwen-shen-big')
