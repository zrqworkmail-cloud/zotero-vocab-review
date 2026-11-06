"""Golden 3D celebration badge, drawn the way match-3 game art does it.

The learner pointed at six real game assets (PERFECT / GREAT / AWESOME / EXCELLENT /
INCREDIBLE / UNBELIEVABLE) and asked for that look. What those assets actually share, read
off the pixels rather than guessed:

* The word is the object. It is extruded — a solid magenta side wall pushed down-right from
  the face — and the face is a three-stop gold (pale top, mid yellow, orange bottom) with a
  hard specular band across the upper third and one small white glint on the first letter.
* Everything sits inside one continuous cream outline, face and extruded side together,
  which is what makes it read as a sticker rather than as text with a shadow.
* Behind it: a sunburst whose rays fade to nothing at the outer edge, plus four-point
  sparkles, plus a star cluster on the higher tiers. (The wreath three of the six assets
  use is implemented but held back — see `_laurel`.)
* Below it: a ribbon with gold edges and curled tails, and one faceted gem at its centre.

Transparency is the part that has to be deliberate, because the card is dark navy and the
reference art sits on white:

* nothing here fills a rectangle; every shape is a path, or a gradient that reaches alpha 0,
* the glow and the rays end at alpha 0 so there is no visible disc edge on the card,
* the overlay widget keeps WA_TranslucentBackground and the painter is never given an opaque
  background brush.

Tier is carried by both the word and the decoration, escalating upward:
  T4 NICE          ribbon + gem, purple side wall
  T3 GREAT         rays + ribbon + gem, green ribbon
  T2 PERFECT       star cluster + rays + ribbon + gem, magenta
  T1 UNBELIEVABLE  as T2 with a wider glow and more sparkles
"""

import math

try:  # pragma: no cover - the import list depends on the Anki build
    from aqt.qt import QColor, QFont, QPainter, QPainterPath, QPen, QRectF, Qt
except ImportError:  # an older aqt.qt shim may not re-export every name
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QFontInfo, QFontMetrics, QLinearGradient, QRadialGradient

from . import card_motion

# --- palette, lifted from the six reference assets -------------------------------------
CREAM = '#FFF8EA'          # the one continuous outline
GOLD_TOP = '#FFF6C8'
GOLD_MID = '#FFD84A'
GOLD_LOW = '#F08A16'
GOLD_RIM = '#C85E0E'       # the thin dark line where the face meets the side wall
GLINT = '#FFFFFF'

SIDES = {1: '#D6236A', 2: '#D6236A', 3: '#C2521A', 4: '#7A2FA8'}
SIDES_DEEP = {1: '#8E0F45', 2: '#8E0F45', 3: '#7A3308', 4: '#4A1668'}
RIBBONS = {1: ('#FF4FA3', '#A8124F'), 2: ('#FF4FA3', '#A8124F'),
           3: ('#3FBF5F', '#1B6E33'), 4: ('#9A4BD6', '#5A1F8A')}
GEMS = {1: ('#7FE3FF', '#1E8FD0'), 2: ('#FF6FC0', '#B01573'),
        3: ('#8DF08D', '#1F8F3A'), 4: ('#C99BFF', '#6A2FA0')}

# The hero word is Latin because that is what the reference art is built around, and the
# learner asked for no Chinese in the pop-up — so this is the only text the badge draws.
DISPLAY_CANDIDATES = ('Arial Black', 'Segoe UI Black', 'Verdana', 'Microsoft YaHei')

WORD_PIXEL = 46.0          # face size of the hero word, before the pose scale
RIBBON_HEIGHT = 0.22       # of WORD_PIXEL, times 2.2, for the band's half-height
DEPTH_FRACTION = 0.20      # how far the word is extruded down, as a fraction of its height
# Fixed slots, not random ones: the same tier should look the same every time, and a
# deterministic layout is what lets the offscreen check assert on it. Fractions are of the
# badge width (x) and of the word height (y), measured from the word's centre.
# Every sparkle sits ABOVE the word. Two of them used to have a positive dy (0.52 and 0.48),
# which put them on the letters' extruded lower edge — the learner's rule is that nothing in
# the reward window may lie on top of its own word, at any tier (2026-11-05).
SPARKLE_SLOTS = ((-0.66, -0.92, 1.00), (0.64, -0.78, 0.72), (-0.52, -1.22, 0.52),
                 (0.56, -1.18, 0.86), (-0.30, -1.42, 0.60))
