"""Which spelling performance earns which motion — and how long it is allowed to take.

The user approved this on 2026-11-04 from the mockup (`design/spelling-motion-mockup.html`):
letters hop into their boxes and a badge celebrates at one of four tiers. Two things were
decided against the mockup and are recorded here so they do not creep back: the top tier
**no longer shakes the whole card** (±2px on the dark card looked like a rendering fault),
and paging always outranks the animation. A third mockup item — the answer word sliding up
as it appears — was never implemented and its timing entry has now been deleted, so what is
listed here is what actually moves.

The badge's own wording changed three times on 2026-11-04, and the last two are the live ones.
The first three directions (a pill, a drawn seal, a 朱批 stamp) were all rejected as ugly, and
the user then supplied six real match-3 game assets and said to look like those — so the hero
word became Latin (`TIER_CAPTIONS`). Having seen it on the screen, the next instruction was
「弹出的庆祝窗口不要汉字」: the badge now draws that one Latin word and nothing else. The
card's own Chinese lines (回答正确, the 建议 sentence) are separate text in `review_popup` and
are not part of the celebration.

Keeping the decisions in plain arithmetic means the complaints a user can actually make —
"too flashy", "it blocked my Enter" — are testable without a window. The Qt layer only plays
what `timeline()` and `badge_pose()` return.
"""

FAST_SECONDS = 6.0
# The three question types that are answered by typing letters into the shared boxes. The
# celebration used to cover `typing` only, which meant a cloze card hopped every letter and
# then said nothing — and in a whole day of real studying that scope produced 6 celebrations
# out of 134 cards (2026-11-04), which is why the user asked for it to be widened.
SPELLING_MODES = ('typing', 'cloze', 'listening')

TIER_CAPTIONS = {1: 'UNBELIEVABLE', 2: 'PERFECT', 3: 'GREAT', 4: 'NICE'}
# The Chinese grades were dropped from the pop-up on 2026-11-04 (「弹出的庆祝窗口不要汉字」),
# so there is no `TIER_LABELS` any more. The card's own 回答正确 / 建议"Mastered" lines are
# separate text in `review_popup` and still Chinese — the switch is only about the badge.

# Milliseconds lifted from the approved timing table. The badge is the spine of the sequence
# (260 in + 520 hold + 200 out = 980) and everything else is scheduled to finish inside it,
# which is what keeps the whole celebration under one second and off the paging path.
TIMING = {
    'letter': {'delay': 0, 'duration': 180, 'easing': 'OutBack', 'rise': 11},
    'slip': {'delay': 0, 'duration': 220, 'swing': 5},
    'badge': {'delay': 0, 'duration': 980, 'in_ms': 260, 'hold_ms': 520, 'out_ms': 200,
              'easing': 'OutBack'},
    'confetti': {'delay': 80, 'duration': 900, 'count': 14},
}


def hop_allowed(cfg):
    """Do the letters bounce as they land? The learner's switch, on by default."""
    value = (cfg or {}).get('review_motion_hop')
    if value is None:
        # Read before the switch existed: the old three-way radio had no way to say "celebrate
        # but keep the letters still", so the legacy value only tells us whether *anything*
        # moved.
        return (cfg or {}).get('review_motion', 'full') != 'off'
    return bool(value)


def celebration_allowed(cfg):
    """Does the golden badge pop on a spelling that earned it? The switch the user asked for
    on 2026-11-04: 「在设置里增加开关是否使用弹出庆祝特效」."""
    value = (cfg or {}).get('review_motion_celebration')
    if value is None:
        return (cfg or {}).get('review_motion', 'full') != 'off'
    return bool(value)


def mode(cfg):
    """Legacy three-way reading, kept so an old saved value still means what it meant."""
    if not hop_allowed(cfg) and not celebration_allowed(cfg):
        return 'off'
    if hop_allowed(cfg) and celebration_allowed(cfg):
        return 'full'
    return 'calm'


