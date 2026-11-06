"""Does a Chinese layout produce a candidate window when keys go to a NON-editable widget?

Why this exists: the card restores the thread layout as soon as the answer is up, but the
answer face still takes A–E / F / P as plain keys with a push button holding focus. If
微软拼音 composes those letters, the rating shortcuts are eaten — a worse bug than the one
just fixed. Offscreen there is no input method at all, so this can only be answered against
the real TSF on this machine, in an isolated window of our own.

Safety rules, because it sends real keystrokes:
* refuses to run if a study card is on screen (the keys would land in the learner's session);
* sends keys only while its own window is verifiably the foreground one;
* counts what SendInput actually inserted — a short count means nothing was typed, which is
  a different fact from "nothing appeared".

    python tools/probe-answer-face-ime.py
"""
import ctypes
import ctypes.wintypes as wintypes
import os
import sys
import time
import types

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32')])
os.add_dll_directory(os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(BASE))
os.environ['QT_PLUGIN_PATH'] = os.path.join(BASE, 'PyQt6', 'Qt6', 'plugins')
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog, QPushButton, QVBoxLayout, QLabel

aqt = types.ModuleType('aqt')
aqt.mw = types.SimpleNamespace()
qt_module = types.ModuleType('aqt.qt')
for name in ('QObject', 'Qt', 'pyqtSignal'):
    setattr(qt_module, name, globals()[name])
sys.modules['aqt'] = aqt
sys.modules['aqt.qt'] = qt_module
package = types.ModuleType('zotero_global_capture')
package.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                                 'anki-global-addon', 'zotero_global_capture'))]
sys.modules['zotero_global_capture'] = package

from zotero_global_capture import input_mode

user32 = ctypes.windll.user32
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('hwndActive', wintypes.HWND), ('hwndFocus', wintypes.HWND),
                ('hwndCapture', wintypes.HWND), ('hwndMenuOwner', wintypes.HWND),
                ('hwndMoveSize', wintypes.HWND), ('hwndCaret', wintypes.HWND),
                ('rcCaret', wintypes.RECT)]


