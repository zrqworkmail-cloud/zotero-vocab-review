"""Design spike v2 for the celebration badge: a 钤印 (sealed stamp), not clipart.

Reference work behind it:
- 篆刻的两种正负关系：朱文（阳文，字是红的、底留白）与白文（阴文，字是白的、底是红的）。
  白文"线条粗壮、具有强烈的视觉冲击力、古朴"，正是庆祝瞬间要的张力，而它来自正负空间，
  不来自渐变。
- 钤印常识：真印盖出来不会绝对水平、墨色不匀、边角有细微缺口。质感来自"不完全干净"。
- Duolingo 的庆祝动画经验：把力气花在一个焦点动作上，并且不能挡住用户继续。

So: one gesture (the stamp presses down, ink soaks, it lifts), 印泥朱砂 on the card's own
dark ground, 华文琥珀 for the square-ish heavy strokes, and one line of 批注 that carries
real information (what the learner actually did) instead of a shouted label.

Rendered onto the real card pixels, on the real font database, no window shown.
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

from PyQt6.QtCore import (QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QVariantAnimation,
                          QUrl, pyqtSignal, QEvent)
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

OUT = os.path.join(os.environ['TEMP'], 'zvr-badge-v2')
os.makedirs(OUT, exist_ok=True)
app = QApplication([])
for font_file in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(font_file)
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'

# --- palette: 印泥朱砂 on the card's own dark ground -------------------------------
CINNABAR = QColor('#C03028')
CINNABAR_DEEP = QColor('#8F1F19')
PAPER = QColor('#F7F2E8')
NOTE = QColor('#E7C9A8')

SEAL_FONT = next((f for f in ('STHupo', '华文琥珀', 'SimHei')
                  if QFontInfo(QFont(f, 40)).family().lower() == f.lower()), 'SimHei')
NOTE_FONT = 'Microsoft YaHei'
print('seal font ->', SEAL_FONT, '| note font ->', NOTE_FONT)

CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_hint_audio': False,
       'review_theme': 'dark', 'review_position': 'center', 'review_plan_mode': 'fixed',
       'review_batch_size': 10, 'model': '四六级单词模板', 'deck': 'Literature'}


def real_card():
    dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': 'typing', 'word': 'characteristic',
                           'meaning': 'adj. 典型的，特有的；n. 特征',
                           'example': 'It was a characteristic smile.', 'literature': '',
                           'options': [], '音标': "kærəktə'rɪstɪk"},
                          'center', lambda *_a: None, CFG)
    dialog.resize(510, 630)
    dialog.show()
    for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText(expected)
    dialog.check_input()
    app.processEvents()
    return dialog


def seal_path(size, radius, chips):
    """A rounded square with a few bites taken out of the edge: a real impression."""
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    for x, y, r in chips:
        bite = QPainterPath()
        bite.addEllipse(QPointF(x, y), r, r)
        path = path.subtracted(bite)
    return path


def draw_seal(painter, rect, label, note, variant, press=1.0):
    """One stamp, pressed at `press` (0 = still falling, 1 = landed)."""
    size = rect.width()
    cx, cy = rect.center().x(), rect.center().y()
    painter.save()
    painter.translate(cx, cy)
    painter.rotate(-6.0 + 3.0 * (1.0 - press))
    scale = 1.0 + 0.42 * (1.0 - press)
    painter.scale(scale, scale)
    painter.translate(-size / 2, -size / 2)

    chips = [(0.0, size * 0.34, 4.2), (size, size * 0.62, 3.6), (size * 0.22, 0.0, 3.2),
             (size * 0.78, size, 4.0), (size, size * 0.12, 2.6)]
    body = seal_path(size, 10, chips)
    ink = QColor(CINNABAR)
    ink.setAlphaF(0.80 + 0.20 * press)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    painter.drawPath(body)
    # Uneven pressure: the top-left corner of a hand-pressed stamp takes less ink.
    soak = QRadialGradient(QPointF(size * 0.3, size * 0.25), size * 0.95)
    soak.setColorAt(0.0, QColor(255, 255, 255, 46))
    soak.setColorAt(1.0, QColor(0, 0, 0, 26))
    painter.setBrush(soak)
    painter.drawPath(body)

    margin = size * 0.10
    inner = QPainterPath()
    inner.addRoundedRect(QRectF(margin, margin, size - 2 * margin, size - 2 * margin), 4, 4)
    border = QPen(PAPER if variant == 'baiwen' else CINNABAR)
    border.setWidthF(size * 0.022)
    painter.setPen(border)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(inner)

    font = QFont(SEAL_FONT)
    font.setPixelSize(int(size * 0.30))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(PAPER if variant == 'baiwen' else CINNABAR)
    painter.drawText(QRectF(0, size * 0.10, size, size * 0.52),
                     int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), label)
    small = QFont(NOTE_FONT)
    small.setPixelSize(int(size * 0.085))
    small.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
    painter.setFont(small)
    painter.setPen(QColor(PAPER.red(), PAPER.green(), PAPER.blue(), 215) if variant == 'baiwen'
                   else QColor(CINNABAR_DEEP.red(), CINNABAR_DEEP.green(), CINNABAR_DEEP.blue(), 230))
    painter.drawText(QRectF(0, size * 0.62, size, size * 0.22),
                     int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), note)
    painter.restore()


def draw_hanamaru(painter, rect, label, note, press=1.0):
    """花丸：one red pen circle with the mark inside, no seal block at all."""
    size = rect.width()
    painter.save()
    painter.translate(rect.center().x() - size / 2, rect.center().y() - size / 2)
    scale = 1.0 + 0.25 * (1.0 - press)
    painter.translate(size / 2, size / 2)
    painter.scale(scale, scale)
    painter.translate(-size / 2, -size / 2)
    pen = QPen(CINNABAR)
    pen.setWidthF(size * 0.055)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    ring = QPainterPath()
    ring.addEllipse(QRectF(size * 0.06, size * 0.08, size * 0.88, size * 0.84))
    painter.drawPath(ring)
    # The pen crosses itself where a hand closes a circle.
    tail = QPainterPath()
    tail.moveTo(size * 0.80, size * 0.06)
    tail.cubicTo(size * 0.95, size * 0.18, size * 0.92, size * 0.34, size * 0.74, size * 0.30)
    painter.drawPath(tail)
    font = QFont(SEAL_FONT)
    font.setPixelSize(int(size * 0.30))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(CINNABAR)
    painter.drawText(QRectF(0, size * 0.16, size, size * 0.5),
                     int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), label)
    small = QFont(NOTE_FONT)
    small.setPixelSize(int(size * 0.085))
    painter.setFont(small)
    painter.setPen(QColor(NOTE))
    painter.drawText(QRectF(-size * 0.2, size * 0.72, size * 1.4, size * 0.2),
                     int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), note)
    painter.restore()


def composite(card, drawer, rect, label, note, variant, press, path):
    base = card.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(base)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    drawer(painter, QRect(rect), label, note, variant, press)
    painter.end()
    base.save(path, 'PNG')
    return path


card = real_card()
area = QRect(135, 300, 240, 240)
LABEL, NOTE_TEXT = '不可思议', '零提示 · 一次写对'
made = []
for variant, drawer, title in (('baiwen', draw_seal, 'A 白文方印'),
                               ('zhuwen', draw_seal, 'B 朱文方印'),
                               ('hanamaru', draw_hanamaru, 'C 花丸')):
    for press, suffix in ((0.55, 'press'), (1.0, 'land')):
        path = os.path.join(OUT, '%s-%s.png' % (variant, suffix))
        made.append(composite(card, drawer, area, LABEL, NOTE_TEXT, variant, press, path))
        print('rendered', title, suffix, '->', path)
