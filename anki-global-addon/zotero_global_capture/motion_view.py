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

from . import candy_badge, card_motion
from .card_motion import TIMING, badge_pose, shows_confetti, tier_caption, total_ms

# Superseded on 2026-11-05 by `badge_centre` below. The history lives in that function's
# docstring and in AUDIT §9.49: this number was moved 0.24 → 0.68 → 0.60 → 0.50 on opinion,
# and the value that finally looked right cleared the word by luck (2 px on tier 3). Nothing
# reads it any more, and nothing should re-introduce it — the clearance is a rule now.
# The badge is one drawn object now (see candy_badge), so the only particles left are the
# falling paper on the two no-hint tiers. Their colours come from the same palette so the
# confetti cannot read as a different design system landed on top.
CONFETTI_FALL = 340
CONFETTI_COLORS = ('#FFD84A', '#FF4FA3', '#FFF6C8', '#7FE3FF', '#3FBF5F')
# Fixed layouts instead of random ones: the same tier should look the same every time, and a
# deterministic particle set is what lets the offscreen check assert on it.
CONFETTI_SLOTS = (-196, -160, -128, -96, -64, -32, 0, 30, 62, 94, 126, 158, 186, 210)
# Each piece starts a little later than the one before it. Without the stagger every piece
# shares one height at any given moment, which rendered as a line of debris across the card
# rather than paper falling.
CONFETTI_STAGGER = 0.045
# The analytic reach under-reads the real one: on the live card tier 3's topmost painted
# pixel sat 162 px above the anchor where the geometry predicted 130. 1.25 is that measured
# gap, not a safety blanket — and the pixel-diff check re-measures it on every run.
BADGE_REACH_MARGIN = 1.25


def badge_footprint(tier, max_width, fit=1.0):
    """How tall the celebration actually paints — glow, rays, stars and ribbon included.

    Not the font size: on the live card the topmost painted pixel of tier 3 sat 162 px above
    the anchor where the letters suggested ~130. `candy_badge.paint_extent` reads the same
    constants the painter uses, and `BADGE_REACH_MARGIN` covers the gap between that
    arithmetic and the pixels.
    """
    above, below = candy_badge.paint_extent(card_motion.tier_caption(tier), tier,
                                            max_width=max_width, scale=card_motion.POP_TARGET)
    return (above + below) * BADGE_REACH_MARGIN * fit


def badge_centre(height, tier, max_width, rows=()):
    """Return (y, fit) for a celebration of `tier` on a card `height` tall.

    One implementation on purpose: the overlay paints through it, and the mockup and probe
    tools ask it the same question, so a preview can never show a placement the shipped card
    does not have. `rows` are the protected rectangles in card coordinates; with none given
    it degenerates to the centre of the card.
    """
    spans = [(row.top(), row.bottom()) for row in rows] if rows else []
    y, fit = card_motion.badge_anchor(height, badge_footprint(tier, max_width), spans)
    return int(y), fit


class Celebration(QWidget):
    """The badge + optional sparks + optional confetti, painted over one card."""

    def __init__(self, parent, theme='light'):
        super().__init__(parent)
        self.tier = 0
        self.progress = 0.0
        self.duration = 0
        # Rows the celebration may not sit on, supplied by the card at play time.
        self.word_row = None
        self.protected = ()
        self._placement = None
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

    def play(self, tier, cfg=None, word_row=None, protected=()):
        """Start (or restart) the sequence for this tier; tier 0 and an off switch show nothing.

        `word_row` and `protected` are rectangles in this overlay's own coordinates that the
        celebration may not sit on — the word being celebrated first among them, because
        covering the word the learner just spelled correctly is the one thing this animation
        must not do. They arrive from the card, which is the only place that knows where they
        actually are.
        """
        self.stop()
        self.tier = int(tier)
        self.duration = total_ms(self.tier, cfg)
        self.word_row = word_row
        self.protected = tuple(protected or ())
        self._placement = None
        if not self.duration:
            return False
        self.with_confetti = shows_confetti(self.tier)
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
        self._paint_badge(painter, anchor)
        painter.end()

    def _place(self):
        """Where the badge goes, and how big it may be. Computed once per celebration."""
        if getattr(self, '_placement', None) is None:
            self._placement = badge_centre(self.height(), self.tier, self.width() * 0.78,
                                           self.protected)
        return self._placement

    def _anchor(self):
        """The badge's centre, chosen so its painted reach clears the word it celebrates.

        This used to be `height × BADGE_TOP_FRACTION`, and the history of that number is a
        lesson in measuring before arguing: 0.24 put it on the word row (AUDIT §9.39),
        0.60/0.68 moved it onto the 回答正确 line, and 0.50 read as "centre of the card".
        The centre was never the requirement — *not covering the word* was — and a fixed
        fraction satisfied it by luck: 2 px of clearance on tier 3, 27 px on tier 4, and
        confetti sweeping straight through on tiers 1-2. Now the clearance is the rule.
        """
        from PyQt6.QtCore import QPoint
        y, _fit = self._place()
        return QPoint(self.width() // 2, y)

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
        """Hand the whole celebration to `candy_badge`, with the pose from `card_motion`.

        The Qt layer deliberately owns nothing about how it looks or moves: it supplies the
        anchor, the two words, the tier, and the card's width, and asks for the pose at the
        current progress. That is what makes the choreography testable without a window.
        """
        raw = self._phase('badge')
        if raw <= 0:
            return
        pose = badge_pose(raw, self.tier, TIMING['badge']['duration'])
        _y, fit = self._place()
        candy_badge.draw(painter, anchor, tier_caption(self.tier), self.tier, pose,
                         max_width=self.width() * 0.78, pixel_cap=candy_badge.WORD_PIXEL * fit)

    def _paint_confetti(self, painter, anchor):
        """Falling paper for the two no-hint tiers, cut as ribbons rather than rectangles.

        The reference art scatters curled strips, not squares; a square piece of "confetti"
        over a dark card is the flat clipart the user already rejected twice.
        """
        raw = self._phase('confetti')
        if raw <= 0:
            return
        step = TIMING['confetti']
        painter.save()
        for index in range(step['count']):
            local = (raw - index * CONFETTI_STAGGER) / max(0.05, 1.0 - index * CONFETTI_STAGGER)
            if local <= 0:
                continue
            local = min(1.0, local)
            offset = CONFETTI_SLOTS[index % len(CONFETTI_SLOTS)]
            x = anchor.x() + offset + 14 * math.sin(math.pi * local * 2 + index)
            top, room = card_motion.confetti_span(
                self.height(), self.word_row.bottom() if self.word_row is not None else None)
            y = top + min(CONFETTI_FALL, room) * local
            painter.save()
            painter.setOpacity(max(0.0, 1.0 - local * local))
            painter.translate(x, y)
            painter.rotate(local * 540 + index * 20)
            strip = QPainterPath()
            strip.moveTo(-5, -8)
            strip.quadTo(0, -2, -5, 8)
            strip.lineTo(5, 8)
            strip.quadTo(0, 2, 5, -8)
            strip.closeSubpath()
            painter.setBrush(QColor(CONFETTI_COLORS[index % len(CONFETTI_COLORS)]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(strip)
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
