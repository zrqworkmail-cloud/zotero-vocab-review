"""The mixed new/due order: who gets the slot, and what happens when a queue is empty.

Live numbers that made this necessary (2026-11-06): the deck held 365 new cards still
allowed today, 250 cards sitting in Anki's learning steps and 27 mature reviews. Under
"new first, reviews after today's quota" the learning steps were pushed behind roughly 37
groups -- a 10-minute step silently becoming tomorrow. The learner chose a fixed share per
group instead, so these tests pin the share, the fallbacks, and the fact that a small group
is not forced to spend a slot it does not have.
"""
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'anki-global-addon/zotero_global_capture/review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic', path)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)


class DueSlots(unittest.TestCase):
    def test_a_group_of_ten_spends_two_slots_on_old_cards(self):
        self.assertEqual(logic.due_slots_for(10, 500), 2)

    def test_the_share_floors_so_small_groups_are_not_forced(self):
        self.assertEqual(logic.due_slots_for(4, 500), 0)
        self.assertEqual(logic.due_slots_for(5, 500), 1)

    def test_it_never_promises_more_than_exist(self):
        self.assertEqual(logic.due_slots_for(10, 1), 1)
        self.assertEqual(logic.due_slots_for(10, 0), 0)

    def test_a_missing_group_size_means_no_old_cards(self):
        self.assertEqual(logic.due_slots_for(0, 500), 0)


class WhichQueue(unittest.TestCase):
    def test_the_first_two_of_a_group_are_due_then_new(self):
        order = [logic.queue_order(position, 10, 500, 365) for position in range(10)]
        self.assertEqual(order, ['due', 'due'] + ['new'] * 8)

    def test_when_the_due_pile_empties_the_group_goes_back_to_new(self):
        self.assertEqual(logic.queue_order(0, 10, 0, 365), 'new')

    def test_when_new_quota_runs_out_everything_is_due(self):
        self.assertEqual([logic.queue_order(p, 10, 500, 0) for p in range(10)],
                         ['due'] * 10)

    def test_due_only_never_touches_the_new_queue(self):
        self.assertEqual(logic.queue_order(0, 10, 0, 365, due_only=True), 'due',
                         'due_only must still ask for the due queue even with nothing '
                         'promised -- the caller falls back, the loop must not skip it')

    def test_a_group_smaller_than_the_share_stays_new(self):
        self.assertEqual(logic.queue_order(0, 3, 500, 365), 'new')


if __name__ == '__main__':
    unittest.main()
