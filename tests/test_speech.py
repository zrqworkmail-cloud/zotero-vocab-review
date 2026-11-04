"""Why the 朗读音量 dial was silent, and the path that makes it audible.

The routing log from the real machine said `chosen=WindowsTTSPlayer`: Anki answers a word
with SAPI, which speaks straight to the sound card at the 100% it already uses. No mpv
filter can reach that, so the gain had nowhere to land. Rendering the same voice into a wav
and playing the wav through Anki's file player moves the word onto the mpv path — and these
tests pin the decision and the rendering without needing a speech engine.
"""

import array
import importlib.util
import math
import os
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'speech.py'
# Loaded as part of its package: the module reaches for `audio_volume` through a relative
# import, exactly as it does inside Anki.
PACKAGE = str(MODULE.parent)
package = types.ModuleType('zotero_global_capture')
package.__path__ = [PACKAGE]
sys.modules['zotero_global_capture'] = package
spec = importlib.util.spec_from_file_location('zotero_global_capture.speech', MODULE)
speech = importlib.util.module_from_spec(spec)
sys.modules['zotero_global_capture.speech'] = speech
spec.loader.exec_module(speech)


def quiet_word():
    """Peak -18.9 dBFS, RMS -40.4 dBFS — the shape of the real SAPI output on this machine."""
    return [int(3815 * math.sin(i / 2.7) * math.exp(-(i % 2205) / 60.0)) for i in range(22050)]


def tone(frequency, rate=22050, amplitude=4000, seconds=0.5):
    return array.array('h', [int(amplitude * math.sin(2 * math.pi * frequency * i / rate))
                             for i in range(int(rate * seconds))])


def band_magnitude(samples, frequency, rate=22050):
    real = sum(x * math.cos(2 * math.pi * frequency * i / rate) for i, x in enumerate(samples))
    imag = sum(x * math.sin(2 * math.pi * frequency * i / rate) for i, x in enumerate(samples))
    return math.hypot(real, imag)


def band_change_db(before, after, frequency, rate=22050):
    return 20 * math.log10(max(band_magnitude(after, frequency, rate), 1) /
                           max(band_magnitude(before, frequency, rate), 1))


class Speaker:
    """A player that owns a sound card handle — Anki's SAPI player."""

    def __init__(self):
        self.speaker = object()


class MpvPlayer:
    """A player that hands the file to mpv."""


class Slots(unittest.TestCase):
    def test_the_wav_names_rotate_inside_a_small_fixed_pool(self):
        first = speech.slot_path(0)
        self.assertTrue(first.endswith('.wav'))
        self.assertTrue(os.path.isabs(first))
        self.assertEqual(speech.slot_path(speech.SLOTS), first)
        self.assertEqual(len(set(speech.slot_paths(speech.SLOTS))), speech.SLOTS)
        self.assertEqual(speech.slot_paths(3), [speech.slot_path(0), speech.slot_path(1), speech.slot_path(2)])


class Routing(unittest.TestCase):
    def test_only_a_player_with_a_speaker_bypasses_the_filter(self):
        self.assertTrue(speech.speaks_directly(Speaker()))
        self.assertFalse(speech.speaks_directly(MpvPlayer()))
        self.assertFalse(speech.speaks_directly(None))

    def test_the_dial_only_forces_a_render_when_it_is_not_neutral_and_sapi_has_the_word(self):
        flat = lambda volume: None if volume == 100 else 'lavfi=[volume=1.8]'
        self.assertFalse(speech.needs_file_speech(100, Speaker(), gain_filter=flat))
        self.assertTrue(speech.needs_file_speech(180, Speaker(), gain_filter=flat))
        self.assertFalse(speech.needs_file_speech(180, MpvPlayer(), gain_filter=flat))


class AvPlayer:
    def __init__(self, chosen):
        self.chosen = chosen
        self.queued = []

    def _best_player_for_tag(self, tag):
        return self.chosen

    def play_tags(self, tags):
        self.queued.append(list(tags))


