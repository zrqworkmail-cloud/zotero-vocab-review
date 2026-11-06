"""Throwaway experiment: which lever actually stops 微软拼音 in a Qt field?

Root cause already measured (tools/probe-ime-state.py): with zh-CN + Microsoft Pinyin,
`ImmGetOpenStatus` answers False and `ImmSetOpenStatus(False)` changes nothing — the add-on's
IMM32 call is talking to a legacy flag the TSF IME never reads. So the fix has to go through
Qt's own input context, and only typing into a real window proves whether Qt deactivates TSF.

Four fields, one lever each, because the first version of this probe put
`WA_InputMethodEnabled=False` AND `ImhLatinOnly` on the same box and could not tell which one
did the work (or whether both did nothing):

  ① control            — nothing set; must show Chinese candidates
  ② WA_InputMethodEnabled = False
  ③ inputMethodHints = ImhLatinOnly (+ ImhNoPredictiveText)
  ④ both

Type the same syllable into all four. Every keystroke is logged to a file as well, so the
answer is read from the recorded text, not from a description of what appeared.
"""
import ctypes
import os
import sys
from ctypes import wintypes

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32')])
os.add_dll_directory(os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(BASE))
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))

from PyQt6.QtCore import Qt                                          # noqa: E402
from PyQt6.QtWidgets import (QApplication, QLabel, QLineEdit, QVBoxLayout, QWidget)  # noqa: E402

LOG = os.path.join(os.environ['TEMP'], 'zvr-ime-experiment.log')
open(LOG, 'w', encoding='utf-8').close()

imm = ctypes.WinDLL('imm32', use_last_error=True)
imm.ImmGetContext.argtypes = [wintypes.HWND]
imm.ImmGetContext.restype = wintypes.HANDLE
imm.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
imm.ImmGetOpenStatus.argtypes = [wintypes.HANDLE]
imm.ImmGetOpenStatus.restype = wintypes.BOOL


def record(line):
    with open(LOG, 'a', encoding='utf-8') as handle:
        handle.write(line + '\n')
    print(line, flush=True)


def imm_open(widget):
    """The legacy IMM32 flag for this widget's window, as a second opinion."""
    try:
        handle = int(widget.winId())
    except Exception:
        return 'n/a'
    context = imm.ImmGetContext(handle)
    if not context:
        return 'no-context'
    try:
        return bool(imm.ImmGetOpenStatus(context))
    finally:
        imm.ImmReleaseContext(handle, context)


def observe(box, name):
    box.textChanged.connect(lambda text, label=name: record(
        '%-2s text=%r imm_open=%s' % (label, text, imm_open(box))))
    box.destroyed.connect(lambda *_a, label=name: None)


app = QApplication([])
window = QWidget()
window.setWindowTitle('ZVR 输入法实验（四个框各打一次 ceshi）')
layout = QVBoxLayout(window)

boxes = []
specs = (
    ('①', '对照：什么都不设（预期出现中文候选）', {}),
    ('②', '只关 WA_InputMethodEnabled', {'attribute': False}),
    ('③', '只设 ImhLatinOnly 提示', {'hint': True}),
    ('④', '两个都设', {'attribute': False, 'hint': True}),
)
for name, caption, options in specs:
    layout.addWidget(QLabel(caption))
    box = QLineEdit()
    box.setPlaceholderText('在这里打 ceshi')
    if options.get('attribute') is False:
        box.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
    if options.get('hint'):
        box.setInputMethodHints(Qt.InputMethodHint.ImhLatinOnly |
                                Qt.InputMethodHint.ImhNoPredictiveText)
    layout.addWidget(box)
    observe(box, name)
    boxes.append((name, box, options))

record('setup: ' + ' | '.join(
    '%s attr=%s hint=%s' % (name,
                            box.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled),
                            bool(box.inputMethodHints()))
    for name, box, _o in boxes))
record('imm_open at start (whole window): %s' % imm_open(window))
record('type ceshi into all four, then close this window')

window.resize(460, 330)
window.show()
boxes[0][1].setFocus(Qt.FocusReason.OtherFocusReason)
app.exec()

record('final: ' + ' | '.join('%s=%r' % (name, box.text()) for name, box, _o in boxes))
record('log at %s' % LOG)
