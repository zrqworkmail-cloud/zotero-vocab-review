"""Windows login startup for the optional background review companion."""

import ctypes
import os
import subprocess
import sys


VALUE_NAME = 'ZoteroAnkiVocabularyReview'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def configure_login_start(enabled):
    if sys.platform != 'win32':
        if enabled:
            raise RuntimeError('开机启动目前仅支持 Windows。')
        return
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if not enabled:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
            return
        buf = ctypes.create_unicode_buffer(32768)
        if not ctypes.windll.kernel32.GetModuleFileNameW(None, buf, len(buf)):
            raise OSError('无法确定 Anki 程序位置。')
        exe = buf.value
        if not os.path.isfile(exe) or 'anki' not in os.path.basename(exe).lower():
            raise OSError('无法确定 Anki 程序位置。')
        script = os.path.join(os.path.dirname(__file__), 'start_background.vbs')
        if not os.path.isfile(script):
            raise OSError('后台启动文件不存在。')
        wscript = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'wscript.exe')
        command = subprocess.list2cmdline([wscript, '//B', script, exe])
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