def tier_for(question_mode, correct, incorrect_letters=0, hints=0, failed_checks=0, seconds=None):
    """Grade the spelling attempt into 1..4, or 0 for "do not celebrate".

    Every mode answered by typing letters into the shared boxes can celebrate: producing the
    spelling is the evidence, whether the prompt was the meaning, a blanked sentence or the
    audio. A choice card answered in 0.4 秒 is recognition, not spelling, and judgment is left
    out — with two options a fast right answer is a coin flip. A hint or a failed check drops
    to the gentlest tier no matter how fast it was, because the answer was helped.
    """
    if question_mode not in SPELLING_MODES or not correct:
        return 0
    if hints or failed_checks:
        return 4
    if incorrect_letters == 1:
        return 3
    if incorrect_letters >= 2:
        return 4
    if seconds is not None and seconds <= FAST_SECONDS:
        return 1
    return 2


def tier_caption(tier):
    return TIER_CAPTIONS.get(int(tier), '')


def shows_sparks(tier):
    """Deprecated name kept for the old timeline step; the rays live inside the badge now.

    The separate spark step was removed on 2026-11-04 when the celebration became one drawn
    object: eight clipart stars flying out of a pill was exactly the "cheap" the user
    rejected. What replaced them is the sunburst behind the word, which is `shows_rays`.
    """
    return int(tier) > 0


def shows_rays(tier):
    """The sunburst behind the word — every tier except the plainest.

    The user's rule from the earlier round still holds: the lowest tier must not be "no
    decoration at all", and here it still gets the extruded word, the ribbon and the gem.
    """
    return int(tier) <= 3


def shows_stars(tier):
    """The three-star cluster is for the two no-hint tiers only."""
    return int(tier) <= 2


def sparkle_count(tier):
    """Five glints on the top tier, three on the rest."""
    return 5 if int(tier) == 1 else 3


def shows_confetti(tier):
    """Paper for the two no-hint tiers.

    It used to be tier 1 alone, and tier 1 never fired in a day of real studying, so the
    festive half of the celebration was unreachable. 不错 — a hint was used — stays a pill.
    """
    return int(tier) in (1, 2)


def shows_celebration(tier, cfg=None):
    """Will the badge actually be drawn? `timeline` also carries the letter hop, which is a
    different switch — asking it "is there a celebration?" answered yes with no badge at all.
    """
    return int(tier) > 0 and celebration_allowed(cfg)


def timeline(tier, cfg=None):
    """The steps to play, as data: name, start offset, length, easing.

    Two independent switches, because that is what the settings page now offers: the letter
    hop is feedback while answering and the badge is the reward after it. Turning one off
    must not silently turn off the other — the old three-way radio could not express
    "letters still, badge on", which is what the learner asked for on 2026-11-04.

    Every step listed here is played by something. A `word` step (the answer word sliding up
    9px over 420ms) lived here for a day with no code reading it, and the tests asserted its
    presence as if that were behaviour — deleted on 2026-11-05 after the learner chose to
    keep the switches exhaustive rather than implement the missing motion.
    """
    if int(tier) <= 0:
        return []
    steps = []
    if hop_allowed(cfg):
        steps.append(dict(TIMING['letter'], name='letter'))
    if celebration_allowed(cfg):
        steps.append(dict(TIMING['badge'], name='badge'))
        if shows_confetti(tier):
            steps.append(dict(TIMING['confetti'], name='confetti'))
    return steps


def total_ms(tier, cfg=None):
    """When the last pixel of the celebration is gone — the ceiling for "never blocks Enter"."""
    return max((step['delay'] + step['duration'] for step in timeline(tier, cfg)),
               default=0)


# --- the badge's pose, as arithmetic the Qt layer only has to apply ---------------------
# Overshoot first, settle second: a game pop that goes straight to 1.0 looks like a dialog
# opening, and the reference assets all slam slightly past their resting size and come back.
POP_TARGET = 1.14
POP_START = 0.28
POP_BEND = 0.72
EXIT_GROW = 0.08
EXIT_TURN = 3.0
GLOW_REST = 0.55


