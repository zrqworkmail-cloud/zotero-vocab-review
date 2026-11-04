"""Catch the live celebration on the real card: wait for the add-on to log a celebration,
then grab that window's pixels.

The badge is on screen for 0.98 秒, so a human screenshot almost always misses it. This polls
the runtime log and calls PrintWindow the moment a new `card motion:` line appears, which is
written by the same call that starts the animation. PrintWindow renders into a bitmap without
depending on z-order, so another window on top does not spoil the capture.

Throwaway verification tool. Writes %TEMP%\\zvr-motion-live-<n>.png and prints the path.
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes
from datetime import datetime

LOG = os.path.join(os.environ['TEMP'], 'zotero_global_capture_runtime.log')
CARD_TITLE = '单词随身复习'
DEADLINE = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 600)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
for name, func, args, rest in (
        ('GetWindowTextW', user32.GetWindowTextW, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        ('GetWindowTextLengthW', user32.GetWindowTextLengthW, [wintypes.HWND], ctypes.c_int),
        ('GetWindowThreadProcessId', user32.GetWindowThreadProcessId, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.UINT),
        ('IsWindowVisible', user32.IsWindowVisible, [wintypes.HWND], wintypes.BOOL),
        ('GetWindowRect', user32.GetWindowRect, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        ('GetDC', user32.GetDC, [wintypes.HWND], ctypes.c_void_p),
        ('ReleaseDC', user32.ReleaseDC, [wintypes.HWND, ctypes.c_void_p], ctypes.c_int),
        ('CreateCompatibleDC', gdi32.CreateCompatibleDC, [ctypes.c_void_p], ctypes.c_void_p),
        ('CreateCompatibleBitmap', gdi32.CreateCompatibleBitmap, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int], ctypes.c_void_p),
        ('SelectObject', gdi32.SelectObject, [ctypes.c_void_p, ctypes.c_void_p], ctypes.c_void_p),
        ('PrintWindow', user32.PrintWindow, [wintypes.HWND, ctypes.c_void_p, ctypes.c_uint], ctypes.c_bool),
        ('DeleteDC', gdi32.DeleteDC, [ctypes.c_void_p], ctypes.c_bool),
        ('DeleteObject', gdi32.DeleteObject, [ctypes.c_void_p], ctypes.c_bool),
        ('GetDIBits', gdi32.GetDIBits, [ctypes.c_void_p, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                        ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT], ctypes.c_int),
):
    getattr(user32, name, getattr(gdi32, name, None))
    func.argtypes = args
    func.restype = rest


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wintypes.DWORD), ('biWidth', ctypes.c_long), ('biHeight', ctypes.c_long),
                ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', ctypes.c_long),
                ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD)]


def card_windows():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def walk(hwnd, _param):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if CARD_TITLE in buffer.value:
            found.append(hwnd)
        return True

    user32.EnumWindows(walk, 0)
    return found


def grab(hwnd, path):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < 40 or height < 40:
        return False
    dc = user32.GetDC(hwnd)
    memory = gdi32.CreateCompatibleDC(dc)
    bitmap = gdi32.CreateCompatibleBitmap(dc, width, height)
    gdi32.SelectObject(memory, bitmap)
    ok = user32.PrintWindow(hwnd, memory, 2)      # PW_RENDERFULLCONTENT
    info = BITMAPINFOHEADER()
    info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.biWidth, info.biHeight = width, -height
    info.biPlanes, info.biBitCount, info.biCompression = 1, 32, 0
    pixels = (ctypes.c_ubyte * (width * height * 4))()
    got = gdi32.GetDIBits(memory, bitmap, 0, height, pixels, ctypes.byref(info), 0)
    user32.ReleaseDC(hwnd, dc)
    gdi32.DeleteDC(memory)
    gdi32.DeleteObject(bitmap)
    if not got:
        return False
    from PIL import Image
    Image.frombytes('RGBA', (width, height), bytes(pixels), 'raw', 'BGRA').convert('RGB').save(path, 'PNG')
    return True


def log_lines():
    try:
        with open(LOG, encoding='utf-8', errors='replace') as handle:
            return handle.read().splitlines()
    except OSError:
        return []


seen = sum(1 for line in log_lines() if 'card motion:' in line)
print('watching for a new celebration (currently %d logged), until %s'
      % (seen, datetime.fromtimestamp(DEADLINE).strftime('%H:%M:%S')), flush=True)
while time.time() < DEADLINE:
    now = sum(1 for line in log_lines() if 'card motion:' in line)
    if now > seen:
        # The pill fades in over 260ms and measured full colour from ~180ms (see
        # tools/probe-pill-brightness.py). Grabbing the instant the log line appears caught
        # the entrance and looked like a washed-out badge, so wait for the hold.
        time.sleep(0.35)
        windows = card_windows()
        if not windows:
            print('celebration logged but no card window found', flush=True)
        for index, hwnd in enumerate(windows):
            path = os.path.join(os.environ['TEMP'], 'zvr-motion-live-%d.png' % int(time.time()))
            if grab(hwnd, path):
                print('CAPTURED', path, flush=True)
                sys.exit(0)
        seen = now
    time.sleep(0.12)
print('TIMEOUT: no celebration was logged in the window', flush=True)
sys.exit(1)
