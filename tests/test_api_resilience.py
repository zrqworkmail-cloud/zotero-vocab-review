"""The local AnkiConnect call must survive a brief localhost hiccup.

2026-11-07 15:19 the runtime log showed `review preparation failed: URLError` and
`review save failed: URLError`; one rating was lost while AnkiConnect was healthy
again seconds later. The call therefore has to bypass the system proxy explicitly,
retry a transient connection failure a bounded number of times, and leave the real
reason in the runtime log instead of only the exception class.
"""
import ast
import json
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'anki-global-addon' / 'zotero_global_capture' / '__init__.py'


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def load_api(events):
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'api')
    scope = {'json': json, 'urllib': urllib, 'time': time, 'log_runtime': events.append}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), scope)
    return scope['api']


class ApiResilience(unittest.TestCase):
    def test_a_transient_connection_failure_is_retried_until_it_succeeds(self):
        events = []
        api = load_api(events)
        opener = mock.Mock()
        opener.open.side_effect = [
            urllib.error.URLError('connection refused'),
            urllib.error.URLError('connection reset'),
            FakeResponse({'result': 6, 'error': None}),
        ]
        with mock.patch('urllib.request.build_opener', return_value=opener), \
             mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('old path')), \
             mock.patch('time.sleep'):
            try:
                result = api('version')
            except urllib.error.URLError:
                self.fail('api must retry a transient URLError instead of giving up on the first one')
        self.assertEqual(result, 6)
        self.assertEqual(opener.open.call_count, 3)

    def test_the_final_failure_logs_the_action_and_the_real_reason(self):
        events = []
        api = load_api(events)
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.URLError('connection refused')
        with mock.patch('urllib.request.build_opener', return_value=opener), \
             mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('old path')), \
             mock.patch('time.sleep'):
            with self.assertRaises(urllib.error.URLError):
                api('findCards')
        self.assertEqual(opener.open.call_count, 3)
        self.assertTrue(any('findCards' in line and 'connection refused' in line for line in events),
                        events)

    def test_the_request_bypasses_the_system_proxy_explicitly(self):
        events = []
        api = load_api(events)
        opener = mock.Mock()
        opener.open.return_value = FakeResponse({'result': 6, 'error': None})
        with mock.patch('urllib.request.build_opener', return_value=opener) as build, \
             mock.patch('urllib.request.urlopen', return_value=FakeResponse({'result': 6, 'error': None})), \
             mock.patch('time.sleep'):
            api('version')
        self.assertTrue(build.called, 'the local call must build an explicit opener')
        for call in build.call_args_list:
            handler = call.args[0]
            self.assertIsInstance(handler, urllib.request.ProxyHandler)
            self.assertEqual(handler.proxies, {})

    def test_an_anki_error_is_not_retried(self):
        events = []
        api = load_api(events)
        opener = mock.Mock()
        opener.open.return_value = FakeResponse({'result': None, 'error': 'deck missing'})
        with mock.patch('urllib.request.build_opener', return_value=opener), \
             mock.patch('urllib.request.urlopen', return_value=FakeResponse({'result': None, 'error': 'deck missing'})), \
             mock.patch('time.sleep'):
            with self.assertRaises(RuntimeError):
                api('deckNames')
        self.assertEqual(opener.open.call_count, 1)

    def test_an_http_error_is_not_retried(self):
        events = []
        api = load_api(events)
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError('http://127.0.0.1:8765', 500, 'boom', {}, None)
        with mock.patch('urllib.request.build_opener', return_value=opener), \
             mock.patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError('http://127.0.0.1:8765', 500, 'boom', {}, None)), \
             mock.patch('time.sleep'):
            with self.assertRaises(urllib.error.HTTPError):
                api('version')
        self.assertEqual(opener.open.call_count, 1)


if __name__ == '__main__':
    unittest.main()