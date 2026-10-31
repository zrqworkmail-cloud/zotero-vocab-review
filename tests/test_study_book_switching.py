"""The main-screen button and the book switcher.

There used to be three toolbar links — a review button and two 词书 shortcuts that
each rewrote a private scope. Now there is one button that names the book it will
study, and switching is a separate action that must not fire while a card is open.
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
         and n.name in ('add_review_to_toolbar', 'choose_study_book')]
spec = importlib.util.spec_from_file_location('book_logic_toolbar', ROOT / 'review_logic.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)


def environment(config, saved, shown, feedback):
    review = types.SimpleNamespace(dialog=None, busy=False, show_next=lambda manual: shown.append(manual))
    return {'mw': types.SimpleNamespace(col=object()),
            'controller': types.SimpleNamespace(review=review),
            'settings': lambda: dict(config),
            'save_settings': lambda cfg: saved.append(dict(cfg)),
            'show_feedback': feedback,
            'study_book': logic.study_book,
            'study_books': logic.study_books,
            'study_book_id': logic.study_book_id,
            'open_review_from_toolbar': lambda: None}


class Toolbar(unittest.TestCase):
    def collect(self, config):
        links = []
        # create_link returns the link; the production code is what appends it.
        toolbar = types.SimpleNamespace(create_link=lambda cmd, label, func, **kw: (label, kw))
        env = environment(config, [], [], lambda *_a, **_k: None)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), env)
        env['add_review_to_toolbar'](links, toolbar)
        return links

    def test_one_button_that_names_the_book(self):
        links = self.collect({'study_book': 'cet6_core'})
        self.assertEqual(len(links), 1, 'the two 词书 shortcuts are gone')
        self.assertIn('六级核心', links[0][0])
        self.assertIn('六级核心', links[0][1]['tip'])

    def test_no_selection_says_so_on_the_button(self):
        links = self.collect({'study_book': ''})
        self.assertIn('未选词书', links[0][0])

    def test_a_book_from_config_is_named_not_guessed(self):
        config = {'study_book': 'literature'}
        self.assertIn('文献单词', self.collect(config)[0][0])


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
        self.assertEqual([cfg['study_book'] for cfg in saved], ['cet4_core'])
        self.assertEqual(shown, [True])
        self.assertEqual(messages, [])

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
