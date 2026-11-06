"""Design spike v4 — the stamp as an annotation, placed where the card is actually free.

Measured (tools/probe-card-geometry.py, real card 510x541): the only full-width dead bands
are y 240-268 and y 320-368, i.e. between the blocks; every row is otherwise occupied by the
解释 box, the 例句 box, the verdict line, the summary line, the grade buttons and the pills.
So the stamp cannot be a big centred object. It goes where a real 批注 goes: at the end of
the line it comments on — the right-hand end of 「回答正确」, x 361-439, y 331-409, which no
glyph occupies.

Two more consequences of looking at the pixels:
- The card already prints the facts ("无提示，错误字母 0 次…建议"Mastered""), so the stamp
  needs no 落款 line of its own. Removing it is the one accessory Chanel asked for.
- The verdict line is #71e0b5 green. 朱砂 red next to saturated green on navy reads as a
  Christmas card, so when a stamp lands the verdict goes 纸色 and the stamp carries the
  emphasis alone.

Variants at true size: A 白文方印, B 朱文方印, C 花丸.
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

OUT = os.path.join(os.environ['TEMP'], 'zvr-badge-v4')
os.makedirs(OUT, exist_ok=True)
app = QApplication([])
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'

CINNABAR = QColor('#C03028')
CINNABAR_DEEP = QColor('#8F1F19')
PAPER = QColor('#F7F2E8')
SEAL_FONT = 'STHupo'
print('seal font resolves ->', QFontInfo(QFont(SEAL_FONT, 40)).family())

CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_hint_audio': False,
       'review_theme': 'dark', 'review_position': 'center', 'review_plan_mode': 'fixed',
       'review_batch_size': 10, 'model': '四六级单词模板', 'deck': 'Literature'}


def card_for(label, recolour):
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
    if recolour:
        dialog.result_label.setStyleSheet('color: #F7F2E8;')
    app.processEvents()
    return dialog


def seal_path(size, radius, chips):
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    for fx, fy, fr in chips:
        bite = QPainterPath()
        bite.addEllipse(QPointF(fx * size, fy * size), fr * size, fr * size)
        path = path.subtracted(bite)
    return path


CHIPS = ((0.00, 0.34, 0.040), (1.00, 0.62, 0.034), (0.22, 0.00, 0.030),
         (0.78, 1.00, 0.036), (1.00, 0.12, 0.024))


def ink_columns(label):
    """印文右列起读、每列自上而下；返回左→右的列。"""
    text = ''.join(ch for ch in label if '\u4e00' <= ch <= '\u9fff')
    if len(text) <= 1:
        return [[text or '印']]
    if len(text) == 2:
        return [[text[1]], [text[0]]]
    split = len(text) // 2
    return [list(text[split:]), list(text[:split])]


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


def flecks(painter, centre, size, press, variant):
    """落印一瞬甩出的朱砂点——星芒的位置换成墨点。"""
    if press < 0.45:
        return
    reach = size * (0.62 + 0.55 * press)
    ink = QColor(CINNABAR)
    ink.setAlphaF(max(0.0, 0.85 - 0.75 * press))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    for index in range(9):
        angle = -1.62 + index * 0.42
        x = centre.x() + reach * 1.05 * math.cos(angle)
        y = centre.y() + reach * 0.72 * math.sin(angle)
        radius = size * (0.030 + 0.022 * (index % 3))
        painter.drawEllipse(QPointF(x, y), radius, radius)


def draw_seal(painter, centre, size, label, variant, press=1.0):
    lift = 1.0 + 0.45 * (1.0 - press)
    flecks(painter, centre, size, press, variant)
    painter.save()
    painter.translate(centre.x(), centre.y())
    painter.rotate(-7.0 + 5.0 * (1.0 - press))
    painter.scale(lift, lift)
    painter.translate(-size / 2, -size / 2)
    body = seal_path(size, size * 0.05, CHIPS)
    if variant == 'baiwen':
        ink = QColor(CINNABAR)
        ink.setAlphaF(0.86 + 0.14 * press)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawPath(body)
        soak = QRadialGradient(QPointF(size * 0.30, size * 0.24), size * 1.05)
        soak.setColorAt(0.0, QColor(255, 255, 255, 34))
        soak.setColorAt(1.0, QColor(0, 0, 0, 34))
        painter.setBrush(soak)
        painter.drawPath(body)
        glyph = PAPER
    else:
        frame = QPen(CINNABAR)
        frame.setWidthF(max(2.0, size * 0.062))
        frame.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(frame)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(body)
        glyph = CINNABAR
    columns = ink_columns(label)
    gutter = size * 0.10
    col_width = (size - 2 * gutter) / len(columns)
    for index, column in enumerate(columns):
        rows = len(column)
        cell_height = (size - 2 * gutter) / rows
        for row, char in enumerate(column):
            box = QRectF(gutter + index * col_width, gutter + row * cell_height,
                         col_width, cell_height)
            font = fit_font(SEAL_FONT, size * (0.30 if rows == 2 else 0.44), char,
                            box.width() * 0.98, box.height() * 0.94)
            painter.setFont(font)
            painter.setPen(glyph)
            painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), char)
    painter.restore()


def draw_hanamaru(painter, centre, size, label, variant, press=1.0):
    lift = 1.0 + 0.25 * (1.0 - press)
    flecks(painter, centre, size, press, variant)
    painter.save()
    painter.translate(centre.x(), centre.y())
    painter.rotate(-4.0)
    painter.scale(lift, lift)
    pen = QPen(CINNABAR)
    pen.setWidthF(max(2.5, size * 0.070))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    ring = QPainterPath()
    ring.addEllipse(QRectF(-size * 0.42, -size * 0.40, size * 0.84, size * 0.80))
    painter.drawPath(ring)
    tail = QPainterPath()
    tail.moveTo(size * 0.26, -size * 0.44)
    tail.cubicTo(size * 0.44, -size * 0.30, size * 0.40, -size * 0.10, size * 0.20, -size * 0.20)
    painter.drawPath(tail)
    mark = ink_columns(label)[-1][0]
    font = fit_font(SEAL_FONT, size * 0.46, mark, size * 0.58, size * 0.54)
    painter.setFont(font)
    painter.setPen(CINNABAR)
    painter.drawText(QRectF(-size * 0.29, -size * 0.27, size * 0.58, size * 0.54),
                     int(Qt.AlignmentFlag.AlignCenter), mark)
    painter.restore()


DRAWERS = {'baiwen': draw_seal, 'zhuwen': draw_seal, 'hanamaru': draw_hanamaru}


CARDS = []  # keep every card alive: deleteLater() mid-loop segfaults the grab of the next


def shoot(centre, size, label, variant, press, recolour, path):
    card = card_for(label, recolour)
    CARDS.append(card)
    base = card.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(base)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    DRAWERS[variant](painter, QPoint(centre[0], centre[1]), size, label, variant, press)
    painter.end()
    base.save(path, 'PNG')
    print('rendered', os.path.basename(path))


for label in ('不可思议', '完美'):
    for variant in ('baiwen', 'zhuwen', 'hanamaru'):
        shoot((398, 372), 88, label, variant, 1.0, True,
              os.path.join(OUT, '%s-%s-land.png' % (variant, label)))
        shoot((398, 372), 88, label, variant, 0.55, True,
              os.path.join(OUT, '%s-%s-press.png' % (variant, label)))
shoot((398, 372), 88, '不可思议', 'baiwen', 1.0, False,
      os.path.join(OUT, 'baiwen-不可思议-land-greenverdict.png'))
