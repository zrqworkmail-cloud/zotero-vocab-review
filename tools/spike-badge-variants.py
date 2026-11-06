"""Design spike for the celebration badge: three drawn variants, four keyframes each.

The user's note on 2026-11-04: the badge is still ugly — draw it, use a typeface with more
tension, and give it a real entrance and exit. This is a throwaway spike that paints with
QPainter onto images (it does not touch the shipped widget), so the variants can be compared
as pixels before anything goes into the add-on.

Font candidates were read off this machine's registry: 华文琥珀 (STHUPO.TTF), 隶书, 幼圆,
华文行楷, IQYHT Black, Impact, Arial Black, Segoe UI Black, Cooper Black, Rockwell Extra
Bold, Stencil. Whatever is missing must fall back loudly, not silently.
"""
import os
import sys

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32')])
os.add_dll_directory(os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(BASE))
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))
# Painted straight into QImages, so this runs on the real Windows platform: the offscreen
# font database reports only a handful of families and every display face below would
# silently fall back to Microsoft YaHei. No window is ever shown.
os.environ['QT_PLUGIN_PATH'] = os.path.join(BASE, 'PyQt6', 'Qt6', 'plugins')

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QPainter,
                         QPainterPath, QPen, QLinearGradient, QRadialGradient)
from PyQt6.QtWidgets import QApplication, QFontComboBox

OUT = os.path.join(os.environ['TEMP'], 'zvr-badge-variants')
os.makedirs(OUT, exist_ok=True)
app = QApplication([])
for font_file in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(font_file)

box = QFontComboBox()
_model = box.model()
FAMILIES = {str(_model.index(i, 0).data()) for i in range(_model.rowCount())}


def resolve(*candidates):
    """Pick the first candidate that Qt reports back unchanged, else the first one."""
    for name in candidates:
        if name in FAMILIES:
            return name
    # Qt also accepts the localized name for some Chinese faces.
    for name in candidates:
        probe = QFont(name, 40)
        from PyQt6.QtGui import QFontInfo
        if QFontInfo(probe).family().lower() == name.lower():
            return name
    return candidates[-1]


LABEL_FONT = resolve('STHupo', '华文琥珀', 'IQYHT Black', 'SimHei', 'Microsoft YaHei')
CAPTION_FONT = resolve('Impact', 'Arial Black', 'Segoe UI Black', 'Microsoft YaHei')
print('available families:', len(FAMILIES))
print('label font  ->', LABEL_FONT)
print('caption font->', CAPTION_FONT)

W, H = 460, 200
DARK = QColor('#171c2b')


def canvas():
    image = QImage(W, H, QImage.Format.Format_ARGB32)
    image.fill(DARK)
    return image


