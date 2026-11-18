"""The home-screen study card and the book switcher.

The start action lives in the centre of Anki's deck-browser home page, not in the
top toolbar. It names the book it will study; switching is a separate action that
must not fire while a card is open.
"""
import ast
import importlib.util
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
path = ROOT / '__init__.py'
tree = ast.parse(path.read_text(encoding='utf-8'))
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
         and n.name in ('study_book_name', 'refresh_toolbar', 'choose_study_book',
                        'on_webview_message')]
spec = importlib.util.spec_from_file_location('book_logic_toolbar', ROOT / 'review_logic.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)


def environment(config, saved, shown, feedback, drawn=None):
    review = types.SimpleNamespace(dialog=None, busy=False, show_next=lambda manual: shown.append(manual))
    drawn = drawn if drawn is not None else []
    return {'mw': types.SimpleNamespace(col=object(),
                                        toolbar=types.SimpleNamespace(draw=lambda: drawn.append(True))),
            'controller': types.SimpleNamespace(review=review),
            'settings': lambda: dict(config),
            'save_settings': lambda cfg: saved.append(dict(cfg)),
            'show_feedback': feedback,
            'log_runtime': lambda *_a, **_k: None,
            'study_book': logic.study_book,
            'study_books': logic.study_books,
            'study_book_id': logic.study_book_id,
            'selection_entries': logic.selection_entries,
            'selection_labels': logic.selection_labels,
            'open_review_from_toolbar': lambda: None}


class HomeButton(unittest.TestCase):
    def test_the_start_button_is_not_registered_in_the_top_toolbar(self):
        source = path.read_text(encoding='utf-8')
        self.assertNotIn('top_toolbar_did_init_links', source)
        self.assertNotIn('create_link(', source)
        self.assertIn('webview_did_receive_js_message.append(on_webview_message)', source)

    def test_the_home_message_starts_a_review_without_swallowing_other_messages(self):
        calls = []
        env = environment({'study_book': ''}, [], [], lambda *_a, **_k: None)
        env['open_review_from_toolbar'] = lambda: calls.append(True)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), env)
        self.assertEqual(env['on_webview_message']((False, None), 'other', None), (False, None))
        self.assertEqual(env['on_webview_message']((False, None), 'zvr-start-review', None), (True, None))
        self.assertEqual(calls, [True])

    def label(self, config):
        env = environment(config, [], [], lambda *_a, **_k: None)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), env)
        return env['study_book_name'](config)

    def test_one_button_that_names_the_book(self):
        self.assertIn('六级核心', self.label({'study_book': 'cet6_core'}))

    def test_no_selection_says_so_on_the_button(self):
        self.assertIn('未选词书', self.label({'study_book': ''}))

    def test_a_book_from_config_is_named_not_guessed(self):
        self.assertIn('文献单词', self.label({'study_book': 'literature'}))

    def test_a_multi_selection_names_every_book_on_the_button(self):
        label = self.label({'study_selection': [{'book': 'cet6_core', 'tags': []},
                                                {'book': 'cet6_full', 'tags': ['高频']}]})
        self.assertIn('六级核心', label)
        self.assertIn('六级全表', label)


class Switching(unittest.TestCase):
    def run_switch(self, config, book_id, dialog=None, busy=False, fail=False):
        saved, shown, messages = [], [], []
        review = types.SimpleNamespace(dialog=dialog, busy=busy, show_next=lambda manual: shown.append(manual))
        env = environment(config, saved, shown, messages.append)
        env['controller'] = types.SimpleNamespace(review=review)
        if fail:
            def boom(_cfg):
                raise RuntimeError('disk full')
            env['save_settings'] = boom
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), env)
        env['choose_study_book'](book_id)
        return saved, shown, messages

    def test_switching_saves_the_book_and_starts(self):
        saved, shown, messages = self.run_switch({'study_book': 'cet6_core'}, 'cet4_core')
        self.assertEqual([cfg['study_selection'] for cfg in saved],
                         [[{'book': 'cet4_core', 'tags': []}, {'book': 'cet6_core', 'tags': []}]],
                         'the picked book leads the handover; the old one stays behind it')
        self.assertEqual(shown, [True])
        self.assertEqual(messages, [])

    def test_switching_promotes_a_book_already_in_the_selection_without_dropping_tags(self):
        config = {'study_selection': [{'book': 'cet6_core', 'tags': []},
                                      {'book': 'cet6_full', 'tags': ['高频', '真题']}]}
        saved, shown, messages = self.run_switch(config, 'cet6_full')
        self.assertEqual(saved[0]['study_selection'],
                         [{'book': 'cet6_full', 'tags': ['高频', '真题']},
                          {'book': 'cet6_core', 'tags': []}],
                         'the tag subset must survive the promotion')
        self.assertEqual(shown, [True])

    def test_switching_does_not_write_the_legacy_key(self):
        saved, shown, messages = self.run_switch({'study_book': 'cet6_core'}, 'cet4_core')
        self.assertNotIn('study_book', saved[0], '写回时只写 study_selection（spec §3.1）')

    def test_switching_refreshes_the_toolbar_name_immediately(self):
        # The old label survived until an Anki restart, so the button kept naming
        # the previous book while the dashboard studied the new one.
        saved, shown, messages, drawn = [], [], [], []
        env = environment({'study_book': 'cet6_core'}, saved, shown, messages.append, drawn)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), env)
        env['choose_study_book']('cet4_core')
        self.assertEqual(drawn, [True])

    def test_an_unknown_book_is_refused_without_touching_the_config(self):
        saved, shown, messages = self.run_switch({'study_book': 'cet6_core'}, 'does_not_exist')
        self.assertEqual(saved, [])
        self.assertEqual(shown, [])
        self.assertTrue(messages)

    def test_a_card_on_screen_blocks_the_switch(self):
        # Swapping books mid-card would leave the open card grading into the new range.
        for dialog, busy in ((object(), False), (None, True)):
            saved, shown, messages = self.run_switch({'study_book': 'cet6_core'}, 'cet6_full',
                                                     dialog=dialog, busy=busy)
            self.assertEqual(saved, [], 'switching must not save while a card is up')
            self.assertEqual(shown, [])
            self.assertTrue(messages)

    def test_a_failed_save_does_not_start_studying_the_wrong_book(self):
        saved, shown, messages = self.run_switch({'study_book': 'cet6_core'}, 'cet6_full', fail=True)
        self.assertEqual(shown, [], 'show_next would study the old book while the save failed')
        self.assertIn('disk full', ''.join(messages))


if __name__ == '__main__':
    unittest.main()
