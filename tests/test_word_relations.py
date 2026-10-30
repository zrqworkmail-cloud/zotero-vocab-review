import importlib.util
import sys
import types
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
pkg = types.ModuleType('zvr_relations_test')
pkg.__path__ = [str(root)]
sys.modules[pkg.__name__] = pkg
spec = importlib.util.spec_from_file_location('zvr_relations_test.word_relations', root / 'word_relations.py')
relations = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relations)

class WordRelationsTests(unittest.TestCase):
    def test_candidates_prioritize_exam_words_and_use_brief_glosses(self):
        candidates = relations.candidate_words('n. 测试：effect, affect；affect\nvi. impact', 'test')
        self.assertEqual(candidates, ['effect', 'affect', 'impact'])
        self.assertEqual(relations.select_candidates(candidates, {'impact', 'affect'}, 2), ['affect', 'impact'])
        self.assertEqual(relations.brief_meaning('n. 影响；作用\nZotero 收录次数：2'), 'n. 影响')
        self.assertEqual(relations.brief_meaning(''), '')

    def test_antonyms_keep_part_of_speech_and_deduplicate(self):
        data = [{'meanings': [{'partOfSpeech': 'adjective', 'antonyms': ['sad'],
                               'definitions': [{'antonyms': ['sad', 'unhappy']}]}]}]
        self.assertEqual(relations.parse_antonyms(data), [('adjective', 'sad'), ('adjective', 'unhappy')])
        self.assertEqual(relations.parse_antonyms({'error': 'missing'}), [])
        self.assertEqual(relations.parse_words([{'meanings': [{'partOfSpeech': 'verb', 'synonyms': ['use'], 'definitions': []}]}], 'synonyms'), [('verb', 'use')])

    def test_similar_words_are_distinct_real_words(self):
        words = relations.similar_words('affect')
        self.assertIn('effect', words)
        self.assertNotIn('affect', words)
        self.assertTrue(all(word in relations._inflection_table() for word in words))
        self.assertEqual(relations.similar_words('a long phrase'), [])
