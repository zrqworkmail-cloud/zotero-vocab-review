import ast
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / '__init__.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'ensure_anki_connect')
module = ast.Module(body=[node], type_ignores=[])

class ImmediateThread:
    def __init__(self, target, daemon): self.target = target
    def start(self): self.target()

class DependencyTests(unittest.TestCase):
    def run_case(self, exists, connected):
        downloads = []
        messages = []
        addon = types.ModuleType('aqt.addons')
        addon.download_encountered_problem = lambda log: False
        addon.download_addons = lambda parent, mgr, ids, done: downloads.extend(ids)
        mw = types.SimpleNamespace(addonManager=types.SimpleNamespace(addonsFolder=lambda name: '/missing/' + name, isEnabled=lambda name: True),
                                   taskman=types.SimpleNamespace(run_on_main=lambda f: f()))
        def api(*args, **kwargs):
            if connected: return 6
            raise OSError('offline')
        scope = {'os': os, 'mw': mw, 'threading': types.SimpleNamespace(Thread=ImmediateThread), 'api': api,
                 'show_feedback': lambda text, **kw: messages.append(text), 'log_runtime': lambda x: None}
        exec(compile(module, str(source), 'exec'), scope)
        with patch('os.path.isdir', return_value=exists), patch.dict(sys.modules, {'aqt': types.ModuleType('aqt'), 'aqt.addons': addon}):
            scope['ensure_anki_connect']()
        return downloads

    def test_existing_install_is_preserved(self):
        self.assertEqual(self.run_case(True, False), [])

    def test_other_active_connect_is_preserved(self):
        self.assertEqual(self.run_case(False, True), [])

    def test_missing_connect_uses_anki_official_downloader(self):
        self.assertEqual(self.run_case(False, False), [2055492159])
