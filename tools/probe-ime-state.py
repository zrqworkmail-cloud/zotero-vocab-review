"""What does the IMM32 API actually report for a real Qt window on THIS machine?

The add-on closes the IME with ImmSetOpenStatus(hwnd, False). If ImmGetOpenStatus already
answers False while Microsoft Pinyin is the active input method, then that API is looking at
a state the TSF-based IME never writes — and the whole feature is a no-op, which is what the
user is describing. This probe measures it instead of reasoning about it.

It pops a small QLineEdit window for a couple of seconds on the real Windows platform,
because the offscreen platform has no input method at all.
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

from PyQt6.QtCore import Qt, QTimer                                    # noqa: E402
from PyQt6.QtWidgets import QApplication, QLineEdit                   # noqa: E402

app = QApplication([])

imm = ctypes.WinDLL('imm32', use_last_error=True)
imm.ImmGetContext.argtypes = [wintypes.HWND]
imm.ImmGetContext.restype = wintypes.HANDLE
imm.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
imm.ImmReleaseContext.restype = wintypes.BOOL
imm.ImmGetOpenStatus.argtypes = [wintypes.HANDLE]
imm.ImmGetOpenStatus.restype = wintypes.BOOL
imm.ImmSetOpenStatus.argtypes = [wintypes.HANDLE, wintypes.BOOL]
imm.ImmSetOpenStatus.restype = wintypes.BOOL
imm.ImmGetConversionStatus.argtypes = [wintypes.HANDLE,
                                       ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
imm.ImmGetConversionStatus.restype = wintypes.BOOL

box = QLineEdit()
box.resize(320, 40)
box.setWindowTitle('ZVR IME probe')
box.show()
box.setFocus(Qt.FocusReason.OtherFocusReason)
app.processEvents()

hwnd = int(box.winId())
context = imm.ImmGetContext(hwnd)
open_before = bool(imm.ImmGetOpenStatus(context)) if context else None
conversion, sentence = wintypes.DWORD(), wintypes.DWORD()
if context:
    imm.ImmGetConversionStatus(context, ctypes.byref(conversion), ctypes.byref(sentence))
set_result = bool(imm.ImmSetOpenStatus(context, False)) if context else None
open_after = bool(imm.ImmGetOpenStatus(context)) if context else None
if context:
    imm.ImmReleaseContext(hwnd, context)

layout = ctypes.windll.user32.GetKeyboardLayout(0)
print('window hwnd              :', hex(hwnd))
print('active keyboard layout    : 0x%08x  (%s)' % (layout, 'zh-CN' if (layout & 0xFFFF) == 0x0804 else 'other'))
print('ImmGetContext ->          :', 'ok' if context else 'NULL')
print('ImmGetOpenStatus before   :', open_before)
print('ImmGetConversionStatus    : 0x%x (IME_CMODE_NATIVE=%s IME_CMODE_KANA=%s)' % (
    conversion.value, bool(conversion.value & 0x0004), bool(conversion.value & 0x0002)))
print('ImmSetOpenStatus(False) ->:', set_result)
print('ImmGetOpenStatus after    :', open_after)
print()
print('Reading: if `before` is False while you are in 微软拼音 Chinese mode, the API the add-on')
print('calls never sees the real IME state (TSF owns it), so the feature is a no-op by design.')

QTimer.singleShot(6000, app.quit)
app.exec()