class Taskman:
    def __init__(self):
        self.jobs = []

    def run_in_background(self, fn, on_done=None):
        self.jobs.append((fn, on_done))


class Future:
    def __init__(self, value=None, error=None):
        self.value, self.error = value, error

    def result(self):
        if self.error is not None:
            raise self.error
        return self.value


class Speaking(unittest.TestCase):
    def tag(self, text):
        return types.SimpleNamespace(text=text)

    def test_a_neutral_dial_leaves_anki_s_own_path_alone(self):
        player, taskman = AvPlayer(Speaker()), Taskman()
        self.assertTrue(speech.speak(player, taskman, ['one', 'two'], 100, self.tag))
        self.assertEqual([[tag.text for tag in queued] for queued in player.queued], [['one', 'two']])
        self.assertEqual(taskman.jobs, [])

    def test_a_player_that_already_uses_mpv_needs_no_rendering(self):
        player, taskman = AvPlayer(MpvPlayer()), Taskman()
        self.assertTrue(speech.speak(player, taskman, ['one'], 240, self.tag))
        self.assertEqual(taskman.jobs, [])
        self.assertEqual(len(player.queued), 1)

    def test_sapi_with_a_gain_renders_off_the_ui_thread_then_queues_the_files(self):
        player, taskman = AvPlayer(Speaker()), Taskman()
        paths = ['/a.wav', '/b.wav']
        # The job is never run here — win32com lives inside Anki — so the callback is
        # driven directly with the future Anki would hand back.
        self.assertTrue(speech.speak(player, taskman, ['one', 'two'], 240, self.tag))
        self.assertEqual(len(taskman.jobs), 1)
        self.assertEqual(player.queued, [], 'nothing may be spoken before the wav exists')

        class FileTag:
            def __init__(self, filename):
                self.filename = filename

        sys.modules['anki'] = types.ModuleType('anki')
        sys.modules['anki.sound'] = types.ModuleType('anki.sound')
        sys.modules['anki.sound'].SoundOrVideoTag = FileTag
        try:
            taskman.jobs[0][1](Future(value=paths))
        finally:
            del sys.modules['anki'], sys.modules['anki.sound']
        self.assertEqual([[tag.filename for tag in batch] for batch in player.queued], [paths])

    def test_a_render_that_lands_after_the_next_card_was_shown_says_nothing(self):
        player, taskman = AvPlayer(Speaker()), Taskman()
        stale = [False]
        speech.speak(player, taskman, ['one'], 240, self.tag, is_stale=lambda: stale[0])
        stale[0] = True
        taskman.jobs[0][1](Future(value=['/a.wav']))
        self.assertEqual(player.queued, [])

    def test_a_failed_render_is_reported_to_the_caller(self):
        player, taskman = AvPlayer(Speaker()), Taskman()
        seen = []
        speech.speak(player, taskman, ['one'], 240, self.tag, on_error=seen.append)
        taskman.jobs[0][1](Future(error=RuntimeError('no speech engine')))
        self.assertEqual([str(error) for error in seen], ['no speech engine'])

    def test_nothing_to_say_is_not_a_request(self):
        player, taskman = AvPlayer(Speaker()), Taskman()
        self.assertFalse(speech.speak(player, taskman, ['', None], 240, self.tag))
        self.assertEqual(taskman.jobs, [])
        self.assertEqual(player.queued, [])


class DispatchRecorder:
    def __init__(self):
        self.created = []
        self.voices = []
        self.streams = []

    def __call__(self, name):
        obj = types.SimpleNamespace(name=name, calls=[], closed=False)
        self.created.append(obj)
        if name == speech.SAPI_VOICE:
            self.voices.append(obj)
        else:
            self.streams.append(obj)
        if name == speech.SAPI_FILE_STREAM:
            obj.Open = lambda path, mode: obj.calls.append(('open', path, mode))
            obj.Close = lambda: setattr(obj, 'closed', True)
        if name == speech.SAPI_VOICE:
            obj.Speak = lambda text: obj.calls.append(('speak', text))
        return obj


