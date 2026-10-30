import ast
import html
import json
import re
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch


class DictionaryParsingTests(unittest.TestCase):
    def test_list_valued_dictionary_definitions_are_text_not_python_repr(self):
        path = Path(__file__).resolve().parents[1] / 'anki-global-addon/zotero_global_capture/__init__.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        definition = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'dictionary')
        scope = {'urllib': urllib, 'json': json, 're': re, 'html': html}
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), 'exec'), scope)
        payload = {'ec': {'word': [{'trs': [{'pos': 'vt.', 'tr': [{'l': {'i': ['加强', '巩固']}}]}]}]}}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(payload).encode()
        with patch('urllib.request.urlopen', return_value=Response()):
            result = scope['dictionary']('reinforcing')
        self.assertEqual(result['meaning'], 'vt. 加强 巩固')


if __name__ == '__main__':
    unittest.main()
