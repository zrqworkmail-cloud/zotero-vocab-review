"""The shipped mnemonic table: its shape, its lookup, and who wins when both exist.

Why these three: the learner asked for a root decomposition + a memory trick on every word
(2026-11-06). The honest answer was that the data already exists on disk under a BSD licence
and covers 2615 of the 5211 notes in 《六级全表》 (counted over the whole book) — so the code
must (a) read that table correctly, (b) never show a block for a word it does not have, and
(c) never overwrite a note field the learner wrote himself.
"""
import importlib.util
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'anki-global-addon/zotero_global_capture/review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
TABLE = path.parent / 'lexicon' / 'mnemonics.tsv'


def note(**fields):
    return {'fields': {name: {'value': value} for name, value in fields.items()}}


class TableShape(unittest.TestCase):
    def setUp(self):
        self.lines = TABLE.read_text(encoding='utf-8').splitlines()

    def test_every_row_is_a_word_and_a_value(self):
        for line in self.lines:
            parts = line.split('\t')
            self.assertGreaterEqual(len(parts), 2, line)
            self.assertTrue(parts[0].strip() and parts[1].strip(), line)

    def test_words_are_unique_and_sorted(self):
        words = [line.split('\t')[0] for line in self.lines]
        self.assertEqual(len(words), len(set(words)), 'duplicate word in the table')
        self.assertEqual(words, sorted(words), 'table must be sorted so diffs stay readable')

    def test_values_are_plain_text_not_html(self):
        # Note fields arrive HTML-escaped from Anki; this file is read raw, so mixing markup
        # in would render as literal tags on the card.
        for line in self.lines:
            self.assertNotIn('<', line.split('\t', 1)[1], line[:30])

    def test_the_source_licence_ships_next_to_it(self):
        self.assertTrue((path.parent / 'lexicon' / 'KYLEBING_LICENSE').exists(),
                        'BSD-3-Clause data must ship with its notice')


class Lookup(unittest.TestCase):
    def test_a_known_word_returns_its_decomposition(self):
        value = module.mnemonic_for('rebellion')
        self.assertIn('bell', value)
        self.assertIn('re', value)

    def test_case_and_padding_do_not_matter(self):
        self.assertEqual(module.mnemonic_for('  REBELLION '), module.mnemonic_for('rebellion'))

    def test_unknown_and_empty_words_get_nothing(self):
        for word in ('zzznotaword', '', None, '   '):
            self.assertEqual(module.mnemonic_for(word), '')


class WhoseTextWins(unittest.TestCase):
    def test_the_note_field_beats_the_table(self):
        card = note(**{'识记方法': '我自己写的拆法'})
        self.assertEqual(module.question_mnemonic(card, 'rebellion'), '我自己写的拆法')

    def test_a_blank_note_field_falls_back_to_the_table(self):
        for blank in ('', '   ', '<br>'):
            card = note(**{'识记方法': blank})
            self.assertEqual(module.question_mnemonic(card, 'rebellion'),
                             module.mnemonic_for('rebellion'), blank)

    def test_no_field_and_no_table_row_means_no_block(self):
        self.assertEqual(module.question_mnemonic(note(**{'识记方法': ''}), 'zzznotaword'), '')


if __name__ == '__main__':
    unittest.main()
