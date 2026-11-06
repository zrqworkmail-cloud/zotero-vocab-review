"""Can a QLineEdit caret actually be switched off, and does the offscreen platform draw it?

The learner wants the caret gone entirely, with the focused box flashing instead. Before
building that, two things must be known: whether Qt paints a caret at all under
QT_QPA_PLATFORM=offscreen (if it does not, no offscreen test can prove the caret is gone), and
whether `setCursorWidth(0)` suppresses it. Each box is grabbed 12 times over ~1.8 s: a
blinking caret shows up as two distinct images, a dead caret as one.
"""
import os, sys

base = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, base)
os.environ['PATH'] = ';'.join([os.path.join(base, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(base),
                               os.path.join(os.environ['SystemRoot'], 'System32'),
                               os.environ['SystemRoot']])
os.add_dll_directory(os.path.join(base, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(base))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_PLUGIN_PATH'] = os.path.join(base, 'PyQt6', 'Qt6', 'plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication, QLineEdit
from PyQt6.QtTest import QTest

app = QApplication([])
QFontDatabase.addApplicationFont(r'C:\Windows\Fonts\segoeui.ttf')


def states(cursor_width):
    box = QLineEdit()
    box.setFixedSize(38, 40)
    box.setAlignment(Qt.AlignmentFlag.AlignCenter)
    box.setMaxLength(1)
    box.setStyleSheet('background:#252e40; color:#edf1fa; border:1px solid #4a5971;'
                      'border-radius:8px; font-size:18px;')
    box.setCursorWidth(cursor_width)
    box.show()
    box.setFocus()
    app.processEvents()
    seen = set()
    for _ in range(12):
        app.processEvents()
        QTest.qWait(150)
        seen.add(box.grab().toImage().toHex())
    print('cursorWidth=%-3s distinct frames %d  (2 means a blinking caret is painted)'
          % (cursor_width, len(seen)))
    return len(seen)


states(-1)
states(0)
states(1)
os._exit(0)
