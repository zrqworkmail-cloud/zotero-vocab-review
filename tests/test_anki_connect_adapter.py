import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'anki_connect.py'
spec = importlib.util.spec_from_file_location('anki_connect_adapter', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake(action, params=None, **kwargs):
            self.calls.append((action, params, kwargs))
            return {'action': action, 'params': params}

        self.adapter = module.AnkiConnectAdapter(fake)

    def test_call_is_transparent(self):
        result = self.adapter('findNotes', {'query': 'deck:"CET"'})
        self.assertEqual(result, {'action': 'findNotes', 'params': {'query': 'deck:"CET"'}})
        self.assertEqual(self.calls, [('findNotes', {'query': 'deck:"CET"'}, {})])

    def test_empty_params_become_a_dict(self):
        self.adapter('deckNames')
        self.assertEqual(self.calls[-1], ('deckNames', {}, {}))

    def test_optional_timeout_is_forwarded(self):
        self.adapter('version', {}, timeout=2)
        self.assertEqual(self.calls[-1], ('version', {}, {'timeout': 2}))

    def test_multi_wraps_actions(self):
        actions = [{'action': 'deckNames', 'params': {}}]
        self.adapter.multi(actions)
        self.assertEqual(self.calls[-1], ('multi', {'actions': actions}, {}))

    def test_answer_card_uses_the_public_action(self):
        self.adapter.answer_card(42, 3)
        self.assertEqual(self.calls[-1],
                         ('answerCards', {'answers': [{'cardId': 42, 'ease': 3}]}, {}))
        self.assertEqual([call[0] for call in self.calls], ['answerCards'])

    def test_elapsed_answer_uses_json_rpc_scheduling(self):
        rpc_calls = []

        def rpc(method, params=None, **kwargs):
            rpc_calls.append((method, params))
            if method == 'scheduling.predict':
                return {'stateToken': 'token-1'}
            if method == 'scheduling.answer':
                return {'cardId': '42'}
            raise AssertionError(method)

        adapter = module.AnkiConnectAdapter(lambda action, params=None, **kwargs: None, rpc=rpc)
        self.assertEqual(adapter.answer_card(42, 3, elapsed_ms=1250), [True])
        self.assertEqual([call[0] for call in rpc_calls],
                         ['scheduling.predict', 'scheduling.answer'])
        self.assertEqual(rpc_calls[0][1], {'cardId': '42'})
        self.assertEqual(rpc_calls[1][1], {'cardId': '42', 'rating': 'good',
                                           'stateToken': 'token-1', 'elapsedMs': 1250})

    def test_stale_token_retries_after_revlog_confirms_no_write(self):
        reviews = {'42': []}
        rpc_calls = []
        tokens = ['token-1', 'token-2']
        answers = [0]

        def rpc(method, params=None, **kwargs):
            rpc_calls.append((method, params))
            if method == 'scheduling.predict':
                return {'stateToken': tokens.pop(0)}
            if method == 'scheduling.answer':
                answers[0] += 1
                if answers[0] == 1:
                    raise RuntimeError(module.STALE_TOKEN_MESSAGE)
                return {'cardId': '42', 'reviewId': '101'}
            raise AssertionError(method)

        def request(action, params=None, **kwargs):
            if action == 'getReviewsOfCards':
                return {key: list(value) for key, value in reviews.items()}
            raise AssertionError(action)

        adapter = module.AnkiConnectAdapter(request, rpc=rpc)
        self.assertEqual(adapter.answer_card(42, 3, elapsed_ms=1250), [True])
        self.assertEqual(answers[0], 2)
        self.assertEqual([call[0] for call in rpc_calls],
                         ['scheduling.predict', 'scheduling.answer',
                          'scheduling.predict', 'scheduling.answer'])

    def test_stale_token_does_not_retry_when_revlog_has_new_entry(self):
        reviews = {'42': [{'id': 100}]}
        rpc_calls = []
        answers = [0]

        def rpc(method, params=None, **kwargs):
            rpc_calls.append((method, params))
            if method == 'scheduling.predict':
                return {'stateToken': 'token-1'}
            if method == 'scheduling.answer':
                answers[0] += 1
                reviews['42'].append({'id': 101})
                raise RuntimeError(module.STALE_TOKEN_MESSAGE)
            raise AssertionError(method)

        def request(action, params=None, **kwargs):
            if action == 'getReviewsOfCards':
                return {key: list(value) for key, value in reviews.items()}
            raise AssertionError(action)

        adapter = module.AnkiConnectAdapter(request, rpc=rpc)
        self.assertEqual(adapter.answer_card(42, 3, elapsed_ms=1250), [True])
        self.assertEqual(answers[0], 1)
        self.assertEqual([call[0] for call in rpc_calls],
                         ['scheduling.predict', 'scheduling.answer'])

    def test_non_stale_error_is_recovered_only_from_the_revlog(self):
        reviews = {'42': [{'id': 100}]}
        answers = [0]

        def rpc(method, params=None, **kwargs):
            if method == 'scheduling.predict':
                return {'stateToken': 'token-1'}
            if method == 'scheduling.answer':
                answers[0] += 1
                reviews['42'].append({'id': 101})
                raise RuntimeError('transport failed after the write')
            raise AssertionError(method)

        def request(action, params=None, **kwargs):
            if action == 'getReviewsOfCards':
                return {key: list(value) for key, value in reviews.items()}
            raise AssertionError(action)

        adapter = module.AnkiConnectAdapter(request, rpc=rpc)
        self.assertEqual(adapter.answer_card(42, 3, elapsed_ms=1250), [True])
        self.assertEqual(answers[0], 1)

    def test_non_stale_error_without_a_new_review_is_raised(self):
        reviews = {'42': [{'id': 100}]}
        answers = [0]

        def rpc(method, params=None, **kwargs):
            if method == 'scheduling.predict':
                return {'stateToken': 'token-1'}
            if method == 'scheduling.answer':
                answers[0] += 1
                raise RuntimeError('This card cannot be answered outside the reviewer.')
            raise AssertionError(method)

        def request(action, params=None, **kwargs):
            if action == 'getReviewsOfCards':
                return {key: list(value) for key, value in reviews.items()}
            raise AssertionError(action)

        adapter = module.AnkiConnectAdapter(request, rpc=rpc)
        with self.assertRaisesRegex(RuntimeError, 'reviewer'):
            adapter.answer_card(42, 3, elapsed_ms=1250)
        self.assertEqual(answers[0], 1)

    def test_retry_without_a_new_revlog_is_bounded_to_one_attempt(self):
        reviews = {'42': []}
        answers = [0]

        def rpc(method, params=None, **kwargs):
            if method == 'scheduling.predict':
                return {'stateToken': 'token-1'}
            if method == 'scheduling.answer':
                answers[0] += 1
                raise RuntimeError(module.STALE_TOKEN_MESSAGE)
            raise AssertionError(method)

        def request(action, params=None, **kwargs):
            if action == 'getReviewsOfCards':
                return {key: list(value) for key, value in reviews.items()}
            raise AssertionError(action)

        adapter = module.AnkiConnectAdapter(request, rpc=rpc)
        with self.assertRaises(RuntimeError):
            adapter.answer_card(42, 3, elapsed_ms=1250)
        self.assertEqual(answers[0], 2)

    def test_answer_without_review_id_requires_a_new_revlog_entry(self):
        reads = [0]

        def request(action, params=None, **kwargs):
            if action == 'getReviewsOfCards':
                reads[0] += 1
                return {'42': [] if reads[0] == 1 else [{'id': 101}]}
            raise AssertionError(action)

        def rpc(method, params=None, **kwargs):
            if method == 'scheduling.predict':
                return {'stateToken': 'token-1'}
            if method == 'scheduling.answer':
                return {'cardId': '42'}
            raise AssertionError(method)

        adapter = module.AnkiConnectAdapter(request, rpc=rpc)
        self.assertEqual(adapter.answer_card(42, 3, elapsed_ms=1250), [True])

    def test_returned_review_id_must_be_newer_than_the_baseline(self):
        def request(action, params=None, **kwargs):
            if action == 'getReviewsOfCards':
                return {'42': [{'id': 100}]}
            raise AssertionError(action)

        def rpc(method, params=None, **kwargs):
            if method == 'scheduling.predict':
                return {'stateToken': 'token-1'}
            if method == 'scheduling.answer':
                return {'cardId': '42', 'reviewId': '100'}
            raise AssertionError(method)

        adapter = module.AnkiConnectAdapter(request, rpc=rpc)
        self.assertEqual(adapter.answer_card(42, 3, elapsed_ms=1250), [False])

    def test_answer_without_a_review_id_or_revlog_entry_is_not_success(self):
        def request(action, params=None, **kwargs):
            if action == 'getReviewsOfCards':
                return {'42': []}
            raise AssertionError(action)

        def rpc(method, params=None, **kwargs):
            if method == 'scheduling.predict':
                return {'stateToken': 'token-1'}
            if method == 'scheduling.answer':
                return {'cardId': '42'}
            raise AssertionError(method)

        adapter = module.AnkiConnectAdapter(request, rpc=rpc)
        self.assertEqual(adapter.answer_card(42, 3, elapsed_ms=1250), [False])

    def test_a_failed_prediction_falls_back_before_writing(self):
        def rpc(method, params=None, **kwargs):
            raise RuntimeError('json-rpc unavailable')

        adapter = module.AnkiConnectAdapter(
            lambda action, params=None, **kwargs: self.calls.append((action, params, kwargs)), rpc=rpc)
        self.assertIsNone(adapter.answer_card(42, 3, elapsed_ms=1250))
        self.assertEqual(self.calls[-1],
                         ('answerCards', {'answers': [{'cardId': 42, 'ease': 3}]}, {}))

    def test_request_alias(self):
        self.adapter.request('getActiveProfile')
        self.assertEqual(self.calls[-1], ('getActiveProfile', {}, {}))

    def test_rejects_non_callable(self):
        with self.assertRaises(TypeError):
            module.AnkiConnectAdapter(None)

    def test_read_only_queries_are_assembled_here(self):
        book = {'tag': 'CET6'}
        self.adapter.suspended_card_ids([{'book': book, 'tags': []}])
        self.assertEqual(self.calls[-1][0], 'findCards')
        self.assertEqual(self.calls[-1][1], {'query': 'is:suspended tag:"CET6"'})
        self.adapter.due_card_ids()
        self.assertEqual(self.calls[-1][1], {'query': 'is:due'})
        self.adapter.due_card_ids([{'book': book, 'tags': []}])
        self.assertEqual(self.calls[-1][1], {'query': 'is:due tag:"CET6"'})

    def test_progress_counts_returns_learned_then_total(self):
        calls = []

        def fake(action, params=None, **kwargs):
            calls.append((action, params, kwargs))
            if action == 'multi':
                return [[10, 11], [10]]
            return []

        adapter = module.AnkiConnectAdapter(fake)
        self.assertEqual(adapter.progress_counts('CET', [{'book': {'tag': 'CET6'}, 'tags': []}]),
                         (1, 2))
        self.assertEqual(calls[0][0], 'multi')
        queries = [item['params']['query'] for item in calls[0][1]['actions']]
        self.assertEqual(queries[0], 'note:"CET" tag:"CET6" -is:suspended -is:buried')
        self.assertTrue(queries[1].endswith(' prop:reps>0'))

    def test_progress_counts_falls_back_without_multi(self):
        seen = []

        def fake(action, params=None, **kwargs):
            seen.append(action)
            if action == 'multi':
                raise RuntimeError('no batching')
            return [1]

        adapter = module.AnkiConnectAdapter(fake)
        self.assertEqual(adapter.progress_counts('CET', []), (1, 1))
        self.assertEqual(seen, ['multi', 'findCards', 'findCards'])

    def test_tag_and_untagged_queries_are_assembled_here(self):
        book = {'tag': 'CET6'}
        self.adapter.tag_card_ids(book, ['A', 'B'])
        self.assertEqual(self.calls[-1][0], 'multi')
        self.assertEqual([item['params']['query'] for item in self.calls[-1][1]['actions']],
                         [' tag:"CET6" tag:"A"', ' tag:"CET6" tag:"B"'])
        self.adapter.untagged_card_ids(book, ['A', 'B'])
        self.assertEqual(self.calls[-1][1],
                         {'query': ' tag:"CET6" -tag:"A" -tag:"B"'})


if __name__ == '__main__':
    unittest.main()
