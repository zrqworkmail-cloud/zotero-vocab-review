"""The spelling card's motion, drawn on top of the card itself.

Same import dance as `card_icons`: `aqt.qt` re-exports most names but not all of them on
every Anki build, and the offscreen test harnesses stub `aqt.qt` with a short list, so a
missing name has to fall back to PyQt6 rather than break the import.

Three decisions are baked in here and are worth knowing before changing anything:

* The celebration is a **child widget raised over the card**, not painting done in the
  card's own `paintEvent`. A QDialog paints its background before its children, so anything
  drawn there ends up *behind* the word and the buttons — invisible exactly where it matters.
* The badge never shakes the whole window (the mockup's top tier did). On the dark card a
  ±2px window jolt read as a rendering fault.
* Paging stops the celebration instead of letting it finish over the next card. The old card
  is hidden the moment a new one is handed over, and an overlay that outlives its card is how
  the F-key ghosting looked (AUDIT §9.32) — so `stop()` is called from the card's hide path.
"""

import math

try:  # pragma: no cover - the import list depends on the Anki build
    from aqt.qt import QColor, QFont, QPainter, QPainterPath, QPen, QRectF, Qt, QVariantAnimation, QWidget
except ImportError:  # an older aqt.qt shim may not re-export every name
    from PyQt6.QtCore import QRectF, Qt, QVariantAnimation
    from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
    from PyQt6.QtWidgets import QWidget

from .card_motion import (TIMING, shows_confetti, shows_sparks, tier_caption, tier_label,
                          total_ms)

BADGE_HEIGHT = 64
BADGE_FONT_PX = 26
CAPTION_FONT_PX = 11
BADGE_TOP_FRACTION = 0.68
SPARK_REACH = 150
SPARK_SIZE = 13
CONFETTI_FALL = 340
# Fixed layouts instead of random ones: the same tier should look the same every time, and a
# deterministic particle set is what lets the offscreen check assert on it.
SPARK_ANGLES = tuple(range(0, 360, 45))
CONFETTI_SLOTS = (-196, -160, -128, -96, -64, -32, 0, 30, 62, 94, 126, 158, 186, 210)
# Each piece starts a little later than the one before it. Without the stagger every piece
# shares one height at any given moment, which rendered as a line of debris across the card
# rather than paper falling.
CONFETTI_STAGGER = 0.045