class Rendering(unittest.TestCase):
    def test_a_word_is_spoken_into_a_file_stream_and_the_stream_is_closed(self):
        dispatch = DispatchRecorder()
        path = speech.render_one('increase', '/tmp/x.wav', dispatch)
        self.assertEqual(path, '/tmp/x.wav')
        self.assertEqual(dispatch.voices[0].calls, [('speak', 'increase')])
        self.assertIs(dispatch.voices[0].AudioOutputStream, dispatch.streams[0])
        self.assertEqual(dispatch.streams[0].calls,
                         [('open', '/tmp/x.wav', speech.SSFM_CREATE_FOR_WRITE)])
        self.assertTrue(dispatch.streams[0].closed)

    def test_blank_text_is_not_rendered_at_all(self):
        dispatch = DispatchRecorder()
        self.assertIsNone(speech.render_one('   ', '/tmp/x.wav', dispatch))
        self.assertEqual(dispatch.created, [])

    def test_a_shared_voice_is_reused_instead_of_dispatching_one_per_word(self):
        # Creating a SpVoice costs a COM round trip; Anki's own player keeps one for the
        # same reason. Paths are passed in: the rotating slots are real files in the user's
        # temp folder, and a test must not rewrite them.
        directory = tempfile.mkdtemp()
        paths = [os.path.join(directory, 'one.wav'), os.path.join(directory, 'two.wav')]
        voice = types.SimpleNamespace(AudioOutputStream=None, Speak=lambda text: None)
        seen = []
        voice.Speak = lambda text: seen.append(text)
        written = speech.render_all(['one', 'two'], DispatchRecorder(), voice=voice, paths=paths)
        self.assertEqual(seen, ['one', 'two'])
        self.assertEqual(written, paths)

    def test_render_all_skips_empties_and_keeps_the_order(self):
        directory = tempfile.mkdtemp()
        paths = [os.path.join(directory, 'first.wav'), os.path.join(directory, 'second.wav')]
        written = speech.render_all(['first', '', None, 'second'], DispatchRecorder(), paths=paths)
        self.assertEqual(written, paths)


class Playback(unittest.TestCase):
    def test_files_are_queued_as_file_tags(self):
        # SoundOrVideoTag is what makes av_player choose the mpv path, so the queue has to
        # be built from it rather than from a path list.
        tags = types.ModuleType('anki.sound')

        class SoundOrVideoTag:
            def __init__(self, filename):
                self.filename = filename

        tags.SoundOrVideoTag = SoundOrVideoTag
        anki = types.ModuleType('anki')
        anki.sound = tags
        sys.modules['anki'], sys.modules['anki.sound'] = anki, tags
        try:
            played = []
            player = types.SimpleNamespace(play_tags=lambda built: played.append([t.filename for t in built]))
            speech.play_tags(player, ['/a.wav', '/b.wav'])
            self.assertEqual(played, [['/a.wav', '/b.wav']])
        finally:
            del sys.modules['anki'], sys.modules['anki.sound']


