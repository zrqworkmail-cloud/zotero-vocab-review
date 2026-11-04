"""Say a word loudly enough by letting mpv be the one that says it.

Anki picks its SAPI player for a word on this machine — the add-on's own routing log says
`chosen=WindowsTTSPlayer`, and the file-based WinRT player reports no voices here. SAPI
speaks straight to the sound card, so no filter of ours can touch it, and its own volume
tops out at the 100% it already uses. That is why the 朗读音量 dial did nothing.

Rendering the same voice into a wav and handing the wav to Anki's file player puts the word
back on the one path where the dial has effect: `av_player` → `SoundOrVideoTag` →
`SimpleMpvPlayer`, which is the process that carries our gain filter.
"""

import array
import math
import os
import tempfile
import wave

# The SAPI file stream mode that creates (and overwrites) the destination.
SSFM_CREATE_FOR_WRITE = 3
SAPI_VOICE = 'SAPI.SpVoice'
SAPI_FILE_STREAM = 'SAPI.SpFileStream'
# A small rotating pool rather than a new file per word: the queue may still be holding the
# paths of the examples it has not spoken yet, and a card flip can only get so far ahead.
SLOTS = 8

# Measured on this machine's own output: SAPI renders a word at peak -18.7 dBFS and
# RMS -39.1 dBFS, while a video sits near RMS -16. A fixed gain cannot close twenty decibels
# without clipping, so the rendering stage peak-normalises first and then bends the curve with
# `tanh`, which raises the average without a single clipped sample. The bend (`drive`) comes
# from the dial — see `audio_volume.render_drive`: the first attempt used a fixed 3.0 and the
# user's verdict was 好难听, so loudness is now something the dial asks for, not a given.
TARGET_PEAK = 0.95
# Speech intelligibility over background sound lives around 2–4 kHz — that is where
# consonants are read. Lifting that band costs far less perceived quality than pushing the
# whole word through a compressor, which is what the user objected to (好难听). A peaking
# biquad (RBJ cookbook) touches that band and leaves the bass alone.
PRESENCE_HZ = 2800.0
PRESENCE_DB = 8.0
PRESENCE_Q = 0.8
# And a little room is made underneath it: video and music carry most of their energy below
# 250 Hz, so giving up the word's own rumble buys clarity at the same overall level. Measured
# on this machine's own speech with these numbers: the presence band comes up ~10 dB against
# the bass, nothing is pinned to the rail, and 1 kHz upward is left within 1 dB.
BASS_CUTOFF_HZ = 180.0


def trim_bass(samples, rate, cutoff=BASS_CUTOFF_HZ):
    """Two cascaded one-pole high-passes: give way below `cutoff`, change nothing above it.

    A shelf formula was the first attempt and tilted the wrong end of the spectrum; this
    version is two of the simplest filters there are, and it is measured to leave 1 kHz and
    up within a decibel while taking 5-8 dB out of the 100-200 Hz region a video already
    occupies.
    """
    if not samples or cutoff <= 0:
        return samples
    a = math.exp(-2 * math.pi * cutoff / rate)
    out = array.array('h')
    x1 = y1 = y2 = x2 = 0.0
    for value in samples:
        x = float(value)
        y1 = a * (y1 + x - x1)
        x1 = x
        y2 = a * (y2 + y1 - x2)
        x2 = y1
        out.append(-32767 if y2 < -32767 else (32767 if y2 > 32767 else int(round(y2))))
    return out


def peaking_coefficients(rate, center, db, q):
    """(b, a) for an RBJ peaking filter, normalised so a0 is 1."""
    w0 = 2 * math.pi * center / rate
    alpha = math.sin(w0) / (2 * q)
    amplitude = 10 ** (db / 40.0)
    b0, b1, b2 = 1 + alpha * amplitude, -2 * math.cos(w0), 1 - alpha * amplitude
    a0, a1, a2 = 1 + alpha / amplitude, -2 * math.cos(w0), 1 - alpha / amplitude
    return (b0 / a0, b1 / a0, b2 / a0), (a1 / a0, a2 / a0)


def boost_presence(samples, rate, center=PRESENCE_HZ, db=PRESENCE_DB, q=PRESENCE_Q):
    """Raise the band the ear reads consonants from, and leave the rest of the voice alone.

    Clamped to the signed 16-bit range: a biquad can ring above full scale on a hot input,
    and a wrapped sample is a click.
    """
    if not samples or not db:
        return samples
    (b0, b1, b2), (a1, a2) = peaking_coefficients(rate, center, db, q)
    out = array.array('h')
    x1 = x2 = y1 = y2 = 0.0
    for value in samples:
        x = float(value)
        y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x
        y2, y1 = y1, y
        out.append(-32767 if y < -32767 else (32767 if y > 32767 else int(round(y))))
    return out


def amplify(samples, target_peak=TARGET_PEAK, drive=1.0):
    """Push 16-bit samples toward full scale without ever pinning one to the rail.

    The loudest peak is scaled to `target_peak`, then the whole curve is opened with
    `abs(u) ** (1/drive)`: `drive` 1.0 is exactly the identity — a plain level change, as
    transparent as it gets — and every step above it lifts the quiet middle while pinning
    nothing, because the curve is static. A feedback compressor would pump the background
    between syllables, which is the sound the user rejected.
    """
    if not samples:
        return samples
    peak = max(abs(min(samples)), abs(max(samples)))
    if peak <= 0:
        return samples
    ceiling = 32767.0 * target_peak
    scale = ceiling / peak
    exponent = 1.0 / max(drive, 1.0)
    out = array.array('h')
    for value in samples:
        unit = value * scale / ceiling
        out.append(max(-32767, min(32767, int(round(ceiling * math.copysign(abs(unit) ** exponent, unit))))))
    return out