STAR_SLOTS = ((-0.28, -0.98, 0.66), (0.0, -1.12, 0.92), (0.28, -0.98, 0.66))
LAUREL_LEAVES = 6


def _colour(value, alpha=1.0):
    colour = QColor(value)
    colour.setAlphaF(max(0.0, min(1.0, alpha)))
    return colour


def _linear(x1, y1, x2, y2, stops, alpha):
    gradient = QLinearGradient(x1, y1, x2, y2)
    for position, value in stops:
        gradient.setColorAt(position, _colour(value, alpha))
    return gradient


def _radial(centre, radius, stops, alpha):
    """Stops are (position, colour); the outermost stop is always pushed to alpha 0.

    That rule is the whole reason the glow has no edge on the dark card. Applying one alpha
    to every stop — which is what the first version did — left the outer ring at the same
    opacity as the middle, and the "soft wash" rendered as a flat mauve disc the width of
    the card.
    """
    gradient = QRadialGradient(QPointF(centre), max(1.0, radius))
    last = len(stops) - 1
    for index, (position, value) in enumerate(stops):
        gradient.setColorAt(position, _colour(value, 0.0 if index == last else alpha))
    return gradient


def display_font(pixel):
    """The first chunky face this machine really has, resolved through QFontInfo.

    Offscreen the font database only reports a handful of families, so this has to run on
    the real platform — the same trap the earlier badge spike hit.
    """
    for name in DISPLAY_CANDIDATES:
        font = QFont(name)
        font.setPixelSize(int(round(pixel)))
        if QFontInfo(font).family().lower().startswith(name.split(' ')[0].lower()):
            font.setWeight(QFont.Weight.Black)
            font.setBold(True)
            return font
    font = QFont(DISPLAY_CANDIDATES[-1])
    font.setBold(True)
    font.setPixelSize(int(round(pixel)))
    return font


def word_path(centre, word, pixel):
    """The word as a path centred on `centre`, so outline / extrude / fill share one shape.

    The baseline is placed by metrics: the glyph span runs from `baseline - ascent` to
    `baseline + descent`, so centring that span on the anchor means
    `baseline = centre.y() + (ascent - descent) / 2`. Anything else puts the word a third of
    its own height too low, which reads as the badge floating above where it should be.
    """
    font = display_font(pixel)
    metrics = QFontMetrics(font)
    baseline = centre.y() + (metrics.ascent() - metrics.descent()) / 2.0
    path = QPainterPath()
    path.addText(centre.x() - metrics.horizontalAdvance(word) / 2.0, baseline, font, word)
    return path


def _glow(painter, centre, radius, pose, warm):
    """A soft gold wash that reaches alpha 0, with no disc edge over the navy card.

    The squash has to happen to the gradient, not only to the shape. Drawing a circular
    gradient into a flattened ellipse cuts it off at 74% of its own radius, which showed as a
    visible mauve rim around the celebration; scaling the painter keeps the last stop and the
    boundary on the same circle.
    """
    painter.save()
    painter.translate(centre.x(), centre.y())
    painter.scale(1.0, 0.74)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_radial(QPointF(0, 0), radius, ((0.0, GOLD_TOP), (0.45, GOLD_MID),
                                                     (1.0, warm)),
                             0.34 * pose['opacity'] * pose['glow']))
    painter.drawEllipse(QPointF(0, 0), radius, radius)
    painter.restore()


def _sunburst(painter, centre, radius, pose, warm):
    """Rays that start away from the middle.

    Wedges drawn from the exact centre pile their full-opacity ends on top of each other and
    turn to mud over a dark card; starting them at 0.34 radius leaves the word on clean air.
    """
    count = 18
    inner = radius * 0.34
    painter.save()
    painter.translate(centre.x(), centre.y())
    painter.rotate(pose['twinkle'] * 9.0)
    painter.setPen(Qt.PenStyle.NoPen)
    for index in range(count):
        angle = index * (360.0 / count)
        long = index % 2 == 0
        reach = radius * (1.0 if long else 0.78)
        half = 5.0 if long else 3.4
        wedge = QPainterPath()
        for step, factor in ((-half, 0.40), (0.0, 1.0), (half, 0.40)):
            radians = math.radians(angle + step)
            point = QPointF(reach * factor * math.cos(radians), reach * factor * math.sin(radians))
            inner_point = QPointF(inner * math.cos(radians), inner * math.sin(radians))
            if step == -half:
                wedge.moveTo(inner_point)
            else:
                wedge.lineTo(inner_point)
            wedge.lineTo(point)
        wedge.closeSubpath()
        painter.setBrush(_radial(QPointF(0, 0), reach,
                                 ((0.0, GOLD_MID), (0.62, GOLD_MID), (1.0, warm)),
                                 0.30 * pose['opacity'] * pose['glow']))
        painter.drawPath(wedge)
    painter.restore()


