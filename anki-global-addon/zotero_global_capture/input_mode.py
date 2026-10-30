"""Temporarily use direct keyboard input in a Windows review window."""

import ctypes
import os
from ctypes import wintypes


def _windows_imm():
    if os.name != 'nt':
        return None
    imm = ctypes.WinDLL('imm32', use_last_error=True)
    imm.ImmGetContext.argtypes = [wintypes.HWND]
    imm.ImmGetContext.restype = wintypes.HANDLE
    imm.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
    imm.ImmReleaseContext.restype = wintypes.BOOL
    imm.ImmGetOpenStatus.argtypes = [wintypes.HANDLE]
    imm.ImmGetOpenStatus.restype = wintypes.BOOL
    imm.ImmSetOpenStatus.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    imm.ImmSetOpenStatus.restype = wintypes.BOOL
    return imm


class ReviewInputMode:
    def __init__(self, imm=None):
        self.imm = imm if imm is not None else _windows_imm()
        self.saved = None

    def enable(self, hwnd):
        if not self.imm or self.saved is not None:
            return
        context = self.imm.ImmGetContext(hwnd)
        if not context:
            return
        try:
            original = bool(self.imm.ImmGetOpenStatus(context))
            if original and self.imm.ImmSetOpenStatus(context, False):
                self.saved = (hwnd, original)
        finally:
            self.imm.ImmReleaseContext(hwnd, context)

    def restore(self):
        if not self.imm or self.saved is None:
            return
        hwnd, original = self.saved
        self.saved = None
        context = self.imm.ImmGetContext(hwnd)
        if not context:
            return
        try:
            # Do not undo an input mode the user changed while the card was open.
            if not self.imm.ImmGetOpenStatus(context):
                self.imm.ImmSetOpenStatus(context, original)
        finally:
            self.imm.ImmReleaseContext(hwnd, context)