class Amplifying(unittest.TestCase):
    """The loudness stage, pinned with the numbers measured on this machine's own output.

    SAPI renders a word at peak -18.7 dBFS and RMS -39.1 dBFS. A video sits near RMS -16, so
    the word is about twenty decibels under it — which is why a ×3 gain on the player still
    sounded quiet. Peak-normalising plus a soft-knee bend closes that gap without clipping.
    """

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.path = os.path.join(self.directory, 'word.wav')

    def write(self, samples, channels=1, rate=22050):
        with wave.open(self.path, 'wb') as reader:
            reader.setnchannels(channels)
            reader.setsampwidth(2)
            reader.setframerate(rate)
            reader.writeframes(array.array('h', samples).tobytes())

    def read(self):
        with wave.open(self.path, 'rb') as reader:
            samples = array.array('h')
            samples.frombytes(reader.readframes(reader.getnframes()))
            return samples, reader.getnchannels(), reader.getframerate()

    @staticmethod
    def db(points):
        peak = max(abs(min(points)), abs(max(points)))
        rms = math.sqrt(sum(value * value for value in points) / len(points))
        return (20 * math.log10(max(peak, 1) / 32767.0), 20 * math.log10(max(rms, 1) / 32767.0),
                sum(1 for value in points if abs(value) >= 32700))

    def quiet_word(self):
        return quiet_word()

    def test_a_quiet_word_rises_by_more_than_fifteen_decibels_and_never_clips(self):
        self.write(self.quiet_word())
        before = self.db(self.read()[0])
        self.assertTrue(speech.amplify_file(self.path))
        samples, _channels, _rate = self.read()
        peak, rms, clipped = self.db(samples)
        self.assertGreater(before[0], -20.0, 'the fixture should look like the real SAPI output')
        self.assertLess(before[1], -34.0, 'the fixture should look like the real SAPI output')
        self.assertLessEqual(peak, -0.1)
        self.assertGreater(peak, -3.0, 'the word should end up nearly full scale, got %.1f dBFS' % peak)
        self.assertGreaterEqual(rms, before[1] + 15.0,
                                'average only rose %.1f dB' % (rms - before[1]))
        self.assertEqual(clipped, 0, 'a soft knee must not push any sample onto the rail')

    def test_amplifying_twice_does_not_stack_into_distortion(self):
        self.write(self.quiet_word())
        speech.amplify_file(self.path)
        once = self.db(self.read()[0])
        speech.amplify_file(self.path)
        twice = self.db(self.read()[0])
        self.assertLess(abs(twice[0] - once[0]), 1.0, (once, twice))
        self.assertLessEqual(twice[0], -0.1)
        self.assertEqual(twice[2], 0)

    def test_stereo_and_sample_rate_survive_the_pass(self):
        samples = self.quiet_word() * 2
        self.write(samples, channels=2, rate=44100)
        self.assertTrue(speech.amplify_file(self.path))
        _data, channels, rate = self.read()
        self.assertEqual((channels, rate), (2, 44100))

    def test_a_file_that_is_not_readable_pcm_is_left_exactly_as_it_was(self):
        # A failed loudness pass must not become silence: SAPI's own output still plays.
        with open(self.path, 'wb') as handle:
            handle.write(b'not a wav at all')
        self.assertFalse(speech.amplify_file(self.path))
        with open(self.path, 'rb') as handle:
            self.assertEqual(handle.read(), b'not a wav at all')

    def test_silence_is_not_amplified_into_noise(self):
        self.write([0] * 4410)
        self.assertTrue(speech.amplify_file(self.path))
        self.assertEqual(max(abs(value) for value in self.read()[0]), 0)

    def test_rendering_amplifies_what_it_writes(self):
        class Voice:
            AudioOutputStream = None

            def Speak(self, text):
                with wave.open(self.path, 'wb') as reader:
                    reader.setnchannels(1)
                    reader.setsampwidth(2)
                    reader.setframerate(22050)
                    reader.writeframes(array.array('h', quiet_word()).tobytes())

        def dispatch(name):
            return types.SimpleNamespace(Open=lambda *a: None, Close=lambda: None)

        voice = Voice()
        voice.path = self.path
        self.write(self.quiet_word())
        before = self.db(self.read()[0])
        speech.render_one('increase', self.path, dispatch, voice=voice)
        self.assertGreater(self.db(self.read()[0])[1], before[1] + 15.0)


    def test_the_dial_buys_average_loudness_without_pinning_any_sample(self):
        # What the ladder in `audio_volume.render_drive` is for: 1.0 is a plain level change,
        # each step above it raises the average, and none of them reach a clipped sample.
        samples = quiet_word()
        gentle = speech.amplify(samples, drive=1.0)
        loud = speech.amplify(samples, drive=2.6)
        self.assertGreater(self.db(loud)[1], self.db(gentle)[1] + 4.0,
                           'the dial should be worth at least 4 dB of average')
        self.assertLessEqual(self.db(loud)[0], -0.1)
        self.assertEqual(self.db(loud)[2], 0)
        self.assertEqual(self.db(gentle)[2], 0)


