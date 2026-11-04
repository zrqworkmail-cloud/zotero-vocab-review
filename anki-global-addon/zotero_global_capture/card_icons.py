"""Icons drawn instead of shipped as files.

Two shapes the card needs and Qt cannot give us here: a pushpin for the pin toggle, and a
loudspeaker inside a disc. A stylesheet `border-radius` on the 32px button box did not
round on the Qt build Anki 26 ships, so the circle has to be part of the pixmap.

The pin is drawn rather than taken from the Windows icon font on purpose: its Pin and
Pinned glyphs are both outlines, so the two states of the toggle would read as the same
icon — and an icon font that is not installed renders as an empty box.
"""
try:
    from aqt.qt import QColor, QIcon, QPainter, QPen, QPixmap, QPointF, QPolygonF, QRectF, Qt
except ImportError:  # an older aqt.qt shim may not re-export every name
    from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
    from PyQt6.QtCore import QPointF, QRectF, Qt


def _canvas(size):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return pixmap, painter


def _close(pixmap, painter):
    painter.end()
    return QIcon(pixmap)


def speaker_icon(glyph='#27344d', disc='#eef2ff', ring='#8996e8', size=32):
    """A loudspeaker on a filled disc: the disc is the shape, so it is round everywhere.

    The little sound-wave arc is left out on purpose — at 20-28px it reads as a stray dot
    next to the speaker, which is the first thing the user asked to have removed.
    """
    pixmap, painter = _canvas(size)
    scale = size / 32.0
    painter.setPen(QPen(QColor(ring), 1.0))
    painter.setBrush(QColor(disc))
    painter.drawEllipse(1, 1, size - 2, size - 2)
    pen = QPen(QColor(glyph))
    pen.setWidthF(1.4 * scale)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QColor(glyph))
    body = QPolygonF([QPointF(9 * scale, 13 * scale), QPointF(13 * scale, 13 * scale),
                      QPointF(17 * scale, 9 * scale), QPointF(17 * scale, 23 * scale),
                      QPointF(13 * scale, 19 * scale), QPointF(9 * scale, 19 * scale)])
    painter.drawPolygon(body)
    return _close(pixmap, painter)


def pin_icon(pinned, color='#5668ca', size=18):
    """A pushpin at the usual 45 degrees: solid while pinned, hollow once it is off.

    The tilt is the same in both states so the button does not appear to jump when clicked,
    and the fill is what carries the state — an upright solid blob read as a mushroom.
    """
    pixmap, painter = _canvas(size)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.2, size / 12.0))
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QColor(color) if pinned else Qt.BrushStyle.NoBrush)
    painter.translate(size / 2.0, size / 2.0)
    painter.rotate(-45)
    unit = size / 18.0
    painter.drawRoundedRect(QRectF(-6 * unit, -8.5 * unit, 12 * unit, 6.5 * unit), 3 * unit, 3 * unit)
    painter.drawRoundedRect(QRectF(-3.5 * unit, -2 * unit, 7 * unit, 3.5 * unit), 1.2 * unit, 1.2 * unit)
    painter.drawLine(QPointF(0, 1.5 * unit), QPointF(0, 8.5 * unit))
    return _close(pixmap, painter)
