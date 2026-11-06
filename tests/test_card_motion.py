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

# The settings page offers two independent switches, so the tests speak in configs rather
# than in the old three-way mode strings.
FULL = {'review_motion_hop': True, 'review_motion_celebration': True}
HOP_ONLY = {'review_motion_hop': True, 'review_motion_celebration': False}
BADGE_ONLY = {'review_motion_hop': False, 'review_motion_celebration': True}
NOTHING = {'review_motion_hop': False, 'review_motion_celebration': False}
TIERS = (1, 2, 3, 4)


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
    def test_the_pop_up_word_is_latin_and_there_is_only_one(self):
        # 「弹出的庆祝窗口不要汉字」(2026-11-04). The badge draws a single Latin grade word;
        # `tier_label`/`TIER_LABELS` were deleted rather than left as a tempting string that
        # some future render path would put back on screen.
        self.assertEqual([motion.tier_caption(tier) for tier in (1, 2, 3, 4)],
                         ['UNBELIEVABLE', 'PERFECT', 'GREAT', 'NICE'])
        for tier in (1, 2, 3, 4):
            self.assertTrue(motion.tier_caption(tier).isascii(), tier)
        self.assertFalse(hasattr(motion, 'TIER_LABELS'))
        self.assertFalse(hasattr(motion, 'tier_label'))
        self.assertEqual(motion.tier_caption(0), '')

    def test_no_tier_shakes_the_whole_card(self):
        # The mockup had a 120ms card shake on the top tier; on the dark card it read as a
        # rendering fault, so the shipped motion never moves the window itself.
        self.assertFalse(any(step['name'] == 'card-shake' for tier in TIERS
                             for step in motion.timeline(tier, FULL)))


class WhatEachTierDraws(unittest.TestCase):
    def test_the_decoration_ladder_points_the_right_way(self):
        # Tier 1 is the best grade and 4 the plainest. The first version of the game-style
        # badge tested these as `tier >= 3`, which decorated 很棒 and left 不可思议 with no
        # stars at all — the ladder inverted, visible in one render.
        for tier in (1, 2, 3):
            self.assertTrue(motion.shows_rays(tier), tier)
        self.assertFalse(motion.shows_rays(4))
        for tier in (1, 2):
            self.assertTrue(motion.shows_stars(tier), tier)
        for tier in (3, 4):
            self.assertFalse(motion.shows_stars(tier), tier)
        self.assertEqual(motion.sparkle_count(1), 5)
        self.assertEqual(motion.sparkle_count(4), 3)

    def test_the_lowest_tier_still_draws_something(self):
        # The user's standing rule: 不错 must not be "no decoration at all". It loses the
        # rays and the stars but keeps the extruded word, the ribbon and the gem, which is
        # what `shows_confetti` was never about.
        self.assertFalse(motion.shows_confetti(4))
        self.assertTrue(motion.shows_sparks(4))
        for tier in (1, 2):
            self.assertTrue(motion.shows_confetti(tier), tier)
        for tier in (3, 4):
            self.assertFalse(motion.shows_confetti(tier), tier)
        self.assertFalse(motion.shows_sparks(0))

    def test_the_two_switches_are_independent(self):
        # The point of replacing the three-way radio: "letters still, badge on" and
        # "letters on, no pop-up" are both real wishes and neither was expressible.
        self.assertEqual([step['name'] for step in motion.timeline(1, HOP_ONLY)],
                         ['letter'])
        self.assertEqual([step['name'] for step in motion.timeline(1, BADGE_ONLY)],
                         ['badge', 'confetti'])
        self.assertEqual(motion.timeline(1, NOTHING), [])
        for tier in TIERS:
            self.assertTrue(motion.shows_celebration(tier, BADGE_ONLY), tier)
            self.assertFalse(motion.shows_celebration(tier, HOP_ONLY), tier)

    def test_calm_is_gone_and_confetti_follows_the_badge(self):
        names = {step['name'] for step in motion.timeline(1, FULL)}
        self.assertIn('confetti', names)
        self.assertIn('badge', names)
        self.assertNotIn('sparks', names)

    def test_both_switches_off_draws_nothing_at_all(self):
        for tier in TIERS:
            self.assertEqual(motion.timeline(tier, NOTHING), [])
            self.assertFalse(motion.shows_celebration(tier, NOTHING))
            self.assertEqual(motion.total_ms(tier, NOTHING), 0)

    def test_a_tier_of_zero_has_no_celebration_in_any_config(self):
        for cfg in (FULL, HOP_ONLY, BADGE_ONLY, NOTHING):
            self.assertEqual(motion.timeline(0, cfg), [])
            self.assertFalse(motion.shows_celebration(0, cfg))


