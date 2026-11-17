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
