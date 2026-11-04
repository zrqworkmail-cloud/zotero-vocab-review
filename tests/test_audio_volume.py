"""The card's pronunciations are too quiet, and Anki has no volume control of its own.

Disassembly of this Anki build settled the route before these tests were written: a
TTSTag is answered by WindowsRTTTSFilePlayer (SAPI's player carries default_rank -1, so
the WinRT voice wins), that player writes tts.wav with the Rust backend and hands it back
with av_player.insert_file(), and every file Anki plays goes to the bundled
`anki_audio/mpv.exe`. Measured against a -21.7 dBFS TTS-like sample, that mpv applies
`--af-add=lavfi=[volume=2.50]` as exactly x2.50 RMS with nothing clipped, and keeps
`alimiter` out of the way until a peak actually reaches the ceiling.

So the one knob that reaches a pronunciation is a filter on that mpv, and it has to be
put there twice: on the argument list used for the next spawned process, and on the
process that is already running.
"""

import importlib.util
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'audio_volume.py'
spec = importlib.util.spec_from_file_location('audio_volume', MODULE)
volume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(volume)


# Exactly what Anki launches today, read off the live process: its own apad filter must
# survive every change we make, because it is what stops the tail of a clip being cut.
ANKI_ARGS = ['mpv.exe', '--idle', '--no-terminal', '--force-window=no', '--ontop',
             '--audio-display=no', '--keep-open=no', '--autoload-files=no', '--gapless-audio=no',
             '--af-add=lavfi=[apad=pad_dur=0.150]', '--no-ytdl', '--input-media-keys=no',
             '--config-dir=C:/Users/Admin/AppData/Roaming/Anki2']


class SpawningPlayer:
    """Anki's per-file mpv: it only ever gets the filter through its argument list."""

    def __init__(self, args=None):
        self.args = list(ANKI_ARGS if args is None else args)


class LivePlayer(SpawningPlayer):
    """Anki's persistent mpv: it also takes commands over its IPC socket."""

    def __init__(self, args=None, fail=False):
        SpawningPlayer.__init__(self, args)
        self.sent = []
        self.fail = fail

    def command(self, *parts):
        if self.fail:
            raise RuntimeError('mpv is not running')
        self.sent.append(parts)


class Clamping(unittest.TestCase):
    def test_hundred_percent_is_the_one_setting_that_changes_nothing(self):
        self.assertIsNone(volume.gain_filter(100))
        self.assertIsNone(volume.gain_filter('100'))
        self.assertEqual(volume.mpv_args(ANKI_ARGS, 100), ANKI_ARGS)

    def test_out_of_range_and_nonsense_fall_back_instead_of_raising(self):
        self.assertEqual(volume.clamp(9), volume.FLOOR)
        self.assertEqual(volume.clamp(9999), volume.CEILING)
        self.assertEqual(volume.clamp('180'), 180)
        self.assertEqual(volume.clamp(None), volume.NEUTRAL)
        self.assertEqual(volume.clamp('loud'), volume.NEUTRAL)


class Filters(unittest.TestCase):
    def test_boosting_adds_a_ceiling_but_turning_down_does_not(self):
        loud = volume.gain_filter(180)
        self.assertIn('volume=1.80', loud)
        self.assertIn('alimiter', loud)
        self.assertEqual(volume.gain_filter(60), 'lavfi=[volume=0.60]')

    def test_the_filter_is_the_only_thing_we_add_and_we_recognise_our_own(self):
        self.assertTrue(volume.is_ours('--af-add=' + volume.gain_filter(180)))
        self.assertFalse(volume.is_ours('--af-add=lavfi=[apad=pad_dur=0.150]'))
        self.assertFalse(volume.is_ours('--volume=180'))


class Arguments(unittest.TestCase):
    def test_ankis_own_filters_survive_and_applying_twice_does_not_stack(self):
        once = volume.mpv_args(ANKI_ARGS, 180)
        twice = volume.mpv_args(once, 180)
        self.assertEqual(once, twice)
        self.assertIn('--af-add=lavfi=[apad=pad_dur=0.150]', twice)
        self.assertEqual([arg for arg in twice if volume.is_ours(arg)],
                         ['--af-add=lavfi=[volume=1.80,alimiter=limit=0.95]'])

    def test_turning_the_gain_back_off_leaves_anki_exactly_as_it_was(self):
        self.assertEqual(volume.mpv_args(volume.mpv_args(ANKI_ARGS, 250), 100), ANKI_ARGS)

    def test_moving_the_dial_replaces_the_filter_instead_of_adding_another(self):
        args = volume.mpv_args(volume.mpv_args(ANKI_ARGS, 180), 120)
        self.assertEqual([arg for arg in args if volume.is_ours(arg)],
                         ['--af-add=lavfi=[volume=1.20,alimiter=limit=0.95]'])


