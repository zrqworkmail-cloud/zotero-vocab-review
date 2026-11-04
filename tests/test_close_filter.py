"""The window-close filter, tested without a running Anki.

Two decisions live here and both have already bitten: closing Anki's main window must
become a hide only while a study card is on screen — really on screen, not merely still
referenced — and a *real* close has to stop the reminder timer and the background sync
first. Without that second part the app sits in shutdown forever resuming its own timers,
which is what left an Anki with no windows and no way to quit.
"""
import ast
import importlib.util
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'anki-global-addon' / 'zotero_global_capture' / '__init__.py'
spec = importlib.util.spec_from_file_location('review_logic_close', source.parent / 'review_logic.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

CLOSE = 'close'
OTHER = 'paint'


class EventType:
    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return other is not None and getattr(other, 'value', None) == self.value


class Event:
    def __init__(self, value):
        self._type = EventType(value)
        self.ignored = False

    def type(self):
        return self._type

    def ignore(self):
        self.ignored = True


QEvent = types.SimpleNamespace(Type=types.SimpleNamespace(Close=EventType(CLOSE)))


def build(card_open, hide_enabled, visible=None, syncing=False, tray=False, forcing=False):
    """The filter class pulled out of __init__.py, run against stubs."""
    stopped = []
    timer = types.SimpleNamespace(stopped=[], stop=lambda: timer.stopped.append(True))
    review = types.SimpleNamespace(dialog=object() if card_open else None,
                                   card_on_screen=lambda: card_open if visible is None else visible,
                                   stop=lambda: stopped.append('review'))
    controller = types.SimpleNamespace(review=review, sync_timer=timer)
    hidden = []
    mw = types.SimpleNamespace(hide=lambda: hidden.append(True))
    if tray:
        # 'Minimize to Tray 2' puts this attribute on mw and rewrites mw.closeEvent with it.
        mw.closeEventFromAction = False
    if forcing:
        mw.zvr_force_quit = True
    scope = {'QEvent': QEvent, 'mw': mw,
             'controller': controller, 'settings': lambda: {'hide_main_on_close': hide_enabled},
             'show_feedback': lambda *a, **k: None, 'log_runtime': lambda *a: None,
             'hide_instead_of_quit': logic.hide_instead_of_quit,
             'background_instead_of_quit': logic.background_instead_of_quit, 'QObject': object}
    syncer = types.SimpleNamespace(stopped=[], is_syncing=lambda: syncing,
                                   abort=lambda: syncer.stopped.append(True))
    mw.media_syncer = syncer
    tree = ast.parse(source.read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if (isinstance(n, ast.ClassDef) and n.name == 'MainWindowCloseFilter')
             or (isinstance(n, ast.FunctionDef) and n.name == 'abort_media_sync')]
    for node in nodes:
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
    return scope['MainWindowCloseFilter'](), stopped, timer, hidden, mw


class CloseFilter(unittest.TestCase):
    def test_a_card_on_screen_turns_the_close_into_a_hide(self):
        widget, stopped, timer, hidden, mw = build(card_open=True, hide_enabled=True)
        event = Event(CLOSE)
        self.assertTrue(widget.eventFilter(object(), event))
        self.assertEqual(hidden, [True], 'the main window should only be hidden')
        self.assertTrue(event.ignored, 'the close must be cancelled')
        self.assertEqual((stopped, timer.stopped), ([], []), 'a hide must not end the session or the sync')
        self.assertFalse(getattr(mw, 'zvr_closing', False), 'hiding is not closing')

    def test_a_real_close_stops_the_reminder_and_the_sync_timer(self):
        widget, stopped, timer, hidden, mw = build(card_open=False, hide_enabled=True)
        self.assertFalse(widget.eventFilter(object(), Event(CLOSE)), 'the close must reach Anki')
        self.assertEqual(stopped, ['review'], 'the popup timer has to stop or a card reopens mid-shutdown')
        self.assertEqual(timer.stopped, [True], 'the background sync has to stop or it restarts the shutdown')
        self.assertTrue(getattr(mw, 'zvr_closing', False), 'a queued sync tick must still be refused')
        self.assertEqual(hidden, [])
        self.assertEqual(mw.media_syncer.stopped, [], 'nothing to abort when no media sync is running')

    def test_a_media_sync_in_flight_is_aborted_so_the_shutdown_can_finish(self):
        # Three restarts today needed a forced kill: Anki waits for the media syncer inside a
        # nested event loop, so the window never went away while AnkiConnect kept answering.
        widget, stopped, timer, hidden, mw = build(card_open=False, hide_enabled=True, syncing=True)
        self.assertFalse(widget.eventFilter(object(), Event(CLOSE)))
        self.assertEqual(mw.media_syncer.stopped, [True], 'the media sync must be aborted, not waited for')

    def test_a_hide_leaves_a_running_media_sync_alone(self):
        widget, stopped, timer, hidden, mw = build(card_open=True, hide_enabled=True, syncing=True)
        self.assertTrue(widget.eventFilter(object(), Event(CLOSE)))
        self.assertEqual(mw.media_syncer.stopped, [], 'hiding is not shutting down')

    def test_the_feature_being_off_changes_nothing(self):
        widget, stopped, timer, hidden, mw = build(card_open=True, hide_enabled=False)
        self.assertFalse(widget.eventFilter(object(), Event(CLOSE)))
        self.assertEqual(hidden, [], 'with the toggle off the close button must quit as before')
        self.assertEqual(stopped, ['review'])

    def test_other_events_are_left_alone(self):
        widget, stopped, timer, hidden, mw = build(card_open=True, hide_enabled=True)
        self.assertFalse(widget.eventFilter(object(), Event(OTHER)))
        self.assertEqual((stopped, timer.stopped, hidden), ([], [], []))

    def test_a_card_on_screen_is_still_kept_visible_when_a_tray_is_installed(self):
        # The tray's hideAll() would take the study card down with the main window, so the
        # card-on-screen branch still runs first and hides only the main window.
        widget, stopped, timer, hidden, mw = build(card_open=True, hide_enabled=True, tray=True)
        event = Event(CLOSE)
        self.assertTrue(widget.eventFilter(object(), event))
        self.assertEqual(hidden, [True], 'the card must not go to the tray with the main window')
        self.assertEqual((stopped, timer.stopped), ([], []))
        self.assertFalse(mw.closeEventFromAction)

    def test_a_card_that_is_only_still_referenced_does_not_block_the_quit(self):
        """The hide is for a card the user can see; a leftover reference must not count."""
        widget, stopped, timer, hidden, mw = build(card_open=True, hide_enabled=True, visible=False)
        self.assertFalse(widget.eventFilter(object(), Event(CLOSE)), 'the close must reach Anki')
        self.assertEqual(hidden, [], 'this is how Anki ended up hidden with no window anyone could close')
        self.assertEqual(stopped, ['review'], 'and the session still ends')


    def test_a_tray_add_on_makes_the_close_button_go_to_background(self):
        """The user runs 'Minimize to Tray 2': X means "keep running in the tray".

        Stopping the timers here is what silenced the popups for an hour on 2026-11-04 —
        the close never was a shutdown, so nothing may be wound down.
        """
        widget, stopped, timer, hidden, mw = build(card_open=False, hide_enabled=True, tray=True)
        self.assertFalse(widget.eventFilter(object(), Event(CLOSE)),
                         'the tray add-on has to receive the close and do the hiding')
        self.assertEqual((stopped, timer.stopped), ([], []), 'background is not shutdown')
        self.assertEqual(hidden, [], 'the tray owns the visibility decision now')
        self.assertFalse(getattr(mw, 'zvr_closing', False))
        self.assertFalse(mw.closeEventFromAction, 'we must not claim an exit the user did not ask for')

    def test_the_card_menu_exit_still_quits_with_a_tray_installed(self):
        # 退出 Anki sets zvr_force_quit; that is the one close which really is a shutdown,
        # so the timers must go down exactly as before.
        widget, stopped, timer, hidden, mw = build(card_open=False, hide_enabled=True,
                                                   tray=True, forcing=True)
        self.assertFalse(widget.eventFilter(object(), Event(CLOSE)))
        self.assertEqual(stopped, ['review'])
        self.assertEqual(timer.stopped, [True])

    def test_a_card_on_screen_still_hides_when_there_is_no_tray(self):
        # The tray case must not swallow our own feature: without the add-on the old three
        # outcomes (hide / quit / forced quit) still hold.
        widget, stopped, timer, hidden, mw = build(card_open=True, hide_enabled=True, tray=False)
        self.assertTrue(widget.eventFilter(object(), Event(CLOSE)))
        self.assertEqual((hidden, stopped, timer.stopped), ([True], [], []))


if __name__ == '__main__':
    unittest.main()
