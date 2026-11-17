import importlib.util
import sys
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'review_request.py'
spec = importlib.util.spec_from_file_location('review_request', MODULE)
review_request = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = review_request
spec.loader.exec_module(review_request)


class ReviewRequestTests(unittest.TestCase):
    def test_legacy_cfg_is_read_once(self):
        cfg = {
            '_review_exclude_card': 7,
            '_review_exclude_cards': {7, 8},
            '_review_exclude_words': {'alpha'},
            '_review_recent_words': {'beta'},
            '_review_group': (2, 6),
            '_review_inflight_new': 1,
            '_review_inflight_due': 0,
            '_review_prefetch': True,
            '_capture_lookup_cache': {'captures': {'alpha': 1}},
            '_book_decks': ['Deck'],
            '_book_decks_key': 'book',
        }
        request = review_request.ReviewRequest.from_cfg(cfg)
        self.assertEqual(request.exclude_card, 7)
        self.assertEqual(request.exclude_cards, frozenset({7, 8}))
        self.assertEqual(request.exclude_words, frozenset({'alpha'}))
        self.assertEqual(request.recent_words, frozenset({'beta'}))
        self.assertEqual((request.group_position, request.group_size), (2, 6))
        self.assertEqual((request.inflight_new, request.inflight_due), (1, 0))
        self.assertTrue(request.prefetch)
        self.assertEqual(request.book_decks, ['Deck'])
        self.assertEqual(request.book_decks_key, 'book')

    def test_explicit_request_wins_over_legacy_keys(self):
        request = review_request.ReviewRequest(exclude_card=3, group_size=9)
        cfg = {'_review': request, '_review_exclude_card': 99, '_review_group': (8, 8)}
        self.assertIs(review_request.request_for(cfg), request)
        self.assertEqual(review_request.request_for(cfg).exclude_card, 3)
        self.assertEqual(review_request.request_for(cfg).group_size, 9)

    def test_ensure_request_installs_on_the_call_dict_only(self):
        cfg = {'_review_exclude_words': {'alpha'}}
        installed = review_request.ensure_request(cfg)
        self.assertIs(cfg['_review'], installed)
        self.assertEqual(installed.exclude_words, frozenset({'alpha'}))
        self.assertNotIn('_review', {})

    def test_updated_returns_a_copy(self):
        original = review_request.ReviewRequest(group_position=1)
        changed = original.updated(group_position=2)
        self.assertEqual(original.group_position, 1)
        self.assertEqual(changed.group_position, 2)


if __name__ == '__main__':
    unittest.main()