class LiveProcess(unittest.TestCase):
    def test_the_running_player_is_told_to_swap_the_filter(self):
        # change-list takes name, operation, value: passing "+filter" as the operation is
        # what mpv answered "invalid parameter" to on the real machine.
        self.assertEqual(volume.af_changes(None, 180), [('+', 'lavfi=[volume=1.80,alimiter=limit=0.95]')])
        self.assertEqual(volume.af_changes('lavfi=[volume=1.80,alimiter=limit=0.95]', 180),
                         [('-', 'lavfi=[volume=1.80,alimiter=limit=0.95]'),
                          ('+', 'lavfi=[volume=1.80,alimiter=limit=0.95]')])
        self.assertEqual(volume.af_changes('lavfi=[volume=1.80,alimiter=limit=0.95]', 220),
                         [('-', 'lavfi=[volume=1.80,alimiter=limit=0.95]'),
                          ('+', 'lavfi=[volume=2.20,alimiter=limit=0.95]')])
        self.assertEqual(volume.af_changes('lavfi=[volume=1.80]', 100), [('-', 'lavfi=[volume=1.80]')])
        self.assertEqual(volume.af_changes(None, 100), [])

    def test_apply_writes_both_handles_and_reports_what_it_touched(self):
        spawning, live = SpawningPlayer(), LivePlayer()
        applied = volume.apply_volume([spawning, live], 180, None)
        self.assertEqual(applied['spec'], 'lavfi=[volume=1.80,alimiter=limit=0.95]')
        self.assertEqual(applied['errors'], [])
        self.assertEqual(applied['touched'], ['SpawningPlayer.args', 'LivePlayer.args', 'LivePlayer.af'])
        for handle in (spawning, live):
            self.assertIn('--af-add=lavfi=[volume=1.80,alimiter=limit=0.95]', handle.args)
            self.assertIn('--af-add=lavfi=[apad=pad_dur=0.150]', handle.args)
        self.assertEqual(live.sent, [('change-list', 'af', '+', 'lavfi=[volume=1.80,alimiter=limit=0.95]')])

    def test_the_persistent_player_is_also_fixed_for_its_next_spawn(self):
        # MpvBase keeps its command line in `argv`, not `args`, and rebuilds the process
        # from it if mpv dies mid-session.
        manager = LivePlayer()
        manager.args = None
        manager.argv = list(ANKI_ARGS)
        applied = volume.apply_volume([manager], 180, None)
        self.assertIn('LivePlayer.argv', applied['touched'])
        self.assertIn('--af-add=lavfi=[volume=1.80,alimiter=limit=0.95]', manager.argv)

    def test_a_list_that_is_not_an_mpv_command_line_is_left_alone(self):
        # SimpleProcessPlayer declares `args = []` on the class and every TTS player
        # inherits that one list; putting an mpv filter in it would be inert at best.
        class OtherPlayer:
            args = []
            argv = ['lame.exe', '-b', '128']

        handle = OtherPlayer()
        applied = volume.apply_volume([handle], 180, None)
        self.assertEqual(handle.args, [])
        self.assertEqual(handle.argv, ['lame.exe', '-b', '128'])
        self.assertEqual(applied['touched'], [])

    def test_a_player_that_has_gone_away_is_reported_not_raised(self):
        # Anki's persistent mpv dies with the process that owns it; saving settings must
        # still work, so a failed command becomes one line in the report instead of a
        # crash or a pile of retries against the same dead socket.
        applied = volume.apply_volume([LivePlayer(fail=True)], 200, 'lavfi=[volume=1.50,alimiter=limit=0.95]')
        self.assertEqual(len(applied['errors']), 1)
        self.assertIn('mpv is not running', applied['errors'][0])
        self.assertEqual(applied['touched'], ['LivePlayer.args'])

    def test_no_players_at_all_is_not_a_crash(self):
        applied = volume.apply_volume([], 180, None)
        self.assertEqual(applied['touched'], [])
        self.assertEqual(applied['errors'], [])
        self.assertEqual(applied['spec'], 'lavfi=[volume=1.80,alimiter=limit=0.95]')

    def test_an_object_without_the_attributes_is_left_alone(self):
        class NotAPlayer:
            pass
        applied = volume.apply_volume([NotAPlayer()], 180, None)
        self.assertEqual(applied['touched'], [])
        self.assertEqual(applied['errors'], [])