def _four_point(painter, x, y, size, value, alpha):
    star = QPainterPath()
    arms = ((0, -1), (0.24, -0.24), (1, 0), (0.24, 0.24), (0, 1), (-0.24, 0.24), (-1, 0),
            (-0.24, -0.24))
    for index, (dx, dy) in enumerate(arms):
        point = QPointF(x + dx * size, y + dy * size)
        if index == 0:
            star.moveTo(point)
        else:
            star.lineTo(point)
    star.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_colour(value, alpha))
    painter.drawPath(star)


def _star5(painter, x, y, radius, alpha):
    """Gold star with a cream edge and one facet of shine, as the reference clusters look."""
    points = []
    for index in range(10):
        angle = math.radians(-90 + index * 36)
        reach = radius if index % 2 == 0 else radius * 0.46
        points.append((x + reach * math.cos(angle), y + reach * math.sin(angle)))
    path = QPainterPath()
    path.moveTo(points[0][0], points[0][1])
    for index in range(1, 11):
        current = points[index % 10]
        following = points[(index + 1) % 10]
        path.quadTo(current[0], current[1], (current[0] + following[0]) / 2,
                     (current[1] + following[1]) / 2)
    path.closeSubpath()
    painter.setPen(QPen(_colour(CREAM, alpha), max(2.0, radius * 0.16)))
    painter.setBrush(_linear(0, y - radius, 0, y + radius,
                             ((0.0, GOLD_TOP), (0.55, GOLD_MID), (1.0, GOLD_LOW)), alpha))
    painter.drawPath(path)
    painter.save()
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_colour(GLINT, 0.5 * alpha))
    painter.drawEllipse(QPointF(x - radius * 0.08, y - radius * 0.48), radius * 0.40,
                        radius * 0.18)
    painter.restore()


def _laurel(painter, centre, width, height, alpha):
    """Two arcs of gold leaves opening toward the word.

    Kept because three of the six references use a wreath, but `draw` does not call it yet:
    with rays, a star cluster, a ribbon and a gem already on the card, the first render that
    included the wreath read as scattered grains rather than as a frame. If the celebration
    ever gets calmer, this is the piece to put back.
    """
    for side in (-1, 1):
        for index in range(LAUREL_LEAVES):
            fraction = index / float(LAUREL_LEAVES - 1)
            x = centre.x() + side * width * (0.46 + 0.07 * math.sin(fraction * math.pi))
            y = centre.y() + height * (0.95 - fraction * 2.05)
            painter.save()
            painter.translate(x, y)
            painter.rotate(side * (26 - 54 * fraction))
            leaf = QPainterPath()
            leaf.addEllipse(QPointF(0, 0), width * 0.050, width * 0.019)
            painter.setPen(QPen(_colour(GOLD_RIM, alpha), 1.2))
            painter.setBrush(_linear(-width * 0.05, 0, width * 0.05, 0,
                                     ((0.0, GOLD_LOW), (0.5, GOLD_TOP), (1.0, GOLD_MID)), alpha))
            painter.drawPath(leaf)
            painter.restore()