def amplify_file(path, target_peak=TARGET_PEAK, drive=1.0):
    """Rewrite a rendered wav brighter and louder; True when it changed something.

    Presence first, level second: normalising after the lift keeps the peak where it was,
    so the word gains cut-through without gaining overall level. A file that cannot be read
    back (or is not 16-bit PCM) is left exactly as SAPI wrote it — a failed loudness pass
    must not turn into silence.
    """
    try:
        with wave.open(path, 'rb') as reader:
            channels = reader.getnchannels()
            rate = reader.getframerate()
            if reader.getsampwidth() != 2:
                return False
            samples = array.array('h')
            samples.frombytes(reader.readframes(reader.getnframes()))
    except Exception:
        return False
    try:
        louder = amplify(trim_bass(boost_presence(samples, rate), rate), target_peak, drive)
        with wave.open(path, 'wb') as writer:
            writer.setnchannels(channels)
            writer.setsampwidth(2)
            writer.setframerate(rate)
            writer.writeframes(louder.tobytes())
    except Exception:
        return False
    return True


def slot_path(index):
    """One of a fixed set of wav names, so nothing piles up in the temp folder."""
    return os.path.join(tempfile.gettempdir(), 'zvr-speech-%d.wav' % (index % SLOTS))


def slot_paths(count):
    return [slot_path(index) for index in range(count)]


def speaks_directly(player):
    """True for a player that puts sound on the sound card itself.

    Duck-typed on purpose: Anki's SAPI player carries a `speaker` (a `SAPI.SpVoice`), and
    that is exactly the case where a volume filter on mpv cannot reach anything.
    """
    return getattr(player, 'speaker', None) is not None


def needs_file_speech(volume, chosen_player, gain_filter=None):
    """Whether the word has to be rendered to a file for the dial to mean anything.

    `chosen_player` is whatever Anki would use for this tag — asking it is a pure lookup
    (`AVPlayer._best_player_for_tag`), so this costs nothing and never plays anything. At
    100% the answer is always no: the dial then promises to leave Anki alone, and Anki's own
    path is the one that needs no work.
    """
    if gain_filter is None:
        from . import audio_volume
        gain_filter = audio_volume.gain_filter
    if gain_filter(volume) is None:
        return False
    return speaks_directly(chosen_player)


def render_one(text, path, dispatch, voice=None, drive=1.0):
    """Speak `text` into `path` as a wav, using a voice from `dispatch` or `voice`.

    `dispatch` is injected so this can be tested without a speech engine: it is
    `win32com.client.Dispatch` in Anki, and a recorder in the tests.
    """
    text = str(text or '').strip()
    if not text:
        return None
    voice = voice if voice is not None else dispatch(SAPI_VOICE)
    stream = dispatch(SAPI_FILE_STREAM)
    stream.Open(path, SSFM_CREATE_FOR_WRITE)
    voice.AudioOutputStream = stream
    try:
        voice.Speak(text)
    finally:
        stream.Close()
    amplify_file(path, drive=drive)
    return path


def render_all(texts, dispatch, voice=None, paths=None, drive=1.0):
    """Render a list of texts; returns the wav paths, in order, skipping empty ones."""
    wanted = [str(text or '').strip() for text in (texts or []) if str(text or '').strip()]
    paths = paths if paths is not None else slot_paths(len(wanted))
    written = []
    for text, path in zip(wanted, paths):
        if render_one(text, path, dispatch, voice=voice, drive=drive):
            written.append(path)
    return written


def play_tags(av_player, paths):
    """Queue rendered wavs through Anki's own file player, so mpv carries the gain."""
    from anki.sound import SoundOrVideoTag
    av_player.play_tags([SoundOrVideoTag(filename=path) for path in paths])
    return paths


def speak(av_player, taskman, texts, volume, tag_factory, on_error=None, is_stale=None,
          gain_filter=None):
    """Say the texts at the dialled gain, choosing the route that makes the gain real.

    At 100% (or whenever Anki already answers a word through mpv) this is just
    `play_tags`. When SAPI would speak it straight to the sound card, the same voice is
    rendered into a wav on a worker thread and the wav goes through the file player —
    rendering a queue of sentences on the UI thread would freeze the card.

    `is_stale` is the caller's way of saying "this request no longer belongs on screen"; a
    render that lands after the next card was shown must not speak the older word.
    """
    wanted = [str(text)[:500] for text in (texts or []) if text]
    if not wanted:
        return False
    if gain_filter is None:
        from . import audio_volume
        gain_filter = audio_volume.gain_filter
    if gain_filter(volume) is None:
        # 100% promises to leave Anki alone, so ask nothing of it beyond the usual play.
        av_player.play_tags([tag_factory(text) for text in wanted])
        return True
    chosen = av_player._best_player_for_tag(tag_factory(wanted[0]))
    if not speaks_directly(chosen):
        av_player.play_tags([tag_factory(text) for text in wanted])
        return True

    def render():
        import win32com.client
        from . import audio_volume
        return render_all(wanted, win32com.client.Dispatch,
                          drive=audio_volume.render_drive(volume))

    def spoken(future):
        if is_stale is not None and is_stale():
            return
        try:
            play_tags(av_player, future.result())
        except Exception as error:
            if on_error is not None:
                on_error(error)

    taskman.run_in_background(render, on_done=spoken)
    return True
