"""Does the offscreen platform paint a text caret at all, and does `caret-color: transparent`
remove it? The answer decides what the real check can assert.
"""
import os, sys

base = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, base)
os.environ['PATH'] = ';'.join([os.path.join(base, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(base)])
os.add_dll_directory(os.path.join(base, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(base))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_PLUGIN_PATH'] = os.path.join(base, 'PyQt6', 'Qt6', 'plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLineEdit
from PyQt6.QtTest import QTest

app = QApplication([])
CSS = ('QLineEdit{background:#252e40;color:#edf1fa;border:1px solid #4a5971;'
       'border-radius:8px;font-size:18px;}')


def changed(a, b):
    return sum(1 for y in range(a.height()) for x in range(a.width())
               if a.pixelColor(x, y) != b.pixelColor(x, y))


def make(extra=''):
    box = QLineEdit()
    box.setFixedSize(38, 40)
    box.setAlignment(Qt.AlignmentFlag.AlignCenter)
    box.setStyleSheet(CSS + extra)
    box.show()
    app.processEvents()
    return box


plain_box = make()
plain_box.clearFocus()
app.processEvents()
QTest.qWait(120)
plain = plain_box.grab().toImage()

focused = make()
focused.setFocus()
app.processEvents()
frames = [focused.grab().toImage()]
QTest.qWait(560)
frames.append(focused.grab().toImage())
QTest.qWait(560)
frames.append(focused.grab().toImage())
print('focused vs unfocused, three moments:', [changed(plain, f) for f in frames])
print('the two late frames differ by:', changed(frames[1], frames[2]), 'pixels')

quiet = make('caret-color: transparent;')
quiet.setFocus()
app.processEvents()
QTest.qWait(600)
print('caret-color transparent vs unfocused:', changed(plain, quiet.grab().toImage()), 'pixels')
print('cursorRect of the focused box:', quiet.cursorRect().getRect())
os._exit(0)