def geometry(word, pixel, centre, width=None):
    """Where every part of the badge sits, as numbers a check can assert on.

    This exists because the ribbon used to be placed by a magic fraction of the font size
    (`centre.y() + height * 0.80`), and the word's own bottom is not at that fraction — so
    the band's top curve reached up into the letters and ate their lower third. The learner
    called it twice, and the second time made the rule general: 「perfect不应该被下面这个东西
    挡住，所有的其他的那几个都是这样的要求，不要被挡住」. So `word_box` below is the protected
    area — face, extrusion and the cream outline — and every other piece is placed and then
    checked against it.
    """
    bounds = word_path(centre, word, pixel).boundingRect()
    depth = bounds.height() * DEPTH_FRACTION
    outline = max(5.0, bounds.height() * 0.14) / 2.0
    width = width or pixel * 5.4
    band = pixel * RIBBON_HEIGHT * 2.2
    stroke = max(2.0, band * 0.16) / 2.0
    # The gap has to clear the word's cream outline AND the ribbon's own gold edge stroke,
    # measured — not a fixed fraction. With the old `pixel * 0.06` the ribbon's top curve
    # still landed 0.1–0.4px inside the protected box on every tier, which `overlaps_word`
    # reported before the render ever looked wrong to the eye.
    gap = outline + stroke + pixel * 0.06
    ribbon_y = bounds.bottom() + depth + gap + band
    protected = QRectF(bounds.left() - outline, bounds.top() - outline,
                       bounds.width() + 2 * outline, bounds.height() + depth + 2 * outline)
    parts = {'ribbon': QRectF(centre.x() - width * 0.52, ribbon_y - band - stroke,
                              width * 1.04, (band + stroke) * 2),
             'gem': QRectF(centre.x() - band * 0.6, ribbon_y + band * 0.10, band * 1.2,
                           band * 1.04)}
    for name, (dx, dy, scale) in (('star', STAR_SLOTS[1]),):
        size = pixel * 0.30 * scale
        parts[name] = QRectF(centre.x() + width * dx - size, centre.y() + pixel * dy - size,
                             size * 2, size * 2)
    for index, (dx, dy, scale) in enumerate(SPARKLE_SLOTS):
        size = pixel * 0.24 * scale
        x = centre.x() + width * dx * 0.5
        parts['sparkle%d' % index] = QRectF(x - size, centre.y() + pixel * dy - size,
                                            size * 2, size * 2)
    return {'word': bounds, 'word_box': protected,
            'word_bottom': bounds.bottom() + depth,
            'band': band,
            'ribbon_y': ribbon_y,
            'ribbon_top': ribbon_y - band,
            'gem_bottom': ribbon_y + band * 0.62 + band * 0.52,
            'stars_top': centre.y() - pixel * 1.30,
            'parts': parts}


def overlaps_word(word, pixel, centre, width=None):
    """The names of the pieces that would be drawn on top of the word. Empty means clean."""
    geo = geometry(word, pixel, centre, width)
    return sorted(name for name, rect in geo['parts'].items() if rect.intersects(geo['word_box']))


def _ribbon(painter, x, y, width, band, tier, pose):
    """Band with gold edges and curled tails, and nothing written on it.

    The learner asked for no Chinese in the pop-up (2026-11-04: 「弹出的庆祝窗口不要汉字」), so
    the grade is carried by the one Latin word alone and the ribbon is pure structure — which
    is also how four of the six reference assets draw it.

    `y` is the band's centre line and `band` its half-height, both from `geometry`; the top
    curve reaches `y - band` and no further.
    """
    light, deep = RIBBONS[tier]
    alpha = pose['opacity'] * pose['ribbon']
    if alpha <= 0.02:
        return None
    y = y + (1.0 - pose['ribbon']) * 16.0
    for side in (-1, 1):
        tail = QPainterPath()
        edge = width * 0.5
        tail.moveTo(x + side * edge * 0.74, y - band * 0.42)
        tail.lineTo(x + side * edge * 1.14, y - band * 1.02)
        tail.lineTo(x + side * edge * 1.04, y - band * 0.06)
        tail.lineTo(x + side * edge * 1.18, y + band * 0.88)
        tail.lineTo(x + side * edge * 0.72, y + band * 0.56)
        tail.closeSubpath()
        painter.setPen(QPen(_colour(deep, alpha), 1.5))
        painter.setBrush(_colour(deep, alpha))
        painter.drawPath(tail)

    body = QPainterPath()
    body.moveTo(x - width * 0.52, y - band * 0.50)
    body.quadTo(x, y - band * 1.00, x + width * 0.52, y - band * 0.50)
    body.lineTo(x + width * 0.52, y + band * 0.50)
    body.quadTo(x, y + band * 1.00, x - width * 0.52, y + band * 0.50)
    body.closeSubpath()
    painter.setPen(QPen(_colour(GOLD_MID, alpha), max(2.0, band * 0.16)))
    painter.setBrush(_linear(0, y - band, 0, y + band,
                             ((0.0, light), (0.55, deep), (1.0, light)), alpha))
    painter.drawPath(body)
    return y, band


