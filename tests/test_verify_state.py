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
    def test_every_layer_returns_lines(self):
        for collect in (module.layer_source, module.layer_deployed, module.layer_loaded,
                        module.layer_config, module.layer_onscreen):
            lines = collect()
            self.assertIsInstance(lines, list)
            self.assertTrue(lines, '%s produced nothing' % collect.__name__)
            self.assertTrue(all(isinstance(line, str) for line in lines))


if __name__ == '__main__':
    unittest.main()
