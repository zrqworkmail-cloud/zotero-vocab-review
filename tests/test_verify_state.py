"""The status panel must not cry wolf about drift.

git's autocrlf checkout rewrites a deployed file's line endings without changing
a single token of code, and the first version of verify-state reported that as
DRIFT — which is worse than having no check, because it trains you to ignore the
check.
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_state', ROOT / 'tools' / 'verify-state.py')
module = importlib.util.module_from_spec(spec)
sys.modules['verify_state'] = module
spec.loader.exec_module(module)


class Hashing(unittest.TestCase):
    def test_line_endings_do_not_count_as_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            unix = Path(folder) / 'unix.py'
            dos = Path(folder) / 'dos.py'
            unix.write_bytes(b"import os\r\nprint('hi')\r\n".replace(b'\r\n', b'\n'))
            dos.write_bytes(b"import os\r\nprint('hi')\r\n")
            self.assertEqual(module.sha256(unix), module.sha256(dos))

    def test_a_real_change_still_drifts(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / 'a.py'
            second = Path(folder) / 'b.py'
            first.write_bytes(b"x = 1\n")
            second.write_bytes(b"x = 2\n")
            self.assertNotEqual(module.sha256(first), module.sha256(second))


class Layers(unittest.TestCase):
    def test_deployed_layer_checks_domain_and_lexicon_recursively(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, target = root / 'source', root / 'target'
            (source / 'domain').mkdir(parents=True)
            (source / 'lexicon').mkdir()
            (source / 'domain' / 'models.py').write_text('version = 1\n', encoding='utf-8')
            (source / 'lexicon' / 'words.txt').write_text('word\n', encoding='utf-8')
            (source / 'kyle_enrich.py').write_text('private\n', encoding='utf-8')
            (source / 'user_files').mkdir()
            (source / 'user_files' / 'private.json').write_text('{}', encoding='utf-8')
            (source / 'config.json').write_text('{}', encoding='utf-8')
            (target / 'domain').mkdir(parents=True)
            (target / 'domain' / 'models.py').write_text('version = 2\n', encoding='utf-8')
            (target / 'meta.json').write_text('{}', encoding='utf-8')
            (target / '__init__.py.bak-20261109').write_text('old\n', encoding='utf-8')
            (target / 'review_logic.py.before-e-removal').write_text('old\n', encoding='utf-8')
            (target / 'pre-deploy-20261112').mkdir()
            (target / 'pre-deploy-20261112' / 'review_logic.py').write_text('old\n', encoding='utf-8')
            old_source, old_installed = module.SRC, module.installed_dir
            try:
                module.SRC, module.installed_dir = source, lambda: target
                lines = module.layer_deployed()
            finally:
                module.SRC, module.installed_dir = old_source, old_installed
            text = '\n'.join(lines)
            self.assertIn('DRIFT  domain/models.py', text)
            self.assertIn('ABSENT lexicon/words.txt', text)
            self.assertNotIn('kyle_enrich.py', text)
            self.assertNotIn('user_files', text)
            self.assertNotIn('meta.json', text)
            self.assertNotIn('.bak-', text)
            self.assertNotIn('.before-', text)
            self.assertNotIn('pre-deploy-', text)

    def test_every_layer_returns_lines(self):
        for collect in (module.layer_source, module.layer_deployed, module.layer_loaded,
                        module.layer_config, module.layer_onscreen):
            lines = collect()
            self.assertIsInstance(lines, list)
            self.assertTrue(lines, '%s produced nothing' % collect.__name__)
            self.assertTrue(all(isinstance(line, str) for line in lines))


if __name__ == '__main__':
    unittest.main()
