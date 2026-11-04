"""How loud Anki plays, for as long as this add-on is loaded.

Anki has no volume control: `aqt.sound` hands every clip to the bundled
`anki_audio/mpv.exe`, which mixes at 100% and stays there. The card's pronunciations are
therefore only reachable through that process, and there are two of them to deal with —
the persistent one Anki keeps open, and the per-file one it spawns from an argument list
it holds in memory. Both are set here, and neither change is written to disk: return the
dial to 100% and Anki's own command line is exactly what it was.

Measured against a -21.7 dBFS sample of the kind Anki's text-to-speech produces,
`--af-add=lavfi=[volume=2.50]` on this mpv is a clean x2.50 with nothing clipped. Above
unity the filter is paired with `alimiter`, so a loud file in someone else's deck cannot
be pushed into the ceiling; below unity it is left off, because a limiter on a signal
that never reaches the ceiling only adds latency.
"""

import ntpath

FLOOR = 50
CEILING = 300
NEUTRAL = 100
# The starting point for a profile that has never set this: Anki's own text-to-speech sits
# around -21 dBFS, which reads as quiet on a laptop, so the plug-in starts it +5 dB up.
DEFAULT = 180
# How deep the rendered word may be compressed. The loudness is carried by the presence
# band instead (`speech.boost_presence`): measured on this machine's own speech, drive 2.6
# was about 4 dB louder on average but the user's verdict was 好难听, while 1.4 stays
# transparent.
DRIVE_CEILING = 1.4
CEILING_LIMIT = '0.95'
ARGUMENT_PREFIX = '--af-add='
OUR_MARKER = 'volume='


def clamp(value):
    """The percentage to use, or the neutral one when the setting is nonsense."""
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return NEUTRAL
    return max(FLOOR, min(CEILING, number))


def gain_filter(value):
    """The mpv audio filter for a percentage, or None when nothing should change."""
    number = clamp(value)
    if number == NEUTRAL:
        return None
    gain = number / 100.0
    if gain > 1.0:
        return 'lavfi=[volume=%.2f,alimiter=limit=%s]' % (gain, CEILING_LIMIT)
    return 'lavfi=[volume=%.2f]' % gain


def is_ours(argument):
    """Tell our filter from Anki's own, so applying twice never stacks them."""
    return argument.startswith(ARGUMENT_PREFIX) and OUR_MARKER in argument


def mpv_args(args, value):
    """The command line for the next mpv Anki spawns."""
    kept = [argument for argument in args if not is_ours(argument)]
    spec = gain_filter(value)
    if spec:
        kept.append(ARGUMENT_PREFIX + spec)
    return kept


def af_changes(previous, value):
    """`change-list` edits for the mpv that is already running, as (operation, filter).

    The filter in force is removed before the new one goes on, even when the two are the
    same string: if Anki's process died and restarted in the meantime, the running one
    never got the filter and adding it again would be the only thing that fixes it.
    """
    changes = []
    if previous:
        changes.append(('-', previous))
    spec = gain_filter(value)
    if spec:
        changes.append(('+', spec))
    return changes


def is_mpv_argv(values):
    """True only for the command line that launches Anki's mpv.

    `SimpleProcessPlayer` declares `args = []` on the class and every TTS player inherits
    that one list, so an unguarded append would drop an mpv filter into a list that has
    nothing to do with mpv — and `MPVBase` keeps its own line in `argv`.
    """
    if not isinstance(values, list) or not values:
        return False
    first = ntpath.basename(str(values[0]).replace('/', '\\')).lower()
    return ntpath.splitext(first)[0] == 'mpv'


def render_drive(value):
    """How hard the rendered word is compressed for this percentage.

    Peak-normalising alone cannot beat a video: the word's own peaks are only ~20 dB above
    its average, so a linear gain runs out of headroom at about -21 dBFS RMS while a video
    sits near -16. Closing that gap needs compression, and compression costs naturalness —
    the user's verdict on the first attempt was 好难听. The ladder starts at 1.0 (no
    compression) and stops at `DRIVE_CEILING`, which is the point where a listener still
    hears a voice rather than a compressor; the cut-through comes from the presence lift in
    `speech.boost_presence`.
    """
    gain = clamp(value) / 100.0
    if gain <= 1.0:
        return 1.0
    return min(DRIVE_CEILING, 1.0 + (gain - 1.0) * 0.2)


def apply_volume(players, value, previous=None, live=True):
    """Put the gain on every mpv handle Anki exposes.

    Returns the filter now in force, the handles actually changed, one line per failure,
    and whether the running process refused a command. A player whose socket has gone away
    is a report, not a crash: settings still have to save, and the argument list is what
    the next spawn reads anyway — which is the lever that reaches the card's own audio.
    """
    spec = gain_filter(value)
    touched, errors, af_failed = [], [], False
    for player in players or []:
        name = type(player).__name__
        for attribute in ('args', 'argv'):
            values = getattr(player, attribute, None)
            if not is_mpv_argv(values):
                continue
            try:
                fresh = mpv_args(values, value)
                if fresh != values:
                    # In place: Anki keeps the same list object for its own future spawns.
                    values[:] = fresh
                    touched.append('%s.%s' % (name, attribute))
            except Exception as error:
                errors.append('%s.%s: %s' % (name, attribute, error))
        command = getattr(player, 'command', None)
        if live and callable(command):
            for operation, target in af_changes(previous, value):
                try:
                    command('change-list', 'af', operation, target)
                    touched.append('%s.af' % name)
                except Exception as error:
                    errors.append('%s.af %s %s: %s' % (name, operation, target, error))
                    af_failed = True
                    break
    return {'spec': spec, 'touched': touched, 'errors': errors, 'af_failed': af_failed}


def describe_players(players, tag):
    """One line per player: the rank it claims for this tag.

    The gain only reaches audio that mpv plays, so on a new machine the first thing to know
    is which player Anki actually picks for a word — SAPI speaks straight to the sound card
    and no filter of ours can touch it.
    """
    lines = []
    for player in players or []:
        rank = getattr(player, 'rank_for_tag', None)
        if not callable(rank):
            lines.append('%s=no-rank' % type(player).__name__)
            continue
        try:
            lines.append('%s=%s' % (type(player).__name__, rank(tag)))
        except Exception as error:
            lines.append('%s=error:%s' % (type(player).__name__, type(error).__name__))
    return ' '.join(lines)


class VolumeControl:
    """Remembers which filter is live, so the next change replaces it instead of stacking.

    Anki exposes no way to read its mpv filter list back, so the add-on keeps its own
    note of what it put there. Losing that note is not fatal — the worst case is one
    redundant `change-list` on a process that never had the filter.
    """

    def __init__(self):
        self.spec = None
        # This mpv (0.41) answers "error running command" to change-list on af, so the
        # running process is asked once per Anki session and then left alone; the argument
        # lists are what actually carry the gain for the clips the card plays.
        self.live = True

    def reset(self):
        """Forget what is live, because the process that carried it is gone.

        A fresh Anki session means a fresh mpv, so whether it takes commands is worth
        asking again rather than holding onto last session's answer.
        """
        self.spec = None
        self.live = True

    def set(self, players, value):
        applied = apply_volume(players, value, self.spec, live=self.live)
        self.spec = applied['spec']
        if applied['af_failed']:
            self.live = False
        return applied