class Timing(unittest.TestCase):
    def test_the_whole_sequence_fits_under_a_second(self):
        for tier in TIERS:
            for cfg in (FULL, BADGE_ONLY):
                total = motion.total_ms(tier, cfg)
                self.assertLessEqual(total, 980, (tier, cfg, total))
                self.assertGreater(total, 0)

    def test_the_badge_is_the_last_thing_to_leave(self):
        steps = {step['name']: step for step in motion.timeline(1, FULL)}
        badge_end = steps['badge']['delay'] + steps['badge']['duration']
        for name, step in steps.items():
            if name == 'letter':
                continue          # the letter hop happens while typing, before the answer
            self.assertLessEqual(step['delay'] + step['duration'], badge_end, name)

    def test_no_step_is_advertised_that_nothing_plays(self):
        # A `word` step sat in TIMING for a day with no code reading it, and the tests
        # asserted its presence as though that were behaviour. These are the only names the
        # Qt layer consumes: `letter` in `review_popup.letter_motion_allowed` (witnessed by
        # windows-card-motion §1, the box visibly leaves home and returns), `badge` and
        # `confetti` in `Celebration.play` / `_paint_confetti` (witnessed by §3 for the badge
        # and §6 for the confetti flag). `slip` is deliberately absent — it fires per
        # keystroke and `motion_view.shake` reads its numbers directly.
        self.assertEqual({step['name'] for step in motion.timeline(1, FULL)},
                         {'letter', 'badge', 'confetti'})
        self.assertEqual({step['name'] for step in motion.timeline(4, FULL)},
                         {'letter', 'badge'})
        self.assertEqual(set(motion.TIMING), {'letter', 'slip', 'badge', 'confetti'})

    def test_the_slip_step_is_the_wrong_letter_shake(self):
        self.assertNotIn('slip', {step['name'] for step in motion.timeline(1, FULL)})
        self.assertEqual(motion.TIMING['slip']['swing'], 5)
        self.assertEqual(motion.TIMING['letter']['rise'], 11)

    def test_timings_match_the_approved_mockup(self):
        steps = {step['name']: step for step in motion.timeline(1, FULL)}
        self.assertEqual(steps['letter']['duration'], 180)
        self.assertEqual(steps['badge']['in_ms'], 260)
        self.assertEqual(steps['badge']['hold_ms'], 520)
        self.assertEqual(steps['badge']['out_ms'], 200)
        self.assertEqual(steps['confetti']['duration'], 900)


class BadgePose(unittest.TestCase):
    """The choreography, as numbers. `candy_badge` only applies these; it owns no timing."""

    def pose(self, progress, tier=1):
        return motion.badge_pose(progress, tier, motion.TIMING['badge']['duration'])

    def test_it_settles_exactly_still_at_rest(self):
        for tier in (1, 2, 3, 4):
            pose = self.pose(0.55, tier)
            self.assertAlmostEqual(pose['scale'], 1.0, places=6)
            self.assertAlmostEqual(pose['angle'], 0.0, places=6)
            self.assertEqual(pose['opacity'], 1.0)
            self.assertEqual(pose['ribbon'], 1.0)

    def test_it_overshoots_before_it_settles(self):
        # A game pop that goes straight to 1.0 reads as a dialog opening. The scale has to
        # pass through something bigger than rest on its way in.
        peak = max(self.pose(step / 40.0)['scale'] for step in range(0, 12))
        self.assertGreater(peak, 1.05)
        self.assertLess(self.pose(0.0)['scale'], 0.5)

    def test_it_starts_turned_and_ends_straight(self):
        self.assertLess(self.pose(0.0)['angle'], -10.0)
        self.assertAlmostEqual(self.pose(0.4)['angle'], 0.0, places=3)

    def test_the_ribbon_lags_the_word(self):
        # The word slams in first and the ribbon slides after it; if both arrive together the
        # whole object pops as one flat sticker instead of assembling.
        early = self.pose(0.12)
        self.assertGreater(early['opacity'], early['ribbon'])
        self.assertLess(early['ribbon'], 0.5)

    def test_it_leaves_by_fading_not_by_cutting(self):
        last = self.pose(1.0)
        self.assertEqual(last['opacity'], 0.0)
        self.assertGreater(last['scale'], 1.0)      # it grows slightly as it goes
        # The exit owns the last 200ms of 980, i.e. progress from 0.796; just inside it the
        # badge must still be nearly whole, and it must never vanish between two frames.
        self.assertGreater(self.pose(0.82)['opacity'], 0.8)
        self.assertGreater(self.pose(0.90)['opacity'], 0.4)
        self.assertLess(self.pose(0.97)['opacity'], 0.2)

    def test_no_pose_value_is_ever_out_of_range(self):
        for step in range(0, 41):
            pose = self.pose(step / 40.0, 1 + step % 4)
            for name in ('opacity', 'glow', 'ribbon'):
                self.assertGreaterEqual(pose[name], 0.0, (step, name))
                self.assertLessEqual(pose[name], 1.0, (step, name))
            self.assertGreater(pose['scale'], 0.0)

    def test_every_tier_has_its_own_word(self):
        for tier in TIERS:
            self.assertTrue(motion.tier_caption(tier))
        self.assertEqual(motion.tier_caption(1), 'UNBELIEVABLE')
        self.assertEqual(motion.tier_caption(4), 'NICE')


