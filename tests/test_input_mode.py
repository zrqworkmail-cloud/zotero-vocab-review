import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'anki-global-addon/zotero_global_capture/input_mode.py'
spec = importlib.util.spec_from_file_location('input_mode', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeImm:
    def __init__(self, opened=True, context=True):
        self.opened, self.context, self.releases, self.writes = opened, context, 0, []
    def ImmGetContext(self, hwnd):
        return 123 if self.context else None
    def ImmReleaseContext(self, hwnd, context):
        self.releases += 1
    def ImmGetOpenStatus(self, context):
        return self.opened
    def ImmSetOpenStatus(self, context, value):
        self.opened = bool(value)
        self.writes.append(bool(value))
        return True


class InputModeTests(unittest.TestCase):
    def test_switch_and_restore_only_once(self):
        imm = FakeImm()
        mode = module.ReviewInputMode(imm)
        mode.enable(10)
        mode.enable(10)
        self.assertFalse(imm.opened)
        mode.restore()
        mode.restore()
        self.assertEqual(imm.writes, [False, True])
        self.assertEqual(imm.releases, 2)

    def test_already_english_and_missing_context_unchanged(self):
        for imm in (FakeImm(False), FakeImm(context=False)):
            mode = module.ReviewInputMode(imm)
            mode.enable(10)
            mode.restore()
            self.assertEqual(imm.writes, [])

    def test_user_override_is_not_reverted(self):
        imm = FakeImm()
        mode = module.ReviewInputMode(imm)
        mode.enable(10)
        imm.opened = True
        mode.restore()
        self.assertEqual(imm.writes, [False])

    def test_the_module_imports_without_pyqt(self):
        # The IMM32 half has to stay testable without a Qt install, so the Qt flag is
        # resolved lazily inside the helpers. Importing PyQt6 at module scope here would
        # make the pure suite depend on the Anki bundle.
        self.assertIn('ReviewInputMode', dir(module))
        self.assertTrue(callable(module.make_latin_only))
        self.assertTrue(callable(module.is_latin_only))
        self.assertNotIn('PyQt6', str(getattr(module, '__dict__', {}).keys()))


class WhichLeverIsWhich(unittest.TestCase):
    """Recorded so nobody re-adds the hint as if it were the fix."""

    def test_the_imm_flag_is_documented_as_a_legacy_best_effort(self):
        # Measured on this machine: 微软拼音 is TSF-only, ImmGetOpenStatus answers False even
        # in Chinese mode, and ImmSetOpenStatus changes nothing. Keeping the call is fine for
        # other machines; keeping it as *the* fix is what left the learner typing into
        # candidates.
        doc = path.read_text(encoding='utf-8')
        self.assertIn('legacy-IME best effort', doc)
        self.assertIn('WA_InputMethodEnabled', doc)
        self.assertIn('make_latin_only', doc)


if __name__ == '__main__':
    unittest.main()