def _gem(painter, x, ribbon_y, band, tier, pose):
    """One faceted stone hanging on the ribbon's lower edge.

    It slides with the band (`(1 - ribbon) * 16`) rather than sitting at the resting position,
    or the gem would hover above the ribbon for the first 0.17 秒 of the entrance.
    """
    light, deep = GEMS[tier]
    alpha = pose['opacity'] * pose['ribbon']
    if alpha <= 0.02:
        return
    y = ribbon_y + (1.0 - pose['ribbon']) * 16.0 + band * 0.62
    size = band * 0.52
    outline = QPainterPath()
    outline.moveTo(x, y - size)
    outline.lineTo(x + size * 0.82, y - size * 0.20)
    outline.lineTo(x, y + size)
    outline.lineTo(x - size * 0.82, y - size * 0.20)
    outline.closeSubpath()
    painter.setPen(QPen(_colour(GOLD_MID, alpha), max(2.0, size * 0.16)))
    painter.setBrush(_linear(0, y - size, 0, y + size, ((0.0, light), (1.0, deep)), alpha))
    painter.drawPath(outline)
    painter.save()
    painter.setClipPath(outline)
    painter.setPen(QPen(_colour(GLINT, 0.45 * alpha), 1.0))
    for dx in (-0.45, 0.0, 0.45):
        facet = QPainterPath()
        facet.moveTo(x + size * dx, y - size)
        facet.lineTo(x + size * (dx + 0.26), y + size)
        painter.drawPath(facet)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_colour(GLINT, 0.7 * alpha))
    painter.drawEllipse(QPointF(x - size * 0.20, y - size * 0.40), size * 0.26, size * 0.13)
    painter.restore()


def _extruded_word(painter, path, tier, pose):
    """Cream outline → side wall → gold face → bevel and specular → one white glint."""
    alpha = pose['opacity']
    bounds = path.boundingRect()
    depth = bounds.height() * DEPTH_FRACTION
    shift = QPointF(depth * 0.40, depth)

    # 1. One continuous cream edge around face and side wall together.
    silhouette = QPainterPath(path)
    silhouette = silhouette.translated(shift)
    painter.setPen(QPen(_colour(CREAM, alpha), max(5.0, bounds.height() * 0.14)))
    painter.setBrush(_colour(CREAM, alpha))
    painter.drawPath(silhouette)
    painter.drawPath(path)

    # 2. The side wall: the same shape filled at small steps along the extrusion direction.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_linear(0, bounds.top(), 0, bounds.bottom() + shift.y(),
                             ((0.0, SIDES[tier]), (1.0, SIDES_DEEP[tier])), alpha))
    steps = max(7, int(depth))
    for step in range(1, steps):
        fraction = step / float(steps)
        painter.drawPath(path.translated(QPointF(shift.x() * fraction, shift.y() * fraction)))

    # 3. The face: three-stop gold with a hard rim where it meets the wall.
    painter.setBrush(_linear(0, bounds.top(), 0, bounds.bottom(),
                             ((0.0, GOLD_TOP), (0.42, GOLD_MID), (0.78, GOLD_LOW),
                              (1.0, GOLD_RIM)), alpha))
    painter.drawPath(path)

    # 4. Bevel and specular, clipped to the face so nothing spills onto the card.
    painter.save()
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_colour(GLINT, 0.5 * alpha))
    painter.drawRect(QRectF(bounds.left(), bounds.top(), bounds.width(), bounds.height() * 0.09))
    painter.setBrush(_colour(GLINT, 0.26 * alpha))
    painter.drawEllipse(QPointF(bounds.center().x(), bounds.top() + bounds.height() * 0.30),
                        bounds.width() * 0.50, bounds.height() * 0.20)
    painter.restore()

    # 5. One white four-point glint on the first letter, as in every one of the six refs.
    twinkle = 0.55 + 0.45 * math.sin(pose['twinkle'] * math.pi * 2.0)
    _four_point(painter, bounds.left() + bounds.width() * 0.08,
                bounds.top() + bounds.height() * 0.14, bounds.height() * 0.22, GLINT,
                0.85 * alpha * twinkle)


def fit_pixel(word, max_width, cap=None):
    """Shrink the face until the whole word fits the card.

    UNBELIEVABLE is twelve letters and NICE is four; one fixed pixel size either clips the
    long word off the card or makes the short one look like a label. This is the only place
    that asks the font database anything, so the drawing below can stay metric-free.
    """
    cap = WORD_PIXEL if cap is None else cap
    pixel = cap
    while pixel > 18:
        if QFontMetrics(display_font(pixel)).horizontalAdvance(word) <= max_width:
            return pixel
        pixel -= 1
    return pixel


