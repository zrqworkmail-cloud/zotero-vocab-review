"""The idle background sync, wired the way the user asked: quietly, and only in a spare moment.

On 2026-11-02 the background sync surfaced Anki's modal "发生网络错误" box, which is the one
thing an idle sync may never do. These checks run the real `run_background_sync` and friends
from __init__.py against stubs, so the wiring — the guard going on, Anki's error box coming
back off it, the timer pausing after one failure, and the notice being a toast — is pinned
rather than assumed.
"""
import ast
import datetime
import importlib.util
import re
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'anki-global-addon' / 'zotero_global_capture' / '__init__.py'
spec = importlib.util.spec_from_file_location('review_logic_sync', source.parent / 'review_logic.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

WANTED = ('run_background_sync', 'start_sync_timer', 'pause_background_sync',
          'end_background_sync', 'short_sync_reason', 'sync_is_logged_in')


class FakeTimer:
    def __init__(self):
        self.stopped = []
        self.started = []

    def stop(self):
        self.stopped.append(True)

    def start(self, ms):
        self.started.append(ms)


class FakeQTimer:
    """Anki's one-shot timer, recorded instead of fired."""
    shots = []

    @staticmethod
    def singleShot(ms, callback):
        FakeQTimer.shots.append((ms, callback))


def build(cfg=None, dispatch_error=None, idle=True, auth=True):
    """The sync wiring pulled out of __init__.py, run against a stubbed Anki."""
    FakeQTimer.shots = []
    dialogs = []
    handler = lambda mw, err: dialogs.append(err)          # Anki's modal error box
    sync_module = types.SimpleNamespace(handle_sync_error=handler)
    notices, notes, started = [], [], []
    timer = FakeTimer()

    def dispatch():
        if dispatch_error is not None:
            raise dispatch_error
        started.append(True)

    mw = types.SimpleNamespace(zvr_closing=False,
                               pm=types.SimpleNamespace(sync_auth=lambda: auth or None),
                               on_sync_button_clicked=dispatch)
    controller = types.SimpleNamespace(sync_timer=timer)
    scope = {'datetime': datetime, 're': re, 'QTimer': FakeQTimer, 'mw': mw, 'controller': controller,
             'settings': lambda: dict({'sync_background': True, 'sync_background_minutes': 5}, **(cfg or {})),
             'study_is_idle': lambda: idle, 'sync_due': logic.sync_due,
             'install_sync_error_guard': logic.install_sync_error_guard,
             'aqt_sync_module': lambda: sync_module, 'sync_state': {'last': None, 'running': False,
                                                                    'guard': None, 'error': None},
             'log_runtime': notes.append, 'show_feedback': lambda message, **kw: notices.append(message)}
    tree = ast.parse(source.read_text(encoding='utf-8'))
    # exec'd into one dict, so the helpers reach each other the way they do in the add-on
    for name in WANTED:
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
    sync_module.original_box = handler
    return scope, mw, timer, sync_module, dialogs, notices, notes, started


class IdleSync(unittest.TestCase):
    def test_a_sync_in_progress_installs_the_guard_and_keeps_the_timer(self):
        scope, mw, timer, sync_module, dialogs, notices, notes, started = build()
        scope['run_background_sync']()
        self.assertEqual(started, [True], "Anki's own sync path should run")
        self.assertIsNot(sync_module.handle_sync_error, sync_module.original_box,
                         'the modal box has to be swapped out before Anki is asked to sync')
        self.assertTrue(scope['sync_state']['running'], 'an in-flight sync must block the next tick')
        self.assertEqual(timer.stopped, [], 'nothing went wrong, so nothing is paused')
        self.assertEqual(notices, [])
        self.assertEqual(len(FakeQTimer.shots), 1, 'a watchdog is armed to give the error box back')

    def test_anki_reports_a_failure_and_the_sync_is_paused_once(self):
        scope, mw, timer, sync_module, dialogs, notices, notes, started = build()
        scope['run_background_sync']()
        sync_module.handle_sync_error(mw, RuntimeError('error sending request for url ()'))
        self.assertEqual(dialogs, [], 'Anki must never get to show its modal')
        self.assertIs(sync_module.handle_sync_error, sync_module.original_box,
                      "and Anki's own error box is back where it belongs")
        self.assertEqual(timer.stopped, [True], 'one failure and the timer stands down')
        self.assertEqual(len(notices), 1, 'the user is told once, as a toast')
        self.assertIn('error sending request', notices[0])
        self.assertFalse(scope['sync_state']['running'])
        self.assertIsNone(FakeQTimer.shots[0][1](), 'the watchdog then has nothing left to do')

    def test_a_failure_while_starting_pauses_the_same_way(self):
        scope, mw, timer, sync_module, dialogs, notices, notes, started = build(dispatch_error=OSError('boom'))
        scope['run_background_sync']()
        self.assertEqual(started, [], 'the call never completed')
        self.assertEqual(timer.stopped, [True])
        self.assertEqual(len(notices), 1)
        self.assertEqual(dialogs, [])

    def test_saving_the_settings_arms_it_again(self):
        scope, mw, timer, sync_module, dialogs, notices, notes, started = build()
        scope['run_background_sync']()
        sync_module.handle_sync_error(mw, RuntimeError('down'))
        scope['start_sync_timer']()
        self.assertEqual(timer.started, [60000], 'the notice the user just read is true')
        self.assertFalse(scope['sync_state']['running'], 'a fresh arm forgets the failed attempt')
        scope['run_background_sync']()
        self.assertEqual(len(started), 2, 'and it is willing to try again')

    def test_a_card_on_screen_or_no_login_costs_nothing(self):
        scope, mw, timer, sync_module, dialogs, notices, notes, started = build(idle=False)
        scope['run_background_sync']()
        self.assertEqual(started, [], 'never sync mid-card')
        self.assertEqual((timer.stopped, notices), ([], []), 'a skipped tick is not an error')
        scope, mw, timer, sync_module, dialogs, notices, notes, started = build(auth=False)
        scope['run_background_sync']()
        self.assertEqual(started, [], 'and never without a sync login')
        self.assertIn('waiting for a sync login', ' '.join(notes))

    def test_a_profile_that_cannot_answer_is_not_asked_to_sync(self):
        scope, mw, timer, sync_module, dialogs, notices, notes, started = build(auth=False)
        mw.pm = None
        scope['run_background_sync']()
        self.assertEqual(started, [], 'a failing login check must not end in Anki modal login box')
        self.assertIn('login check failed', ' '.join(notes))

    def test_the_notice_is_short_enough_to_read(self):
        scope = build()[0]
        reason = scope['short_sync_reason']('RuntimeError: ' + 'x' * 400)
        self.assertLessEqual(len(reason), 92, reason)
        self.assertFalse(reason.startswith('RuntimeError'), reason)
        self.assertEqual(scope['short_sync_reason'](''), '网络错误')


if __name__ == '__main__':
    unittest.main()
