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


if __name__ == '__main__':
    unittest.main()