class Presence(unittest.TestCase):
    """Lifting the band the ear reads consonants from, instead of squashing the whole word.

    The user's complaint about the deep version was 好难听, and the goal was never more
    overall level — it was hearing the word *over* a video. Speech intelligibility against
    background sound lives around 2–4 kHz, so that is what gets the gain.
    """

    def test_the_presence_band_is_lifted_while_a_low_tone_is_left_alone(self):
        bright = speech.boost_presence(tone(3000), 22050)
        self.assertGreater(band_change_db(tone(3000), bright, 3000), 3.5,
                           'the 3 kHz band should come up by at least 3.5 dB')
        low = speech.boost_presence(tone(200), 22050)
        self.assertLess(abs(band_change_db(tone(200), low, 200)), 1.5,
                        'the bass should not be pumped along with it')

    def test_no_sample_leaves_the_signed_sixteen_bit_range(self):
        out = speech.boost_presence(tone(3000, amplitude=30000), 22050)
        self.assertTrue(all(-32767 <= value <= 32767 for value in out))
        self.assertEqual(len(out), len(tone(3000, amplitude=30000)))

    def test_an_empty_or_zero_signal_comes_back_unchanged(self):
        self.assertEqual(list(speech.boost_presence(array.array('h'), 22050)), [])
        zeros = array.array('h', [0] * 500)
        self.assertEqual(list(speech.boost_presence(zeros, 22050)), [0] * 500)

    def test_the_rendered_word_ends_up_brighter_than_it_came_in(self):
        # 200 Hz + 3 kHz together: after the whole chain the 3 kHz part must dominate more
        # than it did, and the overall level must not have been pushed into the rail.
        mixed = array.array('h', [int(2500 * math.sin(2 * math.pi * 200 * i / 22050) +
                                      1200 * math.sin(2 * math.pi * 3000 * i / 22050))
                                  for i in range(22050)])
        path = os.path.join(tempfile.mkdtemp(), 'mixed.wav')
        with wave.open(path, 'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(22050)
            handle.writeframes(mixed.tobytes())
        before = band_change_db(mixed, mixed, 3000) - band_change_db(mixed, mixed, 200)
        speech.amplify_file(path, drive=1.4)
        with wave.open(path, 'rb') as handle:
            after = array.array('h')
            after.frombytes(handle.readframes(handle.getnframes()))
        ratio_before = 20 * math.log10(max(band_magnitude(mixed, 3000), 1) /
                                       max(band_magnitude(mixed, 200), 1))
        ratio_after = 20 * math.log10(max(band_magnitude(after, 3000), 1) /
                                      max(band_magnitude(after, 200), 1))
        self.assertGreater(ratio_after, ratio_before + 3.0,
                           'the word should read brighter, not just louder')
        self.assertLess(max(abs(min(after)), abs(max(after))), 32767)


    def test_the_bass_tilt_lets_the_bass_down_and_leaves_the_highs_alone(self):
        low = speech.trim_bass(tone(200), 22050)
        self.assertLess(band_change_db(tone(200), low, 200), -3.0,
                        'video and music carry their energy down here, so the word should give way')
        high = speech.trim_bass(tone(3000), 22050)
        self.assertLess(abs(band_change_db(tone(3000), high, 3000)), 1.0,
                        'the presence band must not be dragged down with the bass')

    def test_the_chain_buys_presence_relative_to_bass_without_pinning_anything(self):
        mixed = tone(200, amplitude=2600, seconds=0.4) + tone(3000, amplitude=900, seconds=0.4)
        shaped = speech.amplify(speech.trim_bass(speech.boost_presence(mixed, 22050), 22050),
                                drive=1.4)
        before = band_magnitude(mixed, 3000) / max(band_magnitude(mixed, 200), 1)
        after = band_magnitude(shaped, 3000) / max(band_magnitude(shaped, 200), 1)
        self.assertGreater(20 * math.log10(after / before), 6.0)
        self.assertLess(max(abs(min(shaped)), abs(max(shaped))), 32767)


if __name__ == '__main__':
    unittest.main()