class Celebration(QWidget):
    """The badge + optional sparks + optional confetti, painted over one card."""

    def __init__(self, parent, theme='light'):
        super().__init__(parent)
        self.tier = 0
        self.progress = 0.0
        self.duration = 0
        self.dark = theme == 'dark'
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.valueChanged.connect(self._advanced)
        self.animation.finished.connect(self.hide)
        # See-through and click-through: the card behind must stay readable and the rating
        # buttons must keep working while the celebration is on.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    def play(self, tier, setting_mode='full'):
        """Start (or restart) the sequence for this tier; tier 0 and 'off' show nothing."""
        self.stop()
        self.tier = int(tier)
        self.duration = total_ms(self.tier, setting_mode)
        if not self.duration:
            return False
        self.with_sparks = shows_sparks(self.tier) and setting_mode == 'full'
        self.with_confetti = shows_confetti(self.tier) and setting_mode == 'full'
        self.setGeometry(self.parent().rect() if self.parent() else QRectF())
        self.raise_()
        self.show()
        self.progress = 0.0
        self.animation.setDuration(self.duration)
        self.animation.start()
        self.update()
        return True

    def stop(self):
        if self.animation.state():
            self.animation.stop()
        self.hide()

    def active(self):
        return bool(self.animation.state()) and self.isVisible()

    def _advanced(self, value):
        self.progress = float(value)
        self.update()

    def paintEvent(self, event):
        if not self.tier or not self.duration:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        anchor = self._anchor()
        if self.with_confetti:
            self._paint_confetti(painter, anchor)
        if self.with_sparks:
            self._paint_sparks(painter, anchor)
        self._paint_badge(painter, anchor)
        painter.end()

    def _anchor(self):
        """Where the celebration is centred: over the feedback line, never over the word.

        The mockup stamped it at the card's middle, which on the real answer face lands exactly
        on the word being celebrated — the live capture of `stress` (2026-11-04) showed the
        pill covering the word and the 音标, reading as a glitch. The lower third already holds
        回答正确, so the badge belongs there.
        """
        from PyQt6.QtCore import QPoint
        return QPoint(self.width() // 2, int(self.height() * BADGE_TOP_FRACTION))

    def _phase(self, name, part=None):
        """0..1 through one step of the timeline, or 0 when it is not this step's turn."""
        step = TIMING[name]
        start = step['delay'] / self.duration
        end = (step['delay'] + step['duration']) / self.duration
        if name == 'badge':
            start = 0.0
            end = 1.0
        if not start <= self.progress <= end:
            return 0.0 if self.progress < start else 1.0
        raw = 0.0 if end == start else (self.progress - start) / (end - start)
        if part == 'in':
            span = TIMING['badge']['in_ms'] / TIMING['badge']['duration']
            return min(1.0, raw / span) if raw <= span else 1.0
        if part == 'out':
            span = TIMING['badge']['out_ms'] / TIMING['badge']['duration']
            return max(0.0, (raw - (1.0 - span)) / span) if raw >= 1.0 - span else 0.0
        return raw

    def _paint_badge(self, painter, anchor):
        raw = self._phase('badge')
        if raw <= 0:
            return
        entering = self._phase('badge', 'in')
        leaving = self._phase('badge', 'out')
        scale = 0.2 + (1.14 - 0.2) * entering if entering < 1 else 1.0
        angle = -8.0 * (1.0 - entering)
        opacity = min(1.0, entering * 1.6) * (1.0 - leaving)
        if opacity <= 0.01:
            return
        label, caption = tier_label(self.tier), tier_caption(self.tier)
        painter.save()
        painter.setOpacity(opacity)
        painter.translate(anchor.x(), anchor.y())
        painter.rotate(angle)
        painter.scale(scale, scale)
        font = QFont(self.font())
        font.setPixelSize(BADGE_FONT_PX)
        font.setBold(True)
        painter.setFont(font)
        width = max(190, painter.fontMetrics().horizontalAdvance(label) + 56)
        box = QRectF(-width / 2, -BADGE_HEIGHT / 2, width, BADGE_HEIGHT)
        path = QPainterPath()
        path.addRoundedRect(box, BADGE_HEIGHT / 2, BADGE_HEIGHT / 2)
        painter.fillPath(path, QColor(self.badge_color()))
        # Stroke the rounded outline, not a rectangle around it: drawRect on a pill put square
        # corners over the rounded fill, which is the first thing that looks broken in a
        # screenshot.
        border = QPen(QColor('#ffffff'))
        border.setWidthF(2.5)
        painter.setPen(border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        # The two lines are placed by metrics inside the pill. Drawing the caption at
        # "box centre + height/2 - 4" put it on the border, where it read as clipped text.
        painter.setPen(QColor(self.badge_text()))
        painter.drawText(box.adjusted(0, -11, 0, 0),
                         int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), label)
        small = QFont(font)
        small.setPixelSize(CAPTION_FONT_PX)
        small.setBold(True)
        painter.setFont(small)
        painter.drawText(box.adjusted(0, 17, 0, 0),
                         int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine), caption)
        painter.restore()

    def badge_color(self):
        return ('#ffd166' if self.tier == 1 else '#ffe58a' if self.tier == 2 else
                '#a7f3d0' if self.tier == 3 else '#cdd9ff')

    def badge_text(self):
        return '#20164a'

    def _paint_sparks(self, painter, anchor):
        raw = self._phase('sparks')
        if raw <= 0:
            return
        step = TIMING['sparks']
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(step['count']):
            angle = SPARK_ANGLES[index % len(SPARK_ANGLES)]
            reach = SPARK_REACH * raw
            size = SPARK_SIZE * (1.0 - raw * 0.55)
            painter.save()
            painter.setOpacity(max(0.0, 1.0 - raw))
            painter.translate(anchor.x(), anchor.y())
            painter.rotate(angle)
            painter.translate(reach, 0)
            star = QPainterPath()
            star.moveTo(0, -size)
            star.lineTo(size * 0.32, 0)
            star.lineTo(0, size)
            star.lineTo(-size * 0.32, 0)
            star.closeSubpath()
            painter.setBrush(QColor('#aab9ff' if self.dark else '#5668ca'))
            painter.drawPath(star)
            painter.restore()
        painter.restore()

    def _paint_confetti(self, painter, anchor):
        raw = self._phase('confetti')
        if raw <= 0:
            return
        step = TIMING['confetti']
        colors = ('#ffd166', '#71e0b5', '#aab9ff', '#ff99a9', '#cdd9ff')
        painter.save()
        for index in range(step['count']):
            local = (raw - index * CONFETTI_STAGGER) / max(0.05, 1.0 - index * CONFETTI_STAGGER)
            if local <= 0:
                continue
            local = min(1.0, local)
            offset = CONFETTI_SLOTS[index % len(CONFETTI_SLOTS)]
            x = anchor.x() + offset + 14 * math.sin(math.pi * local * 2 + index)
            y = -24 + CONFETTI_FALL * local
            painter.save()
            painter.setOpacity(max(0.0, 1.0 - local * local))
            painter.translate(x, y)
            painter.rotate(local * 540 + index * 20)
            painter.setBrush(QColor(colors[index % len(colors)]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(-4.5, -7, 9, 14))
            painter.restore()
        painter.restore()


def hop(widget, rise=None, duration=None):
    """Land one letter into its box: up 11px and back, with the OutBack overshoot.

    The box is a QLineEdit inside a QHBoxLayout, so the animation writes `pos` directly and
    restores the position the layout gave it. Nothing else relayouts while the learner is
    typing (the card's width is fixed at birth), and the end value is the layout's own slot,
    so a layout pass during the 180ms only snaps the box home sooner.
    """
    rise = TIMING['letter']['rise'] if rise is None else rise
    duration = TIMING['letter']['duration'] if duration is None else duration
    home = widget.property('zvr_home')
    if home is None:
        home = widget.pos()
        widget.setProperty('zvr_home', home)
    animation = QVariantAnimation(widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)

    def shifted(progress):
        widget.move(home.x(), home.y() - int(rise * _arc(progress)))

    animation.valueChanged.connect(shifted)
    animation.finished.connect(lambda: widget.move(home))
    animation.start()
    widget._zvr_hop = animation
    return animation


def _arc(progress):
    """Up and back down again inside one animation: sin over the half period."""
    return math.sin(math.pi * progress)


def shake(widget, swing=None, duration=None):
    """A wrong letter: swing left and right without growing, then sit still."""
    swing = TIMING['slip']['swing'] if swing is None else swing
    duration = TIMING['slip']['duration'] if duration is None else duration
    home = widget.property('zvr_home')
    if home is None:
        home = widget.pos()
        widget.setProperty('zvr_home', home)
    animation = QVariantAnimation(widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    steps = (-1, 1, -0.6, 0.6, 0)

    def swung(progress):
        index = min(len(steps) - 1, int(progress * len(steps)))
        widget.move(home.x() + int(swing * steps[index]), home.y())

    animation.valueChanged.connect(swung)
    animation.finished.connect(lambda: widget.move(home))
    animation.start()
    widget._zvr_shake = animation
    return animation
