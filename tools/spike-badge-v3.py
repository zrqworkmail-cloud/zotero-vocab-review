"""Design spike v3 for the celebration badge: a 钤印 (sealed stamp), not clipart.

Reference work behind it:
- 篆刻的两种正负关系：朱文（阳文，字是红的、底留白）与白文（阴文，字是白的、底是红的）。
  白文"线条粗壮、具有强烈的视觉冲击力、古朴"，正是庆祝瞬间要的张力，而它来自正负空间，
  不来自渐变。
- 印文的排布：四字印是最常见的格式，右列起读、每列自上而下。所以"不可思议"排成两列两行，
  而不是横着一行——这一条决定它像不像一枚印。
- 钤印常识：真印盖出来不会绝对水平、墨色不匀、边角有细微缺口；而且印不大，落在画面边角，
  旁边是题跋。质感来自"不完全干净"，冲击力来自正负形，不来自把色块放大。
- Duolingo 的庆祝动画经验：把力气花在一个焦点动作上，并且不能挡住用户继续。

So: one gesture (the stamp falls, presses, ink soaks, it lifts), a small square of 印泥朱砂
in the lower part of the card, 华文琥珀 for the heavy square-ish strokes, and one line of
批注 beneath it that carries real information (what the learner actually did).

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

OUT = os.path.join(os.environ['TEMP'], 'zvr-badge-v3')
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
    for fx, fy, fr in chips:
        bite = QPainterPath()
        bite.addEllipse(QPointF(fx * size, fy * size), fr * size, fr * size)
        path = path.subtracted(bite)
    return path


CHIPS = ((0.00, 0.34, 0.038), (1.00, 0.62, 0.032), (0.22, 0.00, 0.028),
         (0.78, 1.00, 0.034), (1.00, 0.12, 0.022))


def ink_columns(label):
    """印文按真印排布：右列起读、每列自上而下，返回左→右的列。"""
    text = ''.join(ch for ch in label if ch.isalnum() or '\u4e00' <= ch <= '\u9fff')
    if not text:
        return [['印']]
    if len(text) == 1:
        return [[text]]
    if len(text) == 2:
        return [[text[1]], [text[0]]]
    split = len(text) // 2 if len(text) % 2 == 0 else len(text) // 2 + 1
    right, left = text[:split], text[split:]
    return [list(left), list(right)]


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


def colophon(painter, centre_x, top_y, width, note):
    """落款：一句真话，用小字号，不用大字号喊。"""
    small = QFont(NOTE_FONT)
    small.setPixelSize(13)
    small.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
    painter.setFont(small)
    painter.setPen(QColor(NOTE.red(), NOTE.green(), NOTE.blue(), 235))
    band = QRectF(centre_x - width / 2, top_y, width, 26)
    painter.drawText(band, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), note)


def draw_seal(painter, rect, label, note, variant, press=1.0):
    """One stamp, pressed at `press` (0 = still falling, 1 = landed).

    variant 'baiwen' = 白文（红底白字）, 'zhuwen' = 朱文（红框红字、底留空）。
    """
    size = float(rect.width())
    centre = rect.center()
    lift = 1.0 + 0.40 * (1.0 - press)

    painter.save()
    painter.translate(centre.x(), centre.y())
    painter.rotate(-7.0 + 3.5 * (1.0 - press))
    painter.scale(lift, lift)
    painter.translate(-size / 2, -size / 2)

    body = seal_path(size, size * 0.055, CHIPS)
    if variant == 'baiwen':
        ink = QColor(CINNABAR)
        ink.setAlphaF(0.82 + 0.18 * press)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawPath(body)
        # Uneven pressure: the corner a hand leans on least holds less ink.
        soak = QRadialGradient(QPointF(size * 0.28, size * 0.22), size * 1.05)
        soak.setColorAt(0.0, QColor(255, 255, 255, 40))
        soak.setColorAt(1.0, QColor(0, 0, 0, 30))
        painter.setBrush(soak)
        painter.drawPath(body)
        glyph = PAPER
    else:
        frame = QPen(CINNABAR)
        frame.setWidthF(size * 0.055)
        frame.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(frame)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(body)
        glyph = CINNABAR

    columns = ink_columns(label)
    gutter = size * 0.11
    col_width = (size - 2 * gutter) / len(columns)
    for index, column in enumerate(columns):
        left = gutter + index * col_width
        rows = len(column)
        cell_height = (size - 2 * gutter) / rows
        for row, char in enumerate(column):
            box = QRectF(left, gutter + row * cell_height, col_width, cell_height)
            font = fit_font(SEAL_FONT, size * (0.30 if rows == 2 else 0.42), char,
                            box.width() * 0.96, box.height() * 0.92)
            painter.setFont(font)
            painter.setPen(glyph)
            painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), char)
    painter.restore()

    colophon(painter, centre.x(), centre.y() + size * lift / 2 + 10, size * 2.4, note)


def draw_hanamaru(painter, rect, label, note, variant=None, press=1.0):
    """花丸：一支红笔的圈 + 一个记号，没有任何色块。"""
    size = float(rect.width())
    centre = rect.center()
    lift = 1.0 + 0.22 * (1.0 - press)
    painter.save()
    painter.translate(centre.x(), centre.y())
    painter.scale(lift, lift)
    pen = QPen(CINNABAR)
    pen.setWidthF(max(2.5, size * 0.050))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    ring = QPainterPath()
    ring.addEllipse(QRectF(-size * 0.44, -size * 0.40, size * 0.88, size * 0.80))
    painter.drawPath(ring)
    # 手写收尾时笔会压过起点：一小段出锋。
    tail = QPainterPath()
    tail.moveTo(size * 0.30, -size * 0.42)
    tail.cubicTo(size * 0.46, -size * 0.30, size * 0.42, -size * 0.12, size * 0.24, -size * 0.20)
    painter.drawPath(tail)
    mark = ink_columns(label)[-1][0]
    font = fit_font(SEAL_FONT, size * 0.42, mark, size * 0.60, size * 0.56)
    painter.setFont(font)
    painter.setPen(CINNABAR)
    painter.drawText(QRectF(-size * 0.30, -size * 0.28, size * 0.60, size * 0.56),
                     int(Qt.AlignmentFlag.AlignCenter), mark)
    painter.restore()
    colophon(painter, centre.x(), centre.y() + size * lift / 2 + 10, size * 2.4, note)


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
LABEL, NOTE_TEXT = '不可思议', '零提示 · 一次写对 · 6.1 秒'
VARIANTS = (('baiwen', draw_seal, 'A 白文方印'),
            ('zhuwen', draw_seal, 'B 朱文方印'),
            ('hanamaru', draw_hanamaru, 'C 花丸'))
for variant, drawer, title in VARIANTS:
    for size, tag in ((112, 'sm'), (152, 'md')):
        area = QRect(424 - size // 2, 452 - size // 2, size, size)
        for press, suffix in ((0.55, 'press'), (1.0, 'land')):
            path = os.path.join(OUT, '%s-%s-%s.png' % (variant, tag, suffix))
            composite(card, drawer, area, LABEL, NOTE_TEXT, variant, press, path)
            print('rendered', title, tag, suffix, '->', path)
