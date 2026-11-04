"""The spelling-card motion rules, tested as plain arithmetic.

Everything here is deliberately Qt-free: which tier a performance earns, what each tier is
allowed to draw, and how long the whole thing may take. The Qt layer only plays what this
module decides, so the parts a user can complain about ("too flashy", "it blocked my Enter")
are testable without a window.
"""
import importlib.util
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'anki-global-addon', 'zotero_global_capture', 'card_motion.py')
spec = importlib.util.spec_from_file_location('card_motion', SRC)
motion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(motion)


class Tier(unittest.TestCase):
    def test_every_mode_where_letters_are_typed_celebrates(self):
        # The letter boxes are shared by typing, cloze and listening, so those three are one
        # experience to the learner. Celebrating only `typing` meant the letters hopped on a
        # cloze card and then nothing came — measured 2026-11-04: 6 celebrations in 134 cards.
        for mode in ('typing', 'cloze', 'listening'):
            self.assertEqual(motion.tier_for(mode, True, seconds=1.2), 1, mode)

    def test_recognition_and_spoken_modes_do_not_celebrate(self):
        # Picking the right meaning or saying it aloud is not producing the spelling.
        for mode in ('choice', 'judgment', 'reverse', 'speaking'):
            self.assertEqual(motion.tier_for(mode, True, seconds=0.1), 0, mode)

    def test_a_flawless_fast_spelling_is_the_top_tier(self):
        self.assertEqual(motion.tier_for('typing', True, incorrect_letters=0, hints=0,
                                         failed_checks=0, seconds=5.9), 1)
        self.assertEqual(motion.tier_for('typing', True, incorrect_letters=0, hints=0,
                                         failed_checks=0, seconds=6.0), 1)
        # Over the line and the same answer is merely 完美 — the bar moved from 3 秒 because
        # at 3 秒 it never fired in a whole day of real studying.
        self.assertEqual(motion.tier_for('typing', True, incorrect_letters=0, hints=0,
                                         failed_checks=0, seconds=6.1), 2)
        self.assertEqual(motion.FAST_SECONDS, 6.0)

    def test_a_single_corrected_slip_is_one_tier_down(self):
        self.assertEqual(motion.tier_for('typing', True, incorrect_letters=1, hints=0,
                                         failed_checks=0, seconds=1.0), 3)

    def test_any_hint_or_repeat_failure_lands_on_the_gentlest_tier(self):
        self.assertEqual(motion.tier_for('typing', True, hints=1, seconds=1.0), 4)
        self.assertEqual(motion.tier_for('typing', True, failed_checks=1, seconds=1.0), 4)
        self.assertEqual(motion.tier_for('typing', True, incorrect_letters=3, seconds=1.0), 4)

    def test_a_wrong_answer_gets_nothing(self):
        self.assertEqual(motion.tier_for('typing', False, seconds=1.0), 0)
        self.assertEqual(motion.tier_for('typing', None, seconds=1.0), 0)


class Labels(unittest.TestCase):
    def test_the_badge_words_are_chinese_with_a_latin_caption(self):
        self.assertEqual([motion.tier_label(tier) for tier in (1, 2, 3, 4)],
                         ['不可思议', '完美', '很棒', '不错'])
        self.assertTrue(all(motion.tier_caption(tier).isascii() for tier in (1, 2, 3, 4)))
        self.assertEqual(motion.tier_label(0), '')

    def test_no_tier_shakes_the_whole_card(self):
        # The mockup had a 120ms card shake on the top tier; on the dark card it read as a
        # rendering fault, so the shipped motion never moves the window itself.
        self.assertFalse(any(step['name'] == 'card-shake' for tier in (1, 2, 3, 4)
                             for step in motion.timeline(tier, 'full')))


class WhatEachTierDraws(unittest.TestCase):
    def test_the_decoration_reaches_more_of_the_ladder(self):
        # Confetti was top-tier only, and the top tier never fired in a day, so nobody ever
        # saw the festive part. It now covers the two clean-recall tiers; sparks reach one
        # tier lower. 不错 (a hint was used) stays a plain pill.
        for tier in (1, 2, 3):
            self.assertTrue(motion.shows_sparks(tier), tier)
        self.assertFalse(motion.shows_sparks(4))
        for tier in (1, 2):
            self.assertTrue(motion.shows_confetti(tier), tier)
        for tier in (3, 4):
            self.assertFalse(motion.shows_confetti(tier), tier)

    def test_calm_mode_keeps_the_badge_and_the_letter_hop_but_drops_the_deco(self):
        full = {step['name'] for step in motion.timeline(1, 'full')}
        calm = {step['name'] for step in motion.timeline(1, 'calm')}
        self.assertIn('confetti', full)
        self.assertIn('sparks', full)
        self.assertNotIn('confetti', calm)
        self.assertNotIn('sparks', calm)
        self.assertIn('badge', calm)
        self.assertIn('letter', calm)

    def test_off_mode_draws_nothing_at_all(self):
        for tier in (1, 2, 3, 4):
            self.assertEqual(motion.timeline(tier, 'off'), [])
            self.assertFalse(motion.shows_celebration(tier, 'off'))

    def test_a_tier_of_zero_has_no_celebration_in_any_mode(self):
        for mode in ('full', 'calm', 'off'):
            self.assertEqual(motion.timeline(0, mode), [])
            self.assertFalse(motion.shows_celebration(0, mode))


class Timing(unittest.TestCase):
    def test_the_whole_sequence_fits_under_a_second(self):
        for tier in (1, 2, 3, 4):
            total = motion.total_ms(tier, 'full')
            self.assertLessEqual(total, 980, (tier, total))
            self.assertGreater(total, 0)

    def test_the_badge_is_the_last_thing_to_leave(self):
        steps = {step['name']: step for step in motion.timeline(1, 'full')}
        badge_end = steps['badge']['delay'] + steps['badge']['duration']
        for name, step in steps.items():
            if name == 'letter':
                continue          # the letter hop happens while typing, before the answer
            self.assertLessEqual(step['delay'] + step['duration'], badge_end, name)

    def test_the_letter_hop_starts_after_the_word_pop_only_slightly(self):
        # The mockup's order: the last letter lands, then the word pops 60ms later.
        steps = {step['name']: step for step in motion.timeline(2, 'full')}
        self.assertEqual(steps['word']['delay'], 60)

    def test_timings_match_the_approved_mockup(self):
        steps = {step['name']: step for step in motion.timeline(1, 'full')}
        self.assertEqual(steps['letter']['duration'], 180)
        self.assertEqual(steps['word']['duration'], 420)
        self.assertEqual(steps['badge']['in_ms'], 260)
        self.assertEqual(steps['badge']['hold_ms'], 520)
        self.assertEqual(steps['badge']['out_ms'], 200)
        self.assertEqual(steps['sparks']['duration'], 500)
        self.assertEqual(steps['confetti']['duration'], 900)


class SettingMode(unittest.TestCase):
    def test_the_three_positions_are_understood(self):
        self.assertEqual(motion.mode({'review_motion': 'full'}), 'full')
        self.assertEqual(motion.mode({'review_motion': 'calm'}), 'calm')
        self.assertEqual(motion.mode({'review_motion': 'off'}), 'off')

    def test_a_missing_or_bogus_value_defaults_to_the_approved_full_motion(self):
        self.assertEqual(motion.mode({}), 'full')
        self.assertEqual(motion.mode({'review_motion': 'everything please'}), 'full')
        self.assertEqual(motion.mode({'review_motion': None}), 'full')


if __name__ == '__main__':
    unittest.main()
