"""Which spelling performance earns which motion — and how long it is allowed to take.

The user approved this on 2026-11-04 from the mockup (`design/spelling-motion-mockup.html`):
letters hop into their boxes, the answer word pops, and a badge celebrates at one of four
tiers. Two things were decided against the mockup and are recorded here so they do not creep
back: the badge words are **Chinese** (an English shout printed on a study card reads as a
game show), and the top tier **no longer shakes the whole card** (±2px on the dark card looked
like a rendering fault).

Keeping the decisions in plain arithmetic means the complaints a user can actually make —
"too flashy", "it blocked my Enter" — are testable without a window. The Qt layer only plays
what `timeline()` returns.
"""

FAST_SECONDS = 6.0
# The three question types that are answered by typing letters into the shared boxes. The
# celebration used to cover `typing` only, which meant a cloze card hopped every letter and
# then said nothing — and in a whole day of real studying that scope produced 6 celebrations
# out of 134 cards (2026-11-04), which is why the user asked for it to be widened.
SPELLING_MODES = ('typing', 'cloze', 'listening')
MODES = ('full', 'calm', 'off')
DEFAULT_MODE = 'full'

TIER_LABELS = {1: '不可思议', 2: '完美', 3: '很棒', 4: '不错'}
TIER_CAPTIONS = {1: 'UNBELIEVABLE', 2: 'PERFECT', 3: 'GREAT', 4: 'NICE'}

# Milliseconds lifted from the approved timing table. The badge is the spine of the sequence
# (260 in + 520 hold + 200 out = 980) and everything else is scheduled to finish inside it,
# which is what keeps the whole celebration under one second and off the paging path.
TIMING = {
    'letter': {'delay': 0, 'duration': 180, 'easing': 'OutBack', 'rise': 11},
    'slip': {'delay': 0, 'duration': 220, 'swing': 5},
    'word': {'delay': 60, 'duration': 420, 'easing': 'OutBack', 'rise': 9},
    'badge': {'delay': 0, 'duration': 980, 'in_ms': 260, 'hold_ms': 520, 'out_ms': 200,
              'easing': 'OutBack'},
    'sparks': {'delay': 100, 'duration': 500, 'count': 8},
    'confetti': {'delay': 80, 'duration': 900, 'count': 14},
}


def mode(cfg):
    """The user's choice: full / calm / off, defaulting to the approved full motion."""
    value = (cfg or {}).get('review_motion')
    return value if value in MODES else DEFAULT_MODE


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


def tier_label(tier):
    return TIER_LABELS.get(int(tier), '')


def tier_caption(tier):
    return TIER_CAPTIONS.get(int(tier), '')


def shows_sparks(tier):
    """Rays for anything that was spelled out cleanly enough to be worth a second look."""
    return int(tier) in (1, 2, 3)


def shows_confetti(tier):
    """Paper for the two no-hint tiers.

    It used to be tier 1 alone, and tier 1 never fired in a day of real studying, so the
    festive half of the celebration was unreachable. 不错 — a hint was used — stays a pill.
    """
    return int(tier) in (1, 2)


def shows_celebration(tier, setting_mode=None):
    return int(tier) > 0 and (setting_mode or DEFAULT_MODE) != 'off'


def timeline(tier, setting_mode=None):
    """The steps to play, as data: name, start offset, length, easing.

    `calm` keeps the two steps that carry information — the letter landing and the badge —
    and drops the two that are decoration. `off` returns nothing, and the caller must not
    create any animation at all.
    """
    setting_mode = setting_mode or DEFAULT_MODE
    if setting_mode == 'off' or int(tier) <= 0:
        return []
    steps = [dict(TIMING['letter'], name='letter'), dict(TIMING['word'], name='word'),
             dict(TIMING['badge'], name='badge')]
    if setting_mode == 'full':
        if shows_sparks(tier):
            steps.append(dict(TIMING['sparks'], name='sparks'))
        if shows_confetti(tier):
            steps.append(dict(TIMING['confetti'], name='confetti'))
    return steps


def total_ms(tier, setting_mode=None):
    """When the last pixel of the celebration is gone — the ceiling for "never blocks Enter"."""
    return max((step['delay'] + step['duration'] for step in timeline(tier, setting_mode)),
               default=0)
