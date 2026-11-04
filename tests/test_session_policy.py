"""The three session policies the user asked for on 2026-11-02.

Anki syncs on open and on close, which is two waits around every study session; the
main window cannot be closed while a card is up; and the card is always on top. These
are pure decisions so the rules can be read and argued about without a Qt or Anki
fixture — the wiring in __init__.py only calls them.
"""
import datetime
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
spec = importlib.util.spec_from_file_location('review_logic_session', ROOT / 'review_logic.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)


class BackgroundSync(unittest.TestCase):
    def test_turning_the_feature_off_restores_what_anki_had(self):
        profile = {'autoSync': True}
        remembered = logic.apply_auto_sync_preference(profile, True, None)
        self.assertFalse(profile['autoSync'], 'Anki must stop syncing on open and close')
        self.assertTrue(remembered)
        self.assertEqual(logic.apply_auto_sync_preference(profile, True, remembered), remembered,
                         'a repeat apply must not lose the remembered value')
        self.assertEqual(logic.apply_auto_sync_preference(profile, False, remembered), None)
        self.assertTrue(profile['autoSync'], 'the user must get their own setting back')

    def test_a_value_the_user_already_turned_off_is_not_turned_back_on(self):
        profile = {'autoSync': False}
        remembered = logic.apply_auto_sync_preference(profile, True, None)
        self.assertFalse(remembered, 'we only remember what we found, not what we assume')
        self.assertEqual(logic.apply_auto_sync_preference(profile, False, remembered), None)
        self.assertFalse(profile['autoSync'])

    def test_no_profile_is_not_an_error(self):
        self.assertIsNone(logic.apply_auto_sync_preference(None, True, None))

    def test_sync_waits_for_a_quiet_moment_and_then_runs_periodically(self):
        start = datetime.datetime(2026, 11, 2, 10, 0, 0)
        self.assertFalse(logic.sync_due(start, None, 5, idle=False), 'never sync mid-card')
        self.assertTrue(logic.sync_due(start, None, 5, idle=True), 'the first idle moment syncs')
        self.assertFalse(logic.sync_due(start + datetime.timedelta(minutes=2), start, 5, idle=True))
        self.assertTrue(logic.sync_due(start + datetime.timedelta(minutes=5), start, 5, idle=True))

    def test_the_interval_is_never_shorter_than_a_minute(self):
        start = datetime.datetime(2026, 11, 2, 10, 0, 0)
        self.assertTrue(logic.sync_due(start + datetime.timedelta(seconds=61), start, 0, idle=True))
        self.assertFalse(logic.sync_due(start + datetime.timedelta(seconds=30), start, 0, idle=True))


class ClosingTheMainWindow(unittest.TestCase):
    def test_closing_hides_only_while_a_card_is_up(self):
        self.assertTrue(logic.hide_instead_of_quit(card_open=True, enabled=True, forcing_quit=False))
        self.assertFalse(logic.hide_instead_of_quit(card_open=False, enabled=True, forcing_quit=False),
                         'with no card on screen Anki must still quit normally')
        self.assertFalse(logic.hide_instead_of_quit(card_open=True, enabled=False, forcing_quit=False))
        self.assertFalse(logic.hide_instead_of_quit(card_open=True, enabled=True, forcing_quit=True),
                         'the card menu can always quit Anki for real')


class SilentSyncErrors(unittest.TestCase):
    """A failed background sync must stay in the log, not interrupt with Anki's error box.

    On 2026-11-02 the proxy made AnkiWeb unreachable and the idle sync answered with the
    modal "发生网络错误" dialog — the one thing a silent sync may never do.
    """

    def setUp(self):
        import types
        self.reported = []
        self.original = lambda mw, err: self.reported.append(err)
        self.module = types.SimpleNamespace(handle_sync_error=self.original)
        self.state = {}
        self.raised = []
        self.restore = logic.install_sync_error_guard(self.module, self.state, self.raised.append)

    def test_a_failure_is_recorded_instead_of_opening_a_dialog(self):
        self.assertIsNot(self.module.handle_sync_error, self.original, 'the dialog path must be swapped out')
        self.module.handle_sync_error(object(), RuntimeError('error sending request for url ()'))
        self.assertEqual(self.reported, [], 'Anki must not get to show its modal')
        self.assertIn('error sending request', self.state['error'])
        self.assertEqual(len(self.raised), 1, 'the caller gets told once, to pause the timer')

    def test_one_failure_ends_the_guard(self):
        for _ in range(2):
            self.module.handle_sync_error(object(), RuntimeError('boom'))
        self.assertEqual(len(self.raised), 1, 'the timer is paused on the first failure')
        self.assertEqual(len(self.reported), 1, 'and the guard is gone, so nothing else is swallowed')

    def test_restoring_gives_anki_its_own_error_box_back(self):
        self.module.handle_sync_error(object(), RuntimeError('boom'))
        self.restore()
        self.restore()
        self.assertIs(self.module.handle_sync_error, self.original,
                      "Anki's own sync button must still report errors the normal way")

    def test_guarding_twice_does_not_wrap_the_guard(self):
        state2, raised2 = {}, []
        second = logic.install_sync_error_guard(self.module, state2, raised2.append)
        self.restore()
        second()
        self.assertIs(self.module.handle_sync_error, self.original)

    def test_a_sync_module_without_the_handler_is_left_alone(self):
        import types
        bare = types.SimpleNamespace()
        state, raised = {}, []
        self.assertIsNotNone(logic.install_sync_error_guard(bare, state, raised.append))
        bare.handle_sync_error = 'not callable'
        logic.install_sync_error_guard(bare, state, raised.append)


if __name__ == '__main__':
    unittest.main()