def _ease_out(fraction):
    return 1.0 - (1.0 - fraction) ** 3


def _clamp(value):
    return max(0.0, min(1.0, value))


def badge_pose(progress, tier=2, duration=None):
    """Where the badge is at `progress` (0..1 through its own timeline).

    Returns plain numbers so the choreography is testable without a window: `scale`, `angle`,
    `opacity`, `glow`, `ribbon`, `twinkle`. The drawing layer must not invent any timing of
    its own.
    """
    step = TIMING['badge']
    total = duration or step['duration']
    entering = _clamp(progress * total / step['in_ms'])
    leaving = _clamp((progress * total - (step['in_ms'] + step['hold_ms'])) / step['out_ms'])
    if entering < POP_BEND:
        scale = POP_START + (POP_TARGET - POP_START) * _ease_out(entering / POP_BEND)
    else:
        scale = POP_TARGET - (POP_TARGET - 1.0) * _ease_out((entering - POP_BEND) /
                                                             (1.0 - POP_BEND))
    scale += EXIT_GROW * leaving
    angle = -14.0 * (1.0 - _ease_out(entering)) + EXIT_TURN * leaving
    opacity = min(1.0, entering * 2.6) * (1.0 - leaving)
    glow = max(GLOW_REST, 1.0 - 0.45 * _clamp((progress - 0.30) / 0.35))
    glow = glow * (1.0 - leaving)
    ribbon = _ease_out(_clamp((entering - 0.34) / 0.66)) * (1.0 - leaving)
    return {'scale': scale, 'angle': angle, 'opacity': opacity, 'glow': glow,
            'ribbon': ribbon, 'twinkle': _clamp(progress * 2.0), 'tier': int(tier)}


BADGE_CLEARANCE = 8        # px between the painted footprint and a row it must not touch
MIN_BADGE_FIT = 0.55       # shrinking below this stops reading as a celebration
CONFETTI_TOP_GAP = 12
CONFETTI_ENTRY = -24       # paper used to enter from above the card, unconditionally


def free_bands(card_height, rows):
    """The vertical gaps a badge may occupy, given rows it must not sit on."""
    bands = []
    cursor = 0
    for top, bottom in sorted(rows or ()):
        if top > cursor:
            bands.append((cursor, top))
        cursor = max(cursor, bottom)
    if card_height > cursor:
        bands.append((cursor, card_height))
    return bands


def badge_anchor(card_height, footprint, rows, clearance=BADGE_CLEARANCE):
    """Return (y, fit) so the badge's PAINTED footprint never sits on a protected row.

    The anchor used to be `card height × 0.50`, which knew nothing about where the word is.
    Measured on the real machine that left tier 3 clearing the answer word by 2 px and tier 4
    by 27 px — not a rule, an accident, and one content change away from covering the word.

    `footprint` is the height the celebration actually paints (glow, rays, stars and ribbon
    included — measured from `candy_badge.geometry`, not guessed from the font size), because
    the badge's own letters were never the widest part of it.

    When no band is tall enough, the badge shrinks instead of overlapping: covering the word
    that was just spelled correctly is the one thing this animation must not do.
    """
    bands = free_bands(card_height, rows)
    space, top, bottom = max(((b - t, t, b) for t, b in bands),
                             default=(card_height, 0, card_height))
    centre = (top + bottom) / 2.0
    if space >= footprint + 2 * clearance:
        return centre, 1.0
    return centre, max(MIN_BADGE_FIT, (space - 2 * clearance) / float(footprint))


def confetti_span(card_height, word_row_bottom):
    """Where the falling paper starts and how far it may fall.

    Paper used to enter at y = -24 no matter what, so on the two tiers that draw it it swept
    straight through the word being celebrated — 216 changed pixels per frame in the word
    row, on 38 of the day's 168 celebrations. It now begins below that row.
    """
    top = CONFETTI_ENTRY if word_row_bottom is None else max(
        CONFETTI_ENTRY, word_row_bottom + CONFETTI_TOP_GAP)
    return top, max(1, card_height - top)
