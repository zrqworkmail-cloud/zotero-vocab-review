"""Design spike v7 — 开心消消乐 candy language, five forms, drawn in code on the real card.

Token system (derived from the game's own visual language, adapted to our navy card):

  糖粉 CANDY_PINK  #FF5E8F   主体：充气糖字的正面
  果酱 JAM_DEEP    #B01F4E   最外圈暗边 + 内阴影，让字"厚"起来
  奶白 MILK        #FFF6E8   糖字外描边（消消乐的字永远有一圈奶白）
  柠檬 CANDY_LEMON #FFE066   星芒射线、缎带高光
  冰蓝 CANDY_BLUE  #56C7FF   冷档主体（T3/T4 用，避免一路粉红）
  卡底 CARD_NAVY   #1A2238   卡片本身

Type: 华文琥珀 (STHupo) is already a candy face and resolves on this machine; it is the
display face for the mark, and nothing else in the celebration uses type.

Five forms, same footprint (centre 255,382 · width 244 · height 80) so the comparison is
about the form, not the size:
  A 星芒糖果字   the word itself is inflated candy, radial rays behind, two sparkles
  B 缎带横幅     ribbon band with curled tails and fold shadows
  C 宝石圆章     faceted medallion: rim, bevel, gloss
  D 果冻气泡     translucent blister, one big specular blob
  E 星星奖牌     rounded 5-point star with the word across it

All five are drawn with the same three-pass candy recipe (outer jam stroke → milk stroke →
gradient fill → clipped specular), which is what makes them read as one family.
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
from PyQt6.QtGui import (QBrush, QColor, QCursor, QDesktopServices, QFont, QFontDatabase,
                         QFontInfo, QFontMetrics, QImage, QLinearGradient, QPainter,
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

OUT = os.path.join(os.environ['TEMP'], 'zvr-badge-v7')
os.makedirs(OUT, exist_ok=True)
app = QApplication([])
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'

CANDY_PINK = QColor('#FF5E8F')
CANDY_ROSE = QColor('#E2346C')
JAM_DEEP = QColor('#B01F4E')
MILK = QColor('#FFF6E8')
CANDY_LEMON = QColor('#FFE066')
CANDY_BLUE = QColor('#56C7FF')
CANDY_SKY = QColor('#2C8FD6')
CARD_NAVY = QColor('#1A2238')

DISPLAY = 'STHupo'
print('display face resolves ->', QFontInfo(QFont(DISPLAY, 40)).family())

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


def word_path(centre, text, pixel, tilt=0.0):
    """The word as a path, so every form can outline / fill / clip it the same way."""
    font = QFont(DISPLAY)
    font.setBold(True)
    font.setPixelSize(int(pixel))
    path = QPainterPath()
    width = QFontMetrics(font).horizontalAdvance(text)
    path.addText(centre.x() - width / 2, centre.y(), font, text)
    if tilt:
        bound = path.boundingRect()
        pivot = QPointF(bound.center().x(), bound.center().y())
        from PyQt6.QtGui import QTransform
        transform = QTransform()
        transform.translate(pivot.x(), pivot.y())
        transform.rotate(tilt)
        transform.translate(-pivot.x(), -pivot.y())
        path = transform.map(path)
    return path


def candy_word(painter, path, top, bottom, outline=True, gloss=True):
    """Three-pass candy recipe: 果酱暗边 → 奶白描边 → 渐变填充 → 高光。"""
    if outline:
        outer = QPen(JAM_DEEP)
        outer.setWidthF(11.0)
        outer.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(outer)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        milk = QPen(MILK)
        milk.setWidthF(6.0)
        milk.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(milk)
        painter.drawPath(path)
    fill = QLinearGradient(0, path.boundingRect().top(), 0, path.boundingRect().bottom())
    fill.setColorAt(0.0, top)
    fill.setColorAt(0.55, bottom)
    fill.setColorAt(1.0, top)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fill)
    painter.drawPath(path)
    if gloss:
        painter.save()
        painter.setClipPath(path)
        bound = path.boundingRect()
        shine = QPainterPath()
        shine.addEllipse(QPointF(bound.center().x(), bound.top() + bound.height() * 0.26),
                         bound.width() * 0.56, bound.height() * 0.24)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 105))
        painter.drawPath(shine)
        painter.restore()


def rays(painter, centre, radius, count, colour, alpha, spin=0.0):
    """星芒：长短交替的楔形，靠中心实、靠外淡。"""
    painter.save()
    painter.translate(centre.x(), centre.y())
    painter.rotate(spin)
    for index in range(count):
        angle = index * (360.0 / count)
        long = index % 2 == 0
        reach = radius * (1.0 if long else 0.66)
        half = 7.5 if long else 5.0
        wedge = QPainterPath()
        wedge.moveTo(0, 0)
        wedge.lineTo(reach * math.cos(math.radians(angle - half)),
                     reach * math.sin(math.radians(angle - half)))
        wedge.lineTo(reach * math.cos(math.radians(angle + half)),
                     reach * math.sin(math.radians(angle + half)))
        wedge.closeSubpath()
        fade = QRadialGradient(QPointF(0, 0), reach)
        soft = QColor(colour)
        soft.setAlphaF(alpha)
        clear = QColor(colour)
        clear.setAlphaF(0.0)
        fade.setColorAt(0.0, soft)
        fade.setColorAt(0.72, soft)
        fade.setColorAt(1.0, clear)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fade)
        painter.drawPath(wedge)
    painter.restore()


def sparkle(painter, centre, size, colour):
    """四角星：消消乐里最小的那个糖闪。"""
    star = QPainterPath()
    points = ((0, -size), (size * 0.22, -size * 0.22), (size, 0), (size * 0.22, size * 0.22),
              (0, size), (-size * 0.22, size * 0.22), (-size, 0), (-size * 0.22, -size * 0.22))
    star.moveTo(centre.x() + points[0][0], centre.y() + points[0][1])
    for x, y in points[1:]:
        star.lineTo(centre.x() + x, centre.y() + y)
    star.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    painter.drawPath(star)


def drop(painter, path, offset=4.0, alpha=70):
    bound = path.boundingRect()
    shadow = QColor(0, 0, 0, alpha)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shadow)
    shifted = path.translated(QPointF(0, offset))
    painter.drawPath(shifted)
    return bound


def tint(name, alpha):
    colour = QColor(name)
    colour.setAlphaF(alpha / 255.0)
    return colour


# --- A 星芒糖果字 ---------------------------------------------------------------
def form_starburst(painter, centre, box, text, tier):
    rays(painter, centre, box.height() * 0.98, 20, CANDY_LEMON, 0.40, spin=9.0)
    path = word_path(centre, text, box.height() * 0.80, tilt=-3.0)
    drop(painter, path)
    candy_word(painter, path, CANDY_PINK, CANDY_ROSE)
    sparkle(painter, QPoint(int(centre.x() - box.width() * 0.46), int(centre.y() - 20)), 8, MILK)
    sparkle(painter, QPoint(int(centre.x() + box.width() * 0.44), int(centre.y() + 18)), 6,
            CANDY_LEMON)


# --- B 缎带横幅 ---------------------------------------------------------------
def form_ribbon(painter, centre, box, text, tier):
    w, h = box.width() * 0.92, box.height() * 0.62
    band = QRectF(centre.x() - w / 2, centre.y() - h / 2, w, h)
    for side in (-1, 1):
        tail = QPainterPath()
        x = centre.x() + side * (w / 2 - 6)
        tail.moveTo(x, band.top() + 4)
        tail.lineTo(x + side * 34, band.top() - 7)
        tail.lineTo(x + side * 34, band.bottom() - 7)
        tail.lineTo(x, band.bottom() + 4)
        tail.closeSubpath()
        painter.setPen(QPen(JAM_DEEP, 3.0))
        painter.setBrush(QColor('#8E1840'))
        painter.drawPath(tail)
        notch = QPainterPath()
        notch.moveTo(x + side * 34, band.top() - 7)
        notch.lineTo(x + side * 22, band.top() + h / 2 - 7)
        notch.lineTo(x + side * 34, band.bottom() - 7)
        notch.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(CARD_NAVY)
        painter.drawPath(notch)
    body = QPainterPath()
    body.addRoundedRect(band, 8, 8)
    painter.setPen(QPen(JAM_DEEP, 4.0))
    fill = QLinearGradient(0, band.top(), 0, band.bottom())
    fill.setColorAt(0.0, CANDY_ROSE)
    fill.setColorAt(1.0, QColor('#8E1840'))
    painter.setBrush(fill)
    painter.drawPath(body)
    shine = QLinearGradient(0, band.top(), 0, band.top() + h * 0.45)
    shine.setColorAt(0.0, QColor(255, 255, 255, 90))
    shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shine)
    painter.drawPath(body)
    path = word_path(centre, text, h * 0.86)
    candy_word(painter, path, MILK, QColor('#FFDCB8'), outline=True, gloss=False)


# --- C 宝石圆章 ---------------------------------------------------------------
def form_medallion(painter, centre, box, text, tier):
    r = box.height() * 0.86
    halo = QPainterPath()
    halo.addEllipse(QPointF(centre.x(), centre.y()), r + 7, r + 7)
    painter.setPen(QPen(JAM_DEEP, 4.0))
    rim = QLinearGradient(0, centre.y() - r, 0, centre.y() + r)
    rim.setColorAt(0.0, CANDY_LEMON)
    rim.setColorAt(1.0, QColor('#E0A32C'))
    painter.setBrush(rim)
    painter.drawPath(halo)
    face = QPainterPath()
    face.addEllipse(QPointF(centre.x(), centre.y()), r, r)
    body = QRadialGradient(QPointF(centre.x() - r * 0.3, centre.y() - r * 0.4), r * 2.1)
    body.setColorAt(0.0, CANDY_ROSE)
    body.setColorAt(1.0, JAM_DEEP)
    painter.setPen(QPen(MILK, 2.5))
    painter.setBrush(body)
    painter.drawPath(face)
    painter.save()
    painter.setClipPath(face)
    gloss = QPainterPath()
    gloss.addEllipse(QPointF(centre.x() - r * 0.15, centre.y() - r * 0.62), r * 0.66, r * 0.26)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 95))
    painter.drawPath(gloss)
    painter.restore()
    path = word_path(centre, text, r * 0.70)
    candy_word(painter, path, MILK, QColor('#FFD9A8'), outline=True, gloss=False)


# --- D 果冻气泡 ---------------------------------------------------------------
def form_jelly(painter, centre, box, text, tier):
    w, h = box.width() * 0.80, box.height() * 0.86
    rect = QRectF(centre.x() - w / 2, centre.y() - h / 2, w, h)
    body = QPainterPath()
    body.addRoundedRect(rect, h * 0.48, h * 0.48)
    painter.setPen(QPen(JAM_DEEP, 5.0))
    fill = QLinearGradient(0, rect.top(), 0, rect.bottom())
    fill.setColorAt(0.0, tint('#FFC2D6', 235))
    fill.setColorAt(0.45, tint('#FF7FA8', 240))
    fill.setColorAt(1.0, tint('#C2265C', 245))
    painter.setBrush(fill)
    painter.drawPath(body)
    painter.save()
    painter.setClipPath(body)
    blob = QPainterPath()
    blob.addEllipse(QPointF(centre.x() - w * 0.18, rect.top() + h * 0.24), w * 0.28, h * 0.15)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 205))
    painter.drawPath(blob)
    bounce = QPainterPath()
    bounce.addEllipse(QPointF(centre.x() + w * 0.26, rect.bottom() - h * 0.20), w * 0.13, h * 0.07)
    painter.setBrush(QColor(255, 255, 255, 80))
    painter.drawPath(bounce)
    painter.restore()
    path = word_path(centre, text, h * 0.66)
    candy_word(painter, path, CANDY_PINK, CANDY_ROSE, outline=True, gloss=True)


# --- E 星星奖牌 ---------------------------------------------------------------
def rounded_star(painter, centre, radius):
    points = []
    for index in range(10):
        angle = math.radians(-90 + index * 36)
        reach = radius if index % 2 == 0 else radius * 0.42
        points.append((centre.x() + reach * math.cos(angle), centre.y() + reach * math.sin(angle)))
    star = QPainterPath()
    star.moveTo(points[0][0], points[0][1])
    for index in range(1, 10):
        nxt = points[(index + 1) % 10]
        mid = points[index]
        star.quadTo(mid[0], mid[1], (mid[0] + nxt[0]) / 2, (mid[1] + nxt[1]) / 2)
    star.closeSubpath()
    return star


def form_star(painter, centre, box, text, tier):
    radius = box.height() * 0.92
    star = rounded_star(painter, QPointF(centre.x(), centre.y()), radius)
    painter.setPen(QPen(JAM_DEEP, 6.0))
    painter.setBrush(QColor('#8E1840'))
    painter.drawPath(star)
    painter.setPen(QPen(MILK, 3.0))
    painter.setBrush(QColor('#FFF0C8'))
    painter.drawPath(star)
    painter.save()
    painter.setClipPath(star)
    face = QLinearGradient(0, centre.y() - radius, 0, centre.y() + radius)
    face.setColorAt(0.0, CANDY_LEMON)
    face.setColorAt(1.0, QColor('#F0A93A'))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(face)
    painter.drawPath(star)
    shine = QPainterPath()
    shine.addEllipse(QPointF(centre.x() - radius * 0.1, centre.y() - radius * 0.52),
                     radius * 0.55, radius * 0.26)
    painter.setBrush(QColor(255, 255, 255, 150))
    painter.drawPath(shine)
    painter.restore()
    path = word_path(centre, text, radius * 0.48)
    candy_word(painter, path, CANDY_PINK, CANDY_ROSE, outline=True, gloss=True)


FORMS = (('A 星芒糖果字', form_starburst), ('B 缎带横幅', form_ribbon),
         ('C 宝石圆章', form_medallion), ('D 果冻气泡', form_jelly), ('E 星星奖牌', form_star))
BOX = QRect(255 - 122, 382 - 40, 244, 80)


def shoot(name, form, text, press=1.0, tier=2):
    card = answer_card()
    base = card.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(base)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    scale = 1.0 + 0.34 * (1.0 - min(press, 1.0))
    rise = -12.0 * (1.0 - min(press, 1.0)) - 16.0 * max(0.0, press - 1.0)
    painter.translate(BOX.center().x(), BOX.center().y() + rise)
    painter.scale(scale, scale)
    painter.translate(-BOX.center().x(), -BOX.center().y())
    if press > 1.0:
        painter.setOpacity(max(0.0, 1.0 - (press - 1.0) * 1.4))
    elif press < 1.0:
        painter.setOpacity(max(0.3, press))
    form(painter, BOX.center(), BOX, text, tier)
    painter.end()
    base.save(os.path.join(OUT, '%s.png' % name), 'PNG')
    print('rendered', name)


def form_ladder(painter, centre, box, text, tier):
    """档位越高，装饰越多；T4 只有字，T1 才有星芒+双星。冷色给低档，暖色给高档。"""
    if tier == 4:
        path = word_path(centre, text, box.height() * 0.62, tilt=-2.0)
        drop(painter, path)
        candy_word(painter, path, CANDY_BLUE, CANDY_SKY)
        return
    if tier == 3:
        rays(painter, centre, box.height() * 0.72, 10, CANDY_LEMON, 0.26, spin=9.0)
        path = word_path(centre, text, box.height() * 0.70, tilt=-2.5)
        drop(painter, path)
        candy_word(painter, path, CANDY_BLUE, CANDY_SKY)
        return
    burst = box.height() * (0.98 if tier == 2 else 1.18)
    rays(painter, centre, burst, 20, CANDY_LEMON, 0.40, spin=9.0)
    path = word_path(centre, text, box.height() * (0.80 if tier == 2 else 0.88), tilt=-3.0)
    drop(painter, path)
    candy_word(painter, path, CANDY_PINK, CANDY_ROSE)
    sparkle(painter, QPoint(int(centre.x() - box.width() * 0.46), int(centre.y() - 20)), 8, MILK)
    if tier == 1:
        sparkle(painter, QPoint(int(centre.x() + box.width() * 0.44), int(centre.y() + 18)), 10,
                CANDY_LEMON)
        sparkle(painter, QPoint(int(centre.x() + box.width() * 0.30), int(centre.y() - 34)), 6, MILK)


for title, form in FORMS:
    shoot(title.split(' ')[0] + '-wanmei', form, '完美')
shoot('A-taibang', form_starburst, '太棒了')
shoot('C-liang', form_medallion, '不错')
for tier, word in ((4, '不错'), (3, '很棒'), (2, '完美'), (1, '太棒了')):
    shoot('F-t%d' % tier, form_ladder, word, tier=tier)
for press, suffix in ((0.45, 'fall'), (0.85, 'contact'), (1.0, 'hold'), (1.5, 'lift')):
    shoot('G-%s' % suffix, form_ladder, '太棒了', tier=1, press=press)
