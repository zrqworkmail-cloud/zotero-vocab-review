"""Design spike v6 — final geometry check, per-tier marks, and the ink squeeze at contact.

Geometry from the measurement: the 例句 box ends at y 348 and the summary line starts at
y 414, so the only row the stamp can own without covering anything it should not is a 66px
band centred on y 381 — which is also the optical centre of 「回答正确」. Size 66, one
character at ~40px.

Tier is carried by the mark itself, not by decoration: 良 / 优 / 妙 / 神.
T1 and T2 additionally get the ink that is squeezed out at the moment of contact — five
small 朱砂 dots tight to the edges, gone within the press, so they read as force, not
confetti.
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

OUT = os.path.join(os.environ['TEMP'], 'zvr-badge-v6')
os.makedirs(OUT, exist_ok=True)
app = QApplication([])
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'

CINNABAR = QColor('#C03028')
PAPER = QColor('#F7F2E8')
SEAL_FONT = 'STHupo'
CENTRE = (398, 381)
SIZE = 66

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
    dialog.result_label.setStyleSheet('color: #F7F2E8;')
    app.processEvents()
    CARDS.append(dialog)
    return dialog


def seal_path(size, nicks):
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.045, size * 0.045)
    for fx, fy, fr in nicks:
        bite = QPainterPath()
        bite.addEllipse(QPointF(fx * size, fy * size), fr * size, fr * size * 0.6)
        path = path.subtracted(bite)
    return path


NICKS = ((0.00, 0.42, 0.020), (1.00, 0.30, 0.017), (0.38, 1.00, 0.015), (0.72, 0.00, 0.014))


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


def squeeze(painter, centre, size, contact):
    """落印一瞬被挤出的墨：贴着边、五颗、只在触底前后出现。"""
    if contact <= 0.0 or contact >= 1.0:
        return
    alpha = 0.9 * math.sin(math.pi * contact)
    reach = size * (0.58 + 0.30 * contact)
    painter.setPen(Qt.PenStyle.NoPen)
    for index, (angle, scale) in enumerate(((-0.55, 1.0), (-1.55, 0.7), (2.30, 0.85),
                                            (1.20, 0.6), (-2.35, 0.75))):
        ink = QColor(CINNABAR)
        ink.setAlphaF(alpha * (0.55 + 0.15 * (index % 3)))
        painter.setBrush(ink)
        x = centre.x() + reach * 1.12 * math.cos(angle)
        y = centre.y() + reach * 0.80 * math.sin(angle)
        radius = size * 0.030 * scale
        painter.drawEllipse(QPointF(x, y), radius, radius)


def draw_stamp(painter, centre, size, mark, press=1.0, spray=False, font_family=SEAL_FONT):
    """press: 0 = 还在落下，1 = 触底，>1 = 抬起（淡出）。"""
    if press <= 1.0:
        lift = 1.0 + 0.26 * (1.0 - press)
        drop = -10.0 * (1.0 - press)
        tilt = -2.5 + -4.0 * (1.0 - press)
        alpha = 1.0
    else:
        out = min(1.0, press - 1.0)
        lift = 1.0 + 0.10 * out
        drop = -14.0 * out
        tilt = -6.5
        alpha = 1.0 - out
    if spray:
        squeeze(painter, QPoint(*centre), size, max(0.0, min(1.0, (press - 0.72) / 0.28)))
    painter.save()
    painter.setOpacity(alpha)
    painter.translate(centre[0], centre[1] + drop)
    painter.rotate(tilt)
    painter.scale(lift, lift)
    painter.translate(-size / 2, -size / 2)
    body = seal_path(size, NICKS)
    ink = QColor(CINNABAR)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    painter.drawPath(body)
    soak = QRadialGradient(QPointF(size * 0.34, size * 0.28), size * 1.15)
    soak.setColorAt(0.0, QColor(255, 255, 255, 34))
    soak.setColorAt(0.55, QColor(0, 0, 0, 0))
    soak.setColorAt(1.0, QColor(0, 0, 0, 44))
    painter.setBrush(soak)
    painter.drawPath(body)
    font = fit_font(font_family, size * 0.66, mark, size * 0.76, size * 0.76)
    painter.setFont(font)
    painter.setPen(PAPER)
    painter.drawText(QRectF(0, 0, size, size), int(Qt.AlignmentFlag.AlignCenter), mark)
    painter.restore()


def shoot(mark, name, press=1.0, spray=False, size=SIZE, centre=CENTRE, font=SEAL_FONT):
    card = answer_card()
    base = card.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(base)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    draw_stamp(painter, centre, size, mark, press, spray, font)
    painter.end()
    path = os.path.join(OUT, '%s.png' % name)
    base.save(path, 'PNG')
    print('rendered', name)


TIERS = (('良', 't4-liang'), ('优', 't3-you'), ('妙', 't2-miao'), ('神', 't1-shen'))
for mark, name in TIERS:
    shoot(mark, '%s-land' % name)
shoot('神', 't1-shen-contact', press=0.90, spray=True)
shoot('神', 't1-shen-fall', press=0.45)
shoot('神', 't1-shen-lift', press=1.45, spray=True)
shoot('神', 't1-shen-simhei', font='SimHei')
shoot('神', 't1-shen-stormy', font='STXingkai')
shoot('神', 't1-shen-size80', size=80)
print('families checked')
