"""Throwaway experiment: does Qt's per-widget "input method disabled" stop 微软拼音?

Root cause already measured (tools/probe-ime-state.py): with zh-CN + Microsoft Pinyin,
`ImmGetOpenStatus` answers False and `ImmSetOpenStatus(False)` changes nothing — the add-on's
IMM32 call is talking to a legacy flag the TSF IME never reads. So the fix has to go through
Qt's own input context, and only typing in a real window proves whether Qt deactivates TSF.

Two boxes: the top one is normal, the bottom one has WA_InputMethodEnabled = False.
Type the same Chinese syllable (e.g. "ceshi") into both and report what happens.
"""
import ctypes
import os
import sys

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32')])
os.add_dll_directory(os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(BASE))
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))

from PyQt6.QtCore import Qt                                          # noqa: E402
from PyQt6.QtWidgets import (QApplication, QLabel, QLineEdit, QVBoxLayout, QWidget)  # noqa: E402

app = QApplication([])
window = QWidget()
window.setWindowTitle('ZVR 输入法实验')
layout = QVBoxLayout(window)
layout.addWidget(QLabel('① 普通输入框 —— 预期：打 ceshi 会出现中文候选'))
normal = QLineEdit()
normal.setPlaceholderText('在这里打 ceshi')
layout.addWidget(normal)
layout.addWidget(QLabel('② 关掉输入法的输入框 —— 观察：是否还是中文候选？'))
latin = QLineEdit()
latin.setPlaceholderText('在这里也打 ceshi')
latin.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
latin.setInputMethodHints(Qt.InputMethodHint.ImhLatinOnly | Qt.InputMethodHint.ImhNoPredictiveText)
layout.addWidget(latin)
layout.addWidget(QLabel('② 当前 WA_InputMethodEnabled = %s' %
                        latin.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled)))
window.resize(420, 190)
window.show()
normal.setFocus(Qt.FocusReason.OtherFocusReason)
print('实验窗口已打开：请在两个框里各打一次 ceshi，然后告诉我 ② 是不是直接进了英文字母。')
app.exec()
