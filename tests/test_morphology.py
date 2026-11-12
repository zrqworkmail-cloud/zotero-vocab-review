import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'morphology.py'
spec = importlib.util.spec_from_file_location('morphology', MODULE)
morphology = importlib.util.module_from_spec(spec)
spec.loader.exec_module(morphology)


class MemoryAidTests(unittest.TestCase):
    def test_dictionary_syllables_reassemble_and_are_not_called_roots(self):
        label, pieces = morphology.spelling_chunks('maintenance')
        self.assertEqual(label, '音节分段')
        self.assertEqual(''.join(pieces).lower(), 'maintenance')
        self.assertGreater(len(pieces), 1)

    def test_unknown_long_word_shows_nothing(self):
        # The mechanical 4-letter grouping (disi·llus·ion) taught a fake pronunciation;
        # a word the syllable sources do not cover must show no division at all.
        self.assertIsNone(morphology.spelling_chunks('abcdefghijklmno'))

    def test_supplemented_book_word_gets_real_syllables(self):
        # disillusion was one of the 104 shipped-book words the 25k list missed; the
        # supplement (full Moby Hyphenator II) must cover it with the same written breaks.
        label, pieces = morphology.spelling_chunks('disillusion')
        self.assertEqual(label, '音节分段')
        self.assertEqual(pieces, ['dis', 'il', 'lu', 'sion'])

    def test_single_syllable_word_is_not_split(self):
        # strength is one syllable: no source divides it, so it shows nothing.
        self.assertIsNone(morphology.spelling_chunks('strength'))

    def test_short_and_nonword_input_has_no_artificial_breakdown(self):
        self.assertIsNone(morphology.spelling_chunks('cat'))
        self.assertIsNone(morphology.spelling_chunks('hi there'))

    def test_existing_curated_root_explanations_are_preserved(self):
        self.assertIn('chron', morphology.breakdown('asynchrony'))
        self.assertEqual(morphology.breakdown('abcdefghijklmno'), '')

    def test_confusable_words_have_the_same_explanation_in_both_directions(self):
        self.assertEqual(morphology.confusion('affect'), morphology.confusion('effect'))
        self.assertIn('影响', morphology.confusion('affect'))
        self.assertEqual(morphology.confusion('zzzxxyyqq'), '')

if __name__ == '__main__': unittest.main()