class RememberingTheLiveFilter(unittest.TestCase):
    def test_the_control_replaces_what_is_live_instead_of_stacking_it(self):
        # Anki gives no way to read mpv's filter list back, so the add-on keeps its own
        # note of what it put there; that is what makes moving the dial a swap.
        control = volume.VolumeControl()
        live = LivePlayer()
        first = control.set([live], 180)
        self.assertEqual(control.spec, first['spec'])
        self.assertEqual(live.sent, [('change-list', 'af', '+', 'lavfi=[volume=1.80,alimiter=limit=0.95]')])
        control.set([live], 220)
        self.assertEqual(live.sent[-2:], [('change-list', 'af', '-', 'lavfi=[volume=1.80,alimiter=limit=0.95]'),
                                          ('change-list', 'af', '+', 'lavfi=[volume=2.20,alimiter=limit=0.95]')])
        control.set([live], 100)
        self.assertIsNone(control.spec)
        self.assertEqual([arg for arg in live.args if volume.is_ours(arg)], [])
        self.assertEqual(live.args, ANKI_ARGS)


    def test_a_new_player_process_is_told_to_add_only(self):
        # Anki builds a fresh main window (and a fresh mpv) when the profile changes. The
        # new process never carried the filter, so removing it first would only ever fail.
        control = volume.VolumeControl()
        control.set([LivePlayer()], 180)
        control.reset()
        fresh = LivePlayer()
        control.set([fresh], 180)
        self.assertEqual(fresh.sent, [('change-list', 'af', '+', 'lavfi=[volume=1.80,alimiter=limit=0.95]')])


    def test_live_false_leaves_the_running_process_alone(self):
        live = LivePlayer()
        applied = volume.apply_volume([live], 180, None, live=False)
        self.assertEqual(live.sent, [])
        self.assertEqual(applied['touched'], ['LivePlayer.args'])
        self.assertFalse(applied['af_failed'])

    def test_a_refused_command_is_asked_once_per_anki_session(self):
        # mpv 0.41 refuses change-list on af. The argument lists carry the gain anyway, so
        # after one refusal the running process is left be rather than nagged every save.
        control = volume.VolumeControl()
        live = LivePlayer(fail=True)
        first = control.set([live], 180)
        self.assertTrue(first['af_failed'])
        self.assertFalse(control.live)
        second = control.set([live], 220)
        self.assertEqual(second['errors'], [])
        self.assertEqual(second['touched'], ['LivePlayer.args'])
        self.assertEqual(control.spec, 'lavfi=[volume=2.20,alimiter=limit=0.95]')
        self.assertEqual(live.sent, [])


class Routing(unittest.TestCase):
    def test_the_report_names_every_player_and_the_rank_it_claims(self):
        # The gain only reaches what mpv plays. If Anki picks SAPI for a word, no filter of
        # ours can touch it, so the ranks have to be visible in the log.
        class Claims:
            def rank_for_tag(self, tag):
                return 1

        class Refuses:
            def rank_for_tag(self, tag):
                return None

        class Broken:
            def rank_for_tag(self, tag):
                raise RuntimeError('no voices installed')

        class Silent:
            pass

        self.assertEqual(
            volume.describe_players([Claims(), Refuses(), Broken(), Silent()], object()),
            'Claims=1 Refuses=None Broken=error:RuntimeError Silent=no-rank')
        self.assertEqual(volume.describe_players([], object()), '')
        self.assertEqual(volume.describe_players(None, object()), '')


class RenderDrive(unittest.TestCase):
    """How hard the rendered word is compressed, per dialled percentage.

    Measured on this machine's own speech: the word's peaks sit ~20 dB above its average, so
    a linear gain runs out of headroom near -21 dBFS RMS while a video's dialogue sits at
    about -16. Deepening the compression closes that gap, but the user's verdict was 好难听 —
    so the loudness now comes from lifting the presence band (`speech.boost_presence`) and
    the compression is capped where it still sounds human.
    """

    def test_a_neutral_dial_asks_for_no_compression(self):
        self.assertEqual(volume.render_drive(100), 1.0)
        self.assertEqual(volume.render_drive(60), 1.0)

    def test_the_ladder_is_gentle_and_stops_where_it_still_sounds_human(self):
        self.assertAlmostEqual(volume.render_drive(150), 1.1)
        self.assertAlmostEqual(volume.render_drive(200), 1.2)
        self.assertAlmostEqual(volume.render_drive(250), 1.3)
        self.assertAlmostEqual(volume.render_drive(300), 1.4)
        self.assertEqual(volume.render_drive(999), volume.DRIVE_CEILING)
        self.assertLessEqual(volume.DRIVE_CEILING, 1.5,
                             'above this the word audibly squashes; loudness belongs in the EQ')


    def test_work_that_was_already_done_is_not_reported_as_touched(self):
        # The log is the only witness to what the add-on changed on Anki's player, so a list
        # that came back identical must not be listed as changed.
        player = LivePlayer(args=volume.mpv_args(ANKI_ARGS, 180))
        applied = volume.apply_volume([player], 180, None)
        self.assertEqual(applied['touched'], ['LivePlayer.af'])
        self.assertEqual(player.args, volume.mpv_args(ANKI_ARGS, 180))


if __name__ == '__main__':
    unittest.main()
