"""Which lever actually detaches the IME context, read from the API instead of from typing.

Why this version: the typing experiment needed the learner to click a window at the right
moment, and three runs were lost to that (plus two bugs of mine). The mechanism is
observable without anyone typing — Qt disables a widget's input method on Windows by
disassociating the IME context from the top-level window, and `ImmGetContext` reports the
result. If the context is gone, TSF has nothing to compose with; that is the claim being
tested, and it is testable deterministically.

What each line means:
  context   ImmGetContext(hwnd) — 0 means no IME context is attached at all.
  default   ImmGetDefaultIMEWnd(hwnd) — the default IME window for this layout; non-zero
            while the system IME is in charge.
  open      ImmGetOpenStatus(context) — known to lie for a TSF IME, kept as a control.

Read once with focus on a plain box (control), then once per lever. The window never needs to
be the foreground window, because no keystrokes are involved.
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32')])
os.add_dll_directory(os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(BASE))
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))

from PyQt6.QtCore import Qt                                          # noqa: E402
from PyQt6.QtWidgets import (QApplication, QLineEdit, QVBoxLayout, QWidget)  # noqa: E402

LOG = os.path.join(os.environ['TEMP'], 'zvr-ime-api.log')
open(LOG, 'w', encoding='utf-8').close()

imm = ctypes.WinDLL('imm32', use_last_error=True)
user32 = ctypes.windll.user32
imm.ImmGetContext.argtypes = [wintypes.HWND]
imm.ImmGetContext.restype = wintypes.HANDLE
imm.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
imm.ImmReleaseContext.restype = wintypes.BOOL
imm.ImmGetOpenStatus.argtypes = [wintypes.HANDLE]
imm.ImmGetOpenStatus.restype = wintypes.BOOL
imm.ImmGetDefaultIMEWnd.argtypes = [wintypes.HWND]
imm.ImmGetDefaultIMEWnd.restype = wintypes.HWND


def record(line):
    with open(LOG, 'a', encoding='utf-8') as handle:
        handle.write(line + '\n')
    print(line, flush=True)


def pump(app, milliseconds):
    deadline = time.time() + milliseconds / 1000.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


def probe(hwnd, label):
    context = imm.ImmGetContext(hwnd)
    opened = bool(imm.ImmGetOpenStatus(context)) if context else None
    default = imm.ImmGetDefaultIMEWnd(hwnd)
    if context:
        imm.ImmReleaseContext(hwnd, context)
    record('%-6s context=%-12s default_ime_wnd=%-12s imm_open=%s'
           % (label, '0 (detached)' if not context else 'attached',
              '0' if not default else hex(int(default)), opened))
    return bool(context)


app = QApplication([])
window = QWidget()
window.setWindowTitle('ZVR IME API probe')
layout = QVBoxLayout(window)
boxes = {}
for lever in ('none', 'attr', 'hint', 'both'):
    box = QLineEdit()
    box.setPlaceholderText(lever)
    if lever in ('attr', 'both'):
        box.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
    if lever in ('hint', 'both'):
        box.setInputMethodHints(Qt.InputMethodHint.ImhLatinOnly |
                                Qt.InputMethodHint.ImhNoPredictiveText)
    layout.addWidget(box)
    boxes[lever] = box
window.resize(420, 200)
window.show()
pump(app, 500)
hwnd = int(window.winId())
record('layout = 0x%08x' % (user32.GetKeyboardLayout(0) & 0xFFFFFFFF))

# The window's own state first: this is what the card looks like while a normal field has it.
probe(hwnd, 'window')
for lever, box in boxes.items():
    box.setFocus(Qt.FocusReason.OtherFocusReason)
    pump(app, 400)
    focused = app.focusWidget()
    if focused is not box:
        record('%-6s could not take focus (%s) — result not usable'
               % (lever, type(focused).__name__ if focused is not None else None))
        continue
    probe(hwnd, lever)
    record('       attr=%s hint=%s' % (box.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled),
                                        bool(box.inputMethodHints())))

record('reading: context=0 (detached) means Qt unbound the IME from this window while that '
       'field had focus — TSF then has nothing to compose with')
record('log at %s' % LOG)