class MotionSwitches(unittest.TestCase):
    """The two switches, and reading a machine that still holds the old three-way value."""

    def test_explicit_switches_win_over_the_legacy_radio(self):
        self.assertEqual((motion.hop_allowed({'review_motion': 'off',
                                              'review_motion_hop': True}),
                          motion.celebration_allowed({'review_motion': 'off',
                                                      'review_motion_celebration': True})),
                         (True, True))

    def test_a_legacy_value_migrates_instead_of_switching_the_badge_off(self):
        # Someone who had chosen 关闭动效 must not wake up to a pop-up, and someone who never
        # opened the settings page must not lose it.
        self.assertEqual((motion.hop_allowed({'review_motion': 'off'}),
                          motion.celebration_allowed({'review_motion': 'off'})), (False, False))
        for legacy in ('full', 'calm'):
            self.assertEqual((motion.hop_allowed({'review_motion': legacy}),
                              motion.celebration_allowed({'review_motion': legacy})),
                             (True, True), legacy)

    def test_an_absent_or_bogus_config_defaults_to_both_switches_on(self):
        for cfg in ({}, {'review_motion': None}, {'review_motion': 'everything please'},
                    {'review_motion_hop': None, 'review_motion_celebration': None}):
            self.assertTrue(motion.hop_allowed(cfg), cfg)
            self.assertTrue(motion.celebration_allowed(cfg), cfg)

    def test_mode_is_still_readable_for_any_older_caller(self):
        self.assertEqual(motion.mode(FULL), 'full')
        self.assertEqual(motion.mode(HOP_ONLY), 'calm')
        self.assertEqual(motion.mode(NOTHING), 'off')


class WhereTheBadgeLands(unittest.TestCase):
    """The anchor must know where the word is. It used to know only the card's height.

    Measured on the real machine (2026-11-05): at the fixed `height × 0.50` the badge's
    topmost pixel cleared the answer word by 2 px on tier 3, and the confetti on tiers 1-2
    fell straight through the word row — 216 changed pixels per frame, in 38 of the day's
    168 celebrations.
    """

    CARD = 687
    WORD_ROW = (90, 142)
    GRADE_ROW = (454, 490)

    def test_the_footprint_never_touches_a_protected_row(self):
        for rows in ((self.WORD_ROW,), (self.WORD_ROW, self.GRADE_ROW), ()):
            for footprint in (120, 200, 260):
                y, fit = motion.badge_anchor(self.CARD, footprint, rows)
                top, bottom = y - footprint * fit / 2.0, y + footprint * fit / 2.0
                for row_top, row_bottom in rows:
                    self.assertTrue(bottom <= row_top or top >= row_bottom,
                                    (rows, footprint, y, fit, top, bottom))

    def test_it_uses_the_largest_free_band(self):
        y, fit = motion.badge_anchor(self.CARD, 200, (self.WORD_ROW, self.GRADE_ROW))
        self.assertEqual(fit, 1.0)
        self.assertEqual(y, (142 + 454) / 2.0)

    def test_a_card_too_short_for_the_badge_shrinks_it_instead_of_covering_the_word(self):
        y, fit = motion.badge_anchor(300, 200, (self.WORD_ROW,))
        self.assertLess(fit, 1.0, 'there is no room at full size, so it must shrink')
        self.assertGreaterEqual(fit, motion.MIN_BADGE_FIT)
        self.assertGreaterEqual(y + fit * 200 / 2.0, 142, 'the band it chose is the lower one')

    def test_no_protected_rows_leaves_the_centre_alone(self):
        self.assertEqual(motion.badge_anchor(600, 200, ()), (300.0, 1.0))

    def test_clearance_is_paid_even_when_the_band_is_exactly_the_size(self):
        y, fit = motion.badge_anchor(142 + 200 + 2 * motion.BADGE_CLEARANCE, 200,
                                     (self.WORD_ROW,))
        self.assertGreaterEqual(y - 100, 142 + motion.BADGE_CLEARANCE)


class WhereThePaperFalls(unittest.TestCase):
    def test_confetti_starts_under_the_word_row(self):
        top, fall = motion.confetti_span(687, 142)
        self.assertGreater(top, 142, 'paper must not cross the word it is celebrating')
        self.assertEqual(fall, 687 - top)

    def test_without_a_word_row_the_old_start_is_kept(self):
        top, _fall = motion.confetti_span(687, None)
        self.assertLess(top, 0, 'paper may still enter from above the card')

    def test_a_short_card_still_gives_the_paper_somewhere_to_fall(self):
        top, fall = motion.confetti_span(200, 150)
        self.assertGreater(fall, 0)
        self.assertGreaterEqual(top + fall, 200)


if __name__ == '__main__':
    unittest.main()
