"""Make a review window take Latin letters instead of whatever the IME wants to do.

Two levers, and only one of them is proven on this machine:

* `ReviewInputMode` below talks to IMM32 (`ImmSetOpenStatus`). Measured with
  tools/probe-ime-state.py: on a TSF input method — this machine has only 微软拼音 —
  `ImmGetOpenStatus` already answers False while the IME is in Chinese mode, and setting it
  changes nothing. So this call is a **legacy-IME best effort**, kept because the add-on is
  meant to work out of the box on other machines where a non-TSF IME does honour it.
* `make_latin_only` sets Qt's own per-widget flag. Qt disables the input method through its
  platform integration rather than through the IMM flag, which is the layer a TSF IME
  actually reads. In the manual run the control box composed Chinese twice while the box with
  this flag off produced literal `ceshi` twice; the API-level probe could not confirm the
  mechanism because its window never became active, so the real proof is the next card the
  learner types into.
"""

import ctypes
import os
from ctypes import wintypes


def _windows_imm():
    if os.name != 'nt':
        return None
    imm = ctypes.WinDLL('imm32', use_last_error=True)
    imm.ImmGetContext.argtypes = [wintypes.HWND]
    imm.ImmGetContext.restype = wintypes.HANDLE
    imm.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
    imm.ImmReleaseContext.restype = wintypes.BOOL
    imm.ImmGetOpenStatus.argtypes = [wintypes.HANDLE]
    imm.ImmGetOpenStatus.restype = wintypes.BOOL
    imm.ImmSetOpenStatus.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    imm.ImmSetOpenStatus.restype = wintypes.BOOL
    return imm


def _input_method_attribute():
    """Qt's flag, resolved lazily so this module stays importable without PyQt6."""
    try:
        from aqt.qt import Qt
    except ImportError:
        from PyQt6.QtCore import Qt
    return Qt.WidgetAttribute.WA_InputMethodEnabled


def make_latin_only(widget):
    """Stop the input method for this widget only. Returns what was changed, for tests."""
    attribute = _input_method_attribute()
    if widget.testAttribute(attribute):
        widget.setAttribute(attribute, False)
        return True
    return False


def is_latin_only(widget):
    return not widget.testAttribute(_input_method_attribute())


class ReviewInputMode:
    def __init__(self, imm=None):
        self.imm = imm if imm is not None else _windows_imm()
        self.saved = None

    def enable(self, hwnd):
        if not self.imm or self.saved is not None:
            return
        context = self.imm.ImmGetContext(hwnd)
        if not context:
            return
        try:
            original = bool(self.imm.ImmGetOpenStatus(context))
            if original and self.imm.ImmSetOpenStatus(context, False):
                self.saved = (hwnd, original)
        finally:
            self.imm.ImmReleaseContext(hwnd, context)

    def restore(self):
        if not self.imm or self.saved is None:
            return
        hwnd, original = self.saved
        self.saved = None
        context = self.imm.ImmGetContext(hwnd)
        if not context:
            return
        try:
            # Do not undo an input mode the user changed while the card was open.
            if not self.imm.ImmGetOpenStatus(context):
                self.imm.ImmSetOpenStatus(context, original)
        finally:
            self.imm.ImmReleaseContext(hwnd, context)


def _windows_user32():
    """The real `user32`, or None anywhere it does not exist.

    Prototypes are set once: without `argtypes` ctypes guesses `int` for an HKL and a
    truncated handle activates the wrong layout — the same class of bug that made
    `SendInput` return 0 in §9.47.
    """
    import sys
    if not sys.platform.startswith('win'):
        return None
    try:
        import ctypes
        import ctypes.wintypes as wintypes
        user32 = ctypes.windll.user32
    except Exception:
        return None
    if not getattr(user32, '_zvr_keyboard_prototypes', False):
        user32.LoadKeyboardLayoutW.restype = wintypes.HKL
        user32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, ctypes.c_uint]
        user32.ActivateKeyboardLayout.restype = wintypes.HKL
        user32.ActivateKeyboardLayout.argtypes = [wintypes.HKL, ctypes.c_uint]
        user32.GetKeyboardLayout.restype = wintypes.HKL
        user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
        user32._zvr_keyboard_prototypes = True
    return user32


class ThreadKeyboardLayout:
    """Type English in the spelling boxes without asking 微软拼音 to cooperate.

    Why this lever and not the two already in this file: on the learner's machine
    `GetKeyboardLayoutList` returns exactly one layout (0x08040804, Chinese), and the
    Pinyin TIP's Chinese/English state is internal to it — so `ImmSetOpenStatus(False)`
    has nothing to switch, and Qt's `WA_InputMethodEnabled=False` did not stop composition
    either (2026-11-05: 「我输入，也没有自动给我选成英文输入啊」). Activating the US keyboard
    layout for this thread routes the keys past the TIP entirely.

    It is per-thread, reversible, and dies with the process: no system or user setting is
    written. If the machine has no English layout to load, `enable()` says False and the
    card behaves exactly as before.
    """

    ENGLISH_KLID = '00000409'
    KLF_ACTIVATE = 0x0001

    def __init__(self, user32=None):
        self.user32 = user32 if user32 is not None else _windows_user32()
        self.previous = None
        self.activated = None

    def current(self):
        if self.user32 is None:
            return 0
        try:
            return int(self.user32.GetKeyboardLayout(0) or 0)
        except Exception:
            return 0

    def enable(self):
        """Switch this thread to the US layout. True when the English layout is in force."""
        if self.user32 is None:
            return False
        if self.previous is not None:
            return True                      # already switched for this card
        before = self.current()             # read it BEFORE: KLF_ACTIVATE changes it at once
        try:
            hkl = int(self.user32.LoadKeyboardLayoutW(self.ENGLISH_KLID, self.KLF_ACTIVATE) or 0)
        except Exception:
            return False
        if not hkl:
            return False
        self.previous, self.activated = before, hkl
        try:
            self.user32.ActivateKeyboardLayout(hkl, 0)
        except Exception:
            self.previous = self.activated = None
            return False
        return True

    def restore(self):
        """Put the layout back — but never over a change the learner made themselves."""
        if self.user32 is None or self.previous is None:
            return False
        previous, english = self.previous, self.activated
        self.previous = self.activated = None
        now = self.current()
        if english and now and now != english:
            return False                    # someone switched the keyboard mid-card; leave it
        try:
            self.user32.ActivateKeyboardLayout(previous, 0)
        except Exception:
            return False
        return True
