"""The 答案面例句 switch, as one pure decision.

Default is on, because that is what every existing install already does; the switch exists so
the learner can stop paying card height for sentences he skips. 例句填空 is excluded by name,
not by accident — its question is an example sentence, so the switch would eat the card.
"""
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic_examples', MODULE)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)


class ShowExamples(unittest.TestCase):
    def test_examples_are_shown_until_the_setting_says_otherwise(self):
        self.assertTrue(logic.show_examples({}, 'typing'),
                        'a config written before this setting existed must keep showing them')
        self.assertTrue(logic.show_examples({'review_show_example': True}, 'typing'))
        self.assertFalse(logic.show_examples({'review_show_example': False}, 'typing'))

    def test_cloze_keeps_its_sentence_whatever_the_switch_says(self):
        for value in (True, False, None):
            self.assertTrue(logic.show_examples({'review_show_example': value}, 'cloze'),
                            'the cloze prompt is an example; the switch must not eat the card')

    def test_the_switch_is_only_about_the_answer_face(self):
        # Every other mode answers with a sentence block that the switch removes; none of them
        # changes what the question face or the hint row offers.
        for mode in ('typing', 'choice', 'reverse', 'listening', 'speaking', 'judgment'):
            self.assertFalse(logic.show_examples({'review_show_example': False}, mode), mode)


if __name__ == '__main__':
    unittest.main()