def draw(painter, centre, word, tier, pose, max_width=None, pixel_cap=None):
    """Paint the celebration centred on `centre`; `pose` comes from card_motion.badge_pose.

    One word, no second line: the learner asked for no Chinese in the pop-up. `max_width` is
    the card's own width — the badge is sized from it so a long word can never run off the
    edge.
    """
    if tier not in SIDES or pose['opacity'] <= 0.02:
        return
    max_width = max_width or 420.0
    # `pixel_cap` is how far the badge may shrink to keep its painted reach off a row
    # the card has declared protected; None means the caller is not constraining it.
    pixel = fit_pixel(word, max_width, cap=pixel_cap or WORD_PIXEL)
    width = min(max_width, pixel * 5.4)
    height = pixel
    placed = geometry(word, pixel, centre, width)
    path = word_path(centre, word, pixel)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.translate(centre.x(), centre.y())
    painter.rotate(pose['angle'])
    painter.scale(pose['scale'], pose['scale'])
    painter.translate(-centre.x(), -centre.y())
    warm = RIBBONS[tier][0]
    point = QPointF(centre.x(), centre.y())

    _glow(painter, point, width * (0.52 if tier == 1 else 0.44), pose, warm)
    # Which decoration belongs to which tier is `card_motion`'s decision, not this module's:
    # tier 1 is the best grade and 4 the plainest, and getting that backwards once already
    # left 不可思议 with no stars while 很棒 had them.
    if card_motion.shows_rays(tier):
        _sunburst(painter, point, width * 0.46, pose, warm)
    if card_motion.shows_stars(tier):
        for index, (dx, dy, scale) in enumerate(STAR_SLOTS):
            pop = max(0.0, min(1.0, (pose['glow'] - 0.12 * index) / 0.55))
            _star5(painter, centre.x() + width * dx, centre.y() + height * dy,
                   height * 0.30 * scale * (0.55 + 0.45 * pop), pose['opacity'] * pop)
    # The word is drawn last among the things behind it and first among the things in front,
    # so nothing the ribbon or the gem owns can land on the letters.
    _extruded_word(painter, path, tier, pose)
    _ribbon(painter, centre.x(), placed['ribbon_y'], width * 0.72, placed['band'], tier, pose)
    _gem(painter, centre.x(), placed['ribbon_y'], placed['band'], tier, pose)
    for index, (dx, dy, scale) in enumerate(SPARKLE_SLOTS[:card_motion.sparkle_count(tier)]):
        twinkle = 0.35 + 0.65 * abs(math.sin(pose['twinkle'] * math.pi * 2 + index * 1.3))
        _four_point(painter, centre.x() + width * dx * 0.5, centre.y() + height * dy,
                    height * 0.24 * scale, GOLD_TOP if index % 2 else CREAM,
                    pose['opacity'] * twinkle)
    painter.restore()


def paint_extent(word, tier, centre_y=None, max_width=None, scale=1.0):
    """How far the badge actually paints above and below its centre, in pixels.

    `geometry` answers where the pieces are; this answers where ANYTHING is drawn, because
    the celebration is not only its letters: the glow, the rays, the stars and the sparkles
    all reach further, and it was the reach — not the word — that came within 2 px of the
    answer word on the real machine. The anchor needs this number to promise clearance.

    Everything here is read from the same constants the drawing uses, so a decoration that
    grows cannot silently outrun the guard.
    """
    from . import card_motion
    width = max_width or WORD_PIXEL * 5.4
    pixel = fit_pixel(word, width) * scale
    width = min(width, pixel * 5.4)
    placed = geometry(word, pixel, QPointF(0, 0), width)
    above = -(placed['word_box'].top())
    below = placed['gem_bottom']
    glow = width * (0.52 if tier == 1 else 0.44) * 0.74          # the painter is squashed to 0.74
    above = max(above, glow)
    below = max(below, glow)
    if card_motion.shows_rays(tier):
        rays = width * 0.46
        above = max(above, rays)
        below = max(below, rays)
    if card_motion.shows_stars(tier):
        above = max(above, pixel * 1.12 + pixel * 0.30 * STAR_SLOTS[1][2])
    for dx, dy, size_scale in SPARKLE_SLOTS[:card_motion.sparkle_count(tier)]:
        reach = abs(pixel * dy) + pixel * 0.24 * size_scale
        if dy < 0:
            above = max(above, reach)
        else:
            below = max(below, reach)
    return above, below