def paint_variant(variant, label, caption, t, path):
    """t is 0..1 through the badge's own entrance; >1 is handled by the caller."""
    image = canvas()
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    centre = QPointF(W / 2, H / 2)

    if variant == 'seal':
        # 华文琥珀 label inside a double ring, tilted like a rubber stamp.
        scale = 0.4 + 1.25 * t if t < 0.7 else 1.05 - 0.05 * (t - 0.7) / 0.3
        angle = -12 * (1 - min(1.0, t * 1.6))
        painter.save()
        painter.translate(centre)
        painter.rotate(angle)
        painter.scale(scale, scale)
        radius = 78
        glow = QRadialGradient(0, 0, radius)
        glow.setColorAt(0.0, QColor('#ff9f1c'))
        glow.setColorAt(1.0, QColor('#ff5d8f'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(0, 0), radius, radius * 0.62)
        ring = QPen(QColor('#fff3d6'))
        ring.setWidthF(4.0)
        painter.setPen(ring)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), radius - 7, radius * 0.62 - 7)
        font = QFont(LABEL_FONT)
        font.setPixelSize(38)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor('#2b1055'))
        painter.drawText(QRectF(-radius, -26, 2 * radius, 40),
                         int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), label)
        small = QFont(CAPTION_FONT)
        small.setPixelSize(13)
        painter.setFont(small)
        painter.setPen(QColor('#2b1055').lighter(115))
        painter.drawText(QRectF(-radius, 14, 2 * radius, 18),
                         int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), caption)
        painter.restore()

    elif variant == 'ribbon':
        # Skewed satin ribbon: gradient fill, thick cream outline, hard drop shadow.
        shift = (1 - t) * 90
        painter.save()
        painter.translate(centre.x(), centre.y() + shift)
        painter.rotate(-7)
        font = QFont(LABEL_FONT)
        font.setPixelSize(44)
        font.setBold(True)
        painter.setFont(font)
        text_w = QFontMetricsF(font).horizontalAdvance(label)
        width = text_w + 76
        height = 74
        body = QPainterPath()
        body.moveTo(-width / 2 + 14, -height / 2)
        body.lineTo(width / 2, -height / 2)
        body.lineTo(width / 2 - 14, height / 2)
        body.lineTo(-width / 2, height / 2)
        body.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 130))
        painter.drawPath(body.translated(7, 9))
        gradient = QLinearGradient(-width / 2, 0, width / 2, 0)
        gradient.setColorAt(0.0, QColor('#ffd166'))
        gradient.setColorAt(0.55, QColor('#ff9f1c'))
        gradient.setColorAt(1.0, QColor('#ff5d8f'))
        painter.setBrush(gradient)
        painter.drawPath(body)
        edge = QPen(QColor('#fff3d6'))
        edge.setWidthF(3.4)
        painter.setPen(edge)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(body)
        painter.setPen(QColor('#2b1055'))
        painter.drawText(QRectF(-width / 2, -height / 2 - 4, width, height),
                         int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), label)
        small = QFont(CAPTION_FONT)
        small.setPixelSize(12)
        painter.setFont(small)
        painter.setPen(QColor('#3a1a5e'))
        painter.drawText(QRectF(-width / 2, height / 2 - 20, width, 16),
                         int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), caption)
        painter.restore()

    else:
        # Sticker: heavy black outline and an offset solid shadow, no container at all.
        pop = 1 + 0.55 * (1 - t) ** 2 if t < 1 else 1.0
        painter.save()
        painter.translate(centre)
        painter.scale(2.0 - pop, 2.0 - pop)
        painter.rotate(-4)
        font = QFont(LABEL_FONT)
        font.setPixelSize(52)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        box_rect = QRectF(-metrics.horizontalAdvance(label) / 2 - 12, -40,
                          metrics.horizontalAdvance(label) + 24, 62)
        outline = QPainterPath()
        outline.addRoundedRect(box_rect, 16, 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#000000'))
        painter.drawPath(outline.translated(6, 8))
        painter.setBrush(QColor('#7cf5ff'))
        painter.drawPath(outline)
        stroke = QPen(QColor('#08324a'))
        stroke.setWidthF(5.0)
        painter.setPen(stroke)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(outline)
        painter.setPen(QColor('#08324a'))
        painter.drawText(box_rect, int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine),
                         label)
        small = QFont(CAPTION_FONT)
        small.setPixelSize(13)
        painter.setFont(small)
        painter.setPen(QColor('#08324a'))
        painter.drawText(box_rect.adjusted(0, 40, 0, 58),
                         int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), caption)
        painter.restore()

    painter.end()
    image.save(path, 'PNG')
    return path


LABEL, CAPTION = '不可思议', 'UNBELIEVABLE'
made = []
for variant in ('seal', 'ribbon', 'sticker'):
    for index, t in enumerate((0.15, 0.45, 0.75, 1.0)):
        path = os.path.join(OUT, '%s-%d.png' % (variant, index))
        made.append(paint_variant(variant, LABEL, CAPTION, t, path))
print('rendered', len(made), 'frames into', OUT)
