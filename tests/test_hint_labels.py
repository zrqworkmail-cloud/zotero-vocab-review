"""The two pure helpers the redesigned hint row depends on.

Kept out of Qt on purpose: what the letter button says, and whether a card is allowed to
offer a transcription at all, are arithmetic over the question — they must be testable
without a window, because the window tests only notice after the fact.
"""
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'anki-global-addon/zotero_global_capture/review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
letter_hint_label = module.letter_hint_label
phonetic_available = module.phonetic_available
pulse_bright = module.pulse_bright


class FocusPulse(unittest.TestCase):
    def test_the_two_halves_alternate(self):
        self.assertEqual([pulse_bright(step) for step in range(6)],
                         [True, False, True, False, True, False])

    def test_the_frame_is_never_switched_off_only_brightened(self):
        # 'off' here means the dim colour, not invisible: a moment with no cue at all would
        # look like the card lost focus, which is what the caret used to say.
        self.assertIn(True, {pulse_bright(0), pulse_bright(1)})
        self.assertIsNot(pulse_bright(0), pulse_bright(1))

    def test_a_broken_period_cannot_crash_the_blink(self):
        self.assertTrue(pulse_bright(3, 0))


class LetterHintLabel(unittest.TestCase):
    def test_counts_start_at_zero_and_name_the_word_length(self):
        self.assertEqual(letter_hint_label(0, 9), '字母 0/9')

    def test_counts_up(self):
        self.assertEqual(letter_hint_label(2, 9), '字母 2/9')

    def test_all_given_away_reads_as_exhausted(self):
        self.assertEqual(letter_hint_label(9, 9), '字母 9/9')

    def test_negative_or_missing_numbers_do_not_leak_through(self):
        self.assertEqual(letter_hint_label(-1, 0), '字母 0/0')


class PhoneticAvailable(unittest.TestCase):
    def test_a_real_transcription_is_enough(self):
        self.assertTrue(phonetic_available({'phonetic': '/hæzərdəs/'}))

    def test_blank_or_absent_means_no_button_at_all(self):
        for question in ({}, {'phonetic': ''}, {'phonetic': '   '}, {'phonetic': None}):
            self.assertFalse(phonetic_available(question), question)

    def test_missing_question_does_not_raise(self):
        self.assertFalse(phonetic_available(None))


if __name__ == '__main__':
    unittest.main()