user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.c_void_p]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT)]
    _fields_ = [('type', wintypes.DWORD), ('i', _I)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
# The union must carry MOUSEINPUT too: with only KEYBDINPUT, sizeof(INPUT) is 28/32 instead
# of the 40 x64 requires, SendInput returns 0, and an empty result looks like "the IME did
# not compose" when in fact nothing was ever typed (§9.47).
assert ctypes.sizeof(INPUT) == 40, ctypes.sizeof(INPUT)

WORD = 'bug'
VK = {char: ord(char.upper()) for char in WORD}


def title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def window_names():
    found = {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def walk(hwnd, _param):
        if user32.IsWindowVisible(hwnd):
            name = title(hwnd)
            klass = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, klass, 256)
            found[int(hwnd)] = (name, klass.value)
        return True

    user32.EnumWindows(walk, 0)
    return found


def root_of(hwnd):
    """Qt's winId is not always the window Windows reports as active; walk up to the root."""
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    return int(user32.GetAncestor(hwnd, 2) or 0)          # GA_ROOT


def foreground():
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(0, ctypes.byref(info)):
        return 0
    return int(info.hwndActive or 0)


def send(word):
    sent = 0
    for vk in (VK[char] for char in word):
        for flags in (0, 0x0002):
            event = INPUT()
            event.type = 1
            event.i.ki.wVk = vk
            event.i.ki.dwFlags = flags
            sent += user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        time.sleep(0.08)
    return sent


def ours(hwnd):
    """Is the foreground window ours?

    Compared by title, not by handle: Qt's `winId()` and `GA_ROOT` can both differ from the
    window Windows reports as active (the frame is a separate HWND of its own), and a
    handle-only check aborted every run while the title said plainly that we were frontmost.
    """
    active = foreground()
    return active == hwnd or (title(active) and title(active) == title(hwnd))


def run(label, app, hwnd, reader=None):
    for _ in range(4):
        if claim(hwnd) and ours(hwnd):
            break
        time.sleep(0.4)
        app.processEvents()
    if not ours(hwnd):
        print('%-10s ABORT: foreground hwnd=%s %r, not our window'
              % (label, foreground(), title(foreground())))
        return
    before = window_names()
    sent = send(WORD)
    time.sleep(0.6)
    app.processEvents()
    after = window_names()
    new = [(handle, names) for handle, names in after.items() if handle not in before]
    gone = [(handle, names) for handle, names in before.items() if handle not in after]
    layout = input_mode.ThreadKeyboardLayout()
    typed = reader() if reader else ''
    print('%-10s sent=%d/6 布局=0x%08x 新出现的窗口=%-2d 控件里剩下=%r'
          % (label, sent, layout.current(), len(new), typed))
    for handle, (name, klass) in new[:6]:
        print('            + %-28s class=%s' % (name[:28] or '(无标题)', klass))
    if not new:
        print('            没有新窗口 —— 按键没有进入输入法合成')


def claim(hwnd, tries=8):
    """Bring our window to the foreground, and say so if Windows will not allow it."""
    for _ in range(tries):
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        time.sleep(0.2)
        if ours(hwnd):
            return True
    return False


def main():
    card = None
    for probe in ('单词随身复习',):
        card = user32.FindWindowW(None, probe)
        if card:
            break
    if card:
        print('学习卡在屏（hwnd=%s）。这个探针会真发按键，拒绝在你学习时运行。'
              ' 等卡片关掉再跑。' % card)
        return 2

    app = QApplication(sys.argv)
    dialog = QDialog()
    # Topmost while it is being driven: without it, another window can take the foreground
    # between the claim and the keystrokes, and the keys would land somewhere else.
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    dialog.setWindowTitle('ZVR answer-face IME probe')
    dialog.resize(360, 160)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel('模拟答案面：可编辑控件为零，焦点在按钮上'))
    button = QPushButton('B. Hard')
    layout.addWidget(button)
    dialog.show()
    button.setFocus()
    app.processEvents()
    time.sleep(0.4)
    app.processEvents()
    hwnd = root_of(int(dialog.winId()))
    print('我们窗口的根 hwnd =', hwnd, '标题 =', title(hwnd))

    print('本机线程布局（未切）：0x%08x' % input_mode.ThreadKeyboardLayout().current())
    run('中文布局', app, hwnd)

    # --- positive control -------------------------------------------------------------
    # A negative result only means something if this same method can catch the IME in the
    # act. §9.47 was exactly that trap: SendInput returned 0 and an empty result looked
    # like "the IME did not compose". So: type into a real editable widget and require the
    # candidate window (or a non-literal text) to show up in Chinese, and NOT in English.
    from PyQt6.QtWidgets import QLineEdit
    edit = QLineEdit(dialog)
    dialog.layout().addWidget(edit)
    edit.show()

    def type_into(what):
        edit.clear()
        edit.setFocus()
        app.processEvents()
        time.sleep(0.2)
        run('%s/编辑框' % what, app, hwnd, reader=lambda: edit.text())

    type_into('中文')
    switch = input_mode.ThreadKeyboardLayout()
    if switch.enable():
        app.processEvents(); time.sleep(0.2)
        type_into('英文')
        switch.restore()
    edit.deleteLater()
    app.processEvents()

    switch = input_mode.ThreadKeyboardLayout()
    if not switch.enable():
        print('切英文失败：这台机器装不了 00000409，后面的对照没法做')
        return 3
    app.processEvents()
    time.sleep(0.3)
    dialog.activateWindow()
    button.setFocus()
    app.processEvents()
    run('英文布局', app, hwnd)
    switch.restore()
    print('已还原布局：0x%08x' % input_mode.ThreadKeyboardLayout().current())
    dialog.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
