"""Decisive, self-checking experiment: does Qt's WA_InputMethodEnabled stop 微软拼音?

Why this version exists: the four-box manual run (2026-11-05) came back contaminated — box ③
logged literal `ceshi`, was cleared, and then logged Chinese `测桑晨`. Same box, two
outcomes, so the input mode changed mid-run (a stray Shift) and none of the four results can
be attributed to its lever any more.

So this probe drives the keystrokes itself with SendInput (real keyboard input, which is what
goes through TSF — PostMessage would skip the IME and prove nothing), and every trial types
the same syllable into TWO boxes:

  canary  — a plain QLineEdit with nothing set. It MUST come back with a Chinese character.
  subject — the box under test, configured by one lever.

If the canary does not compose Chinese, the trial is void rather than a result: that is the
whole point of the canary. Committing with Space makes the answer unambiguous — an active IME
commits its first candidate (CJK), a disabled one types a literal space.

Levers, one per trial, in a fresh window each time:
  none  control
  attr  WA_InputMethodEnabled = False
  hint  inputMethodHints = ImhLatinOnly | ImhNoPredictiveText
  both  both of the above
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

LOG = os.path.join(os.environ['TEMP'], 'zvr-ime-trial.log')
open(LOG, 'w', encoding='utf-8').close()
SYLLABLE = 'ceshi'
VK = {'c': 0x43, 'e': 0x45, 'h': 0x48, 'i': 0x49, 's': 0x53}
VK_SPACE = 0x20

user32 = ctypes.windll.user32


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


class MOUSEINPUT(ctypes.Structure):
    # The INPUT union is sized by MOUSEINPUT, the largest member. Leaving it out makes
    # sizeof(INPUT) smaller than the OS expects, SendInput returns 0, and every keystroke
    # silently vanishes — which is exactly what the first run of this probe looked like
    # ("the IME is not composing") when the real fault was the struct.
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT)]
    _fields_ = [('type', wintypes.DWORD), ('i', _I)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def send(vk):
    """One real key press and release, so TSF sees it the way it sees a human."""
    sent = 0
    for flags in (0, 0x0002):                       # 0 = down, KEYEVENTF_KEYUP
        event = INPUT()
        event.type = 1                              # INPUT_KEYBOARD
        event.i.ki.wVk = vk
        event.i.ki.dwFlags = flags
        sent += user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    return sent


def foreground_title():
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(user32.GetForegroundWindow(), buffer, 256)
    return buffer.value or ''


def has_cjk(text):
    return any('\u4e00' <= char <= '\u9fff' for char in text)


def record(line):
    with open(LOG, 'a', encoding='utf-8') as handle:
        handle.write(line + '\n')
    print(line, flush=True)


def pump(app, milliseconds):
    deadline = time.time() + milliseconds / 1000.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


def wait_for_foreground(window, lever, seconds=60):
    """Windows refuses SetForegroundWindow for a process that did not receive the last input
    event, so the learner clicks once and the probe takes it from there. It never types unless
    this returns True."""
    deadline = time.time() + seconds
    asked = False
    while time.time() < deadline:
        pump(QApplication.instance(), 100)
        if 'ZVR IME trial' in foreground_title():
            return True
        if not asked:
            record('%-5s waiting: please CLICK the small "ZVR IME trial" window once' % lever)
            window.raise_()
            window.activateWindow()
            asked = True
    return False


def main(app):
    """One window, one click, four bursts: the canary plus the three levers."""
    window = QWidget()
    window.setWindowTitle('ZVR IME trial — 点一下这个窗口')
    layout = QVBoxLayout(window)
    canary = QLineEdit()
    canary.setPlaceholderText('canary：什么都不设，必须打出中文，否则整轮作废')
    layout.addWidget(canary)
    subjects = []
    for lever in ('attr', 'hint', 'both'):
        box = QLineEdit()
        box.setPlaceholderText('subject %s' % lever)
        if lever in ('attr', 'both'):
            box.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        if lever in ('hint', 'both'):
            box.setInputMethodHints(Qt.InputMethodHint.ImhLatinOnly |
                                    Qt.InputMethodHint.ImhNoPredictiveText)
        layout.addWidget(box)
        subjects.append((lever, box))
    window.resize(460, 210)
    window.show()
    if not wait_for_foreground(window, 'setup', seconds=90):
        record('ABORT: never got the foreground; nothing was typed anywhere')
        return []
    outcomes = []
    # The canary doubles as the `none` lever: it is the same configuration, and its result is
    # also the proof that the IME was composing at that moment.
    for label, box in [('none', canary)] + subjects:
        outcome = burst(app, window, box, label, canary)
        outcomes.append(outcome)
        if outcome[1] is None:
            break
    return outcomes


def burst(app, window, box, lever, canary):
    box.setFocus(Qt.FocusReason.OtherFocusReason)
    box.clear()
    pump(app, 300)
    if 'ZVR IME trial' not in foreground_title():
        if not wait_for_foreground(window, lever, seconds=25):
            record('%-5s ABORT: foreground=%r' % (lever, foreground_title()))
            return lever, None, None
    focused = app.focusWidget()
    if focused is not box:
        record('%-5s ABORT: focus=%s active=%s'
               % (lever, type(focused).__name__ if focused is not None else None,
                  window.isActiveWindow()))
        return lever, None, None
    delivered = 0
    for char in SYLLABLE:
        delivered += send(VK[char])
        pump(app, 60)
    delivered += send(VK_SPACE)                     # commit the first candidate, if any
    pump(app, 600)
    text = box.text()
    # SendInput returns the number of events it actually inserted. Anything short of 12
    # (6 keys down + 6 up) means the OS refused the input, and then an empty box says
    # nothing about the input method.
    record('%-5s text=%-12r sent=%2d/12 attr=%s hint=%s  canary=%r'
           % (lever, text, delivered, box.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled),
              bool(box.inputMethodHints()), canary.text()))
    return lever, canary.text(), text


app = QApplication([])
record('sending %r then Space into each box; the canary must compose Chinese or the trial is '
       'void' % SYLLABLE)
outcomes = main(app)

print()
for lever, canary, subject in outcomes:
    if subject is None:
        print('%-5s VOID (focus was not ours)' % lever)
        continue
    if not has_cjk(canary):
        print('%-5s VOID (canary=%r — the IME was not composing, so nothing is proven)'
              % (lever, canary))
        continue
    verdict = ('IME STILL ACTIVE on this box' if has_cjk(subject)
               else 'letters went through — lever works')
    print('%-5s canary composed Chinese, subject=%r -> %s' % (lever, subject, verdict))
record('log at %s' % LOG)
