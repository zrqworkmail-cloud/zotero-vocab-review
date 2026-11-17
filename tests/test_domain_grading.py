import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
spec = importlib.util.spec_from_file_location('domain_grading', ROOT / 'domain' / 'grading.py')
grading = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grading)

logic_spec = importlib.util.spec_from_file_location('review_logic_grading_compat', ROOT / 'review_logic.py')
logic = importlib.util.module_from_spec(logic_spec)
logic_spec.loader.exec_module(logic)


class HintMath(unittest.TestCase):
    def test_letter_weight_falls_off_by_position(self):
        self.assertEqual(grading.letter_weight(0), 1.0)
        self.assertEqual(grading.letter_weight(1), 0.5)
        self.assertEqual(grading.letter_weight(3), 0.25)

    def test_hint_share_is_position_weighted(self):
        self.assertEqual(grading.hint_share(set(), 14), 0.0)
        self.assertAlmostEqual(grading.hint_share({0}, 14), 0.30754, places=4)
        self.assertAlmostEqual(grading.hint_share({13}, 14), 0.02195, places=4)
        self.assertEqual(grading.hint_share({0, 1, 2, 3, 4}, 5), 1.0)
        self.assertEqual(grading.hint_share({99}, 5), 0.0)
        self.assertEqual(grading.hint_share({0}, 0), 0.0)

    def test_ease_bands_are_unchanged(self):
        self.assertEqual(grading.ease_from_hint_share(0.0), 4)
        self.assertEqual(grading.ease_from_hint_share(0.20), 4)
        self.assertEqual(grading.ease_from_hint_share(0.21), 3)
        self.assertEqual(grading.ease_from_hint_share(0.40), 3)
        self.assertEqual(grading.ease_from_hint_share(0.41), 2)
        self.assertEqual(grading.ease_from_hint_share(0.70), 2)
        self.assertEqual(grading.ease_from_hint_share(0.71), 1)


class CompatibilityExports(unittest.TestCase):
    def test_review_logic_keeps_old_names_and_values(self):
        self.assertAlmostEqual(logic.hint_share({0}, 14), 0.30754, places=4)
        self.assertEqual(logic.ease_from_hint_share(0.21), 3)
        self.assertEqual(logic.letter_weight(1), 0.5)


if __name__ == '__main__':
    unittest.main()
