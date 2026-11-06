"""Does 'exit Anki from the tray icon' still work once the tray add-on has hidden the window?

The user reports that the taskbar/tray icon no longer quits Anki, and only the card's own
「退出 Anki」 does. 'Minimize to Tray 2' quits like this:

    def onExit(self):
        self.mw.closeEventFromAction = True
        self.mw.close()

and its wrapper around `mw.closeEvent` hides every window (`hideAll()`) whenever the X button
is used. So after one X, `mw` is hidden -- and this probe asks the only question that matters:
does `QWidget.close()` on a *hidden* window still deliver a QCloseEvent at all, or is it a
silent no-op that leaves Anki running forever?

Everything here is a plain offscreen QMainWindow with the plugin's exact wrapper and an event
filter that counts Close events; nothing touches the real Anki.
"""
import os
import sys
from types import MethodType

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
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow

app = QApplication([])

shutdowns = []          # what an accepted close reaches: Anki's real teardown


class Counter(QObject):
    """Stand-in for our MainWindowCloseFilter: it only counts, never interferes."""

    def __init__(self):
        super().__init__()
        self.closes = 0

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Close:
            self.closes += 1
        return False


def make_window():
    win = QMainWindow()
    win.closeEventFromAction = False

    def repl(self, event):
        # the plugin's `_wrapCloseCloseEvent`, 1:1
        if self.closeEventFromAction:
            AnkiQt_closeEvent(self, event)
        else:
            self.hide()               # hideAll(): the X button goes to the tray
            event.ignore()

    def AnkiQt_closeEvent(self, event):
        event.accept()
        shutdowns.append('profile closed')

    win.closeEvent = MethodType(repl, win)
    counter = Counter()
    win.installEventFilter(counter)
    return win, counter


def step(label, win, counter, exit_action):
    win.closeEventFromAction = exit_action
    before = counter.closes
    returned = win.close()
    app.processEvents()
    print('%-46s close()=%-6s Close事件=%d 可见=%-6s 走到了退出=%s' % (
        label, returned, counter.closes - before, win.isVisible(), bool(shutdowns)))
    shutdowns.clear()


win, counter = make_window()
win.show()
app.processEvents()

step('A X 按钮（窗口可见，flag=False）', win, counter, False)
step('B 托盘「退出」（刚被 X 收进托盘，窗口已隐藏）', win, counter, True)
win.show()
app.processEvents()
step('C 恢复可见后再点托盘「退出」（flag=True）', win, counter, True)

win2, counter2 = make_window()
win2.show()
app.processEvents()
step('D 对照：卡片「退出 Anki」（可见，flag=True）', win2, counter2, True)
