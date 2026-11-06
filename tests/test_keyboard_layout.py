"""ThreadKeyboardLayout — the lever that actually bypasses 微软拼音 on this machine.

Why not the ones already in the file: this Windows has exactly ONE keyboard layout
(`GetKeyboardLayoutList` returns 0x08040804), and 微软拼音's Chinese/English state lives
inside the TIP, so `ImmSetOpenStatus(False)` has nothing to switch, and Qt's
`WA_InputMethodEnabled=False` did not stop composition on the learner's machine
(2026-11-05: 「我输入，也没有自动给我选成英文输入啊」). Activating the US keyboard layout for
the thread routes keys past the TIP entirely — per-thread, reversible, and gone when the
process exits, so no system setting is touched.
"""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'anki-global-addon/zotero_global_capture/input_mode.py'
spec = importlib.util.spec_from_file_location('input_mode', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CHINESE = 0x08040804
ENGLISH = 0x04090409


class FakeUser32:
    def __init__(self, loads=ENGLISH):
        self.loads = loads
        self.loaded, self.activated, self.args = [], [], []
        self.current = CHINESE

    def LoadKeyboardLayoutW(self, klid, flags):
        self.args.append((klid, flags))
        self.loaded.append(klid)
        return self.loads

    def ActivateKeyboardLayout(self, hkl, flags):
        self.activated.append(hkl)
        if hkl:
            self.current = hkl
        return hkl

    def GetKeyboardLayout(self, thread_id):
        return self.current


class Switch(unittest.TestCase):
    def test_enable_loads_the_english_klid_and_activates_it(self):
        user32 = FakeUser32()
        layout = module.ThreadKeyboardLayout(user32)
        self.assertTrue(layout.enable())
        self.assertEqual(user32.loaded, [module.ThreadKeyboardLayout.ENGLISH_KLID])
        self.assertEqual(user32.activated, [ENGLISH])

    def test_the_original_layout_is_saved_so_restore_can_put_it_back(self):
        user32 = FakeUser32()
        layout = module.ThreadKeyboardLayout(user32)
        layout.enable()
        self.assertTrue(layout.restore())
        self.assertEqual(user32.activated, [ENGLISH, CHINESE])
        self.assertEqual(layout.current(), CHINESE)

    def test_repeated_enable_is_not_repeated_work(self):
        user32 = FakeUser32()
        layout = module.ThreadKeyboardLayout(user32)
        layout.enable()
        layout.enable()
        layout.enable()
        self.assertEqual(user32.loaded, [module.ThreadKeyboardLayout.ENGLISH_KLID])
        layout.restore()
        layout.restore()
        self.assertEqual(user32.activated, [ENGLISH, CHINESE])

    def test_restore_without_enable_does_nothing(self):
        user32 = FakeUser32()
        layout = module.ThreadKeyboardLayout(user32)
        self.assertFalse(layout.restore())
        self.assertEqual(user32.activated, [])

    def test_a_machine_without_an_english_layout_falls_back_silently(self):
        user32 = FakeUser32(loads=0)
        layout = module.ThreadKeyboardLayout(user32)
        self.assertFalse(layout.enable())
        self.assertEqual(user32.activated, [], 'nothing may be activated when the load failed')
        self.assertFalse(layout.restore())
        self.assertEqual(user32.activated, [])

    def test_a_card_shown_again_after_restore_switches_again(self):
        user32 = FakeUser32()
        layout = module.ThreadKeyboardLayout(user32)
        layout.enable(); layout.restore()
        self.assertTrue(layout.enable())
        self.assertEqual(user32.loaded, [module.ThreadKeyboardLayout.ENGLISH_KLID] * 2)
        layout.restore()
        self.assertEqual(user32.activated, [ENGLISH, CHINESE, ENGLISH, CHINESE])


    def test_a_layout_the_learner_changed_mid_card_is_left_alone(self):
        user32 = FakeUser32()
        layout = module.ThreadKeyboardLayout(user32)
        layout.enable()
        user32.current = 0x04110411          # the user switched to Japanese themselves
        self.assertFalse(layout.restore())
        self.assertEqual(user32.activated, [ENGLISH], 'restore must not overwrite their choice')
        self.assertEqual(layout.current(), 0x04110411)

if __name__ == '__main__':
    unittest.main()
