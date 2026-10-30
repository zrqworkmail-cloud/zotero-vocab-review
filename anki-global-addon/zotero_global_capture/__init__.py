"""Windows global selection capture for Anki, using its existing AnkiConnect service."""

from __future__ import annotations

import ctypes
import html
import json
import os
import re
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request
from ctypes import wintypes

from aqt import gui_hooks, mw
from aqt.qt import (
    QApplication, QCheckBox, QComboBox, QDate, QDateEdit, QDialog, QDialogButtonBox, QEvent, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QTimer, QVBoxLayout,
    QWidget, QObject, pyqtSignal, Qt, QCursor, QSpinBox, QTime, QTimeEdit,
)

from .background import configure_login_start
from .review_popup import DesktopReviewController, enable_click_away, popup_style
from .review_logic import BOOK_TAGS, collection_plan, review_decks, selected_review_modes, validate_windows, window_minutes
from .exam_dates import fetch_cet
from .study_dashboard import activity_counts, dashboard_html
from . import core_import, cet6_books, cet6_listening


ADDON = __name__
ANKI_TAG = "anki_global_capture"
DEFAULTS = {
    "mode": "preview",
    "modifiers": 0x0002 | 0x0004,  # Ctrl+Shift
    "virtual_key": 0x79,  # F10
    "deck": "文献单词",
    "model": "四六级单词模板",
    "front_field": "正面",
    "back_field": "解释",
    "confirm_seconds": 8,
    "review_enabled": True,
    "review_interval_minutes": 30,
    "review_smart": True,
    "review_core_enabled": True,
    "review_book": "",
    "review_extra_deck": "四六级单词",
    "review_batch_size": 3,
    "review_plan_mode": "fixed",
    "review_daily_goal": 0,
    "review_computer_hours": 8,
    "review_deadline": "",
    "review_exam": "manual",
    "review_windows_enabled": False,
    "review_windows": [
        {"enabled": True, "start": "09:00", "end": "12:00"},
        {"enabled": True, "start": "14:00", "end": "18:00"},
        {"enabled": True, "start": "19:00", "end": "22:00"},
    ],
    "review_auto_word": True,
    "review_hint_audio": False,
    "review_auto_example": False,
    "review_auto_example_mode": "first",
    "review_known_style": "underline",
    "review_position": "corner",
    "review_theme": "light",
    "review_mode": "mixed",
    "review_beautify": True,
    "review_start_at_login": False,
}
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_C = 0x43
CF_UNICODETEXT = 13
WH_MOUSE_LL = 14
_notice = None
_runtime_log = os.path.join(tempfile.gettempdir(), "zotero_global_capture_runtime.log")
_runtime_log_lock = threading.Lock()


def log_runtime(event):
    """Record control-flow only; never write selected words or clipboard text."""
    try:
        with _runtime_log_lock:
            with open(_runtime_log, "a", encoding="utf-8") as log_file:
                log_file.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), event))
    except Exception:
        pass


def settings():
    value = dict(DEFAULTS)
    stored = mw.addonManager.getConfig(ADDON) or {}
    value.update(stored)
    if 'review_auto_example_mode' not in stored and stored.get('review_auto_example'):
        value['review_auto_example_mode'] = 'example'
    return value


def save_settings(value):
    mw.addonManager.writeConfig(ADDON, value)


def format_shortcut(modifiers, virtual_key):
    names = []
    if int(modifiers) & MOD_CONTROL:
        names.append("Ctrl")
    if int(modifiers) & MOD_ALT:
        names.append("Alt")
    if int(modifiers) & MOD_SHIFT:
        names.append("Shift")
    if int(modifiers) & MOD_WIN:
        names.append("Win")
    key = int(virtual_key)
    if 0x41 <= key <= 0x5A or 0x30 <= key <= 0x39:
        key_name = chr(key)
    elif 0x70 <= key <= 0x87:
        key_name = "F%d" % (key - 0x6F)
    else:
        key_name = {0x20: "Space", 0x21: "PageUp", 0x22: "PageDown", 0x23: "End",
                    0x24: "Home", 0x2D: "Insert", 0x2E: "Delete"}.get(key, "?")
    return "+".join(names + [key_name])


def show_feedback(message, period=5000):
    """Show a short topmost notice so feedback is visible over the source app."""
    global _notice
    if _notice is not None:
        _notice.close()
    notice = QLabel(str(message))
    notice.setTextFormat(Qt.TextFormat.PlainText)
    notice.setWordWrap(True)
    notice.setStyleSheet(
        "QLabel { background: #f4f6fb; color: #27344d; border: 1px solid #dce4f1; "
        "border-left: 4px solid #5668ca; border-radius: 10px; padding: 12px 16px; "
        "font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; font-size: 14px; }"
    )
    notice.setWindowFlags(
        Qt.WindowType.ToolTip | Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.WindowDoesNotAcceptFocus
    )
    notice.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
    notice.setMinimumWidth(260)
    notice.setMaximumWidth(min(420, max(260, screen.availableGeometry().width() - 48)) if screen else 420)
    notice.adjustSize()
    if screen:
        area = screen.availableGeometry()
        notice.move(area.right() - notice.width() - 24, area.bottom() - notice.height() - 32)
    _notice = notice
    notice.show()
    QTimer.singleShot(int(period), lambda: notice.close())


def api(action, params=None, timeout=15):
    body = json.dumps({"action": action, "version": 6, "params": params or {}}).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:8765", body,
        {"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = json.loads(response.read().decode("utf-8"))
    if value.get("error"):
        raise RuntimeError(value["error"])
    return value.get("result")


def dictionary(word):
    url = "https://dict.youdao.com/jsonapi?q=" + urllib.parse.quote(word) + "&doctype=json&jsonversion=2"
    request = urllib.request.Request(url, headers={"User-Agent": "Zotero-Global-Anki/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        root = json.loads(response.read().decode("utf-8"))

    def clean(value):
        if isinstance(value, (list, tuple)):
            return " ".join(part for part in (clean(item) for item in value) if part)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html.unescape(str(value or "")))).strip()

    definitions, examples, authority, phonetics, synonyms, roots = [], [], [], [], [], []
    simple = (root.get("simple", {}).get("word") or [{}])[0]
    for sound in (simple.get("ukphone"), simple.get("usphone")):
        if clean(sound) and clean(sound) not in phonetics:
            phonetics.append(clean(sound))
    for group in (root.get("ec", {}).get("word") or [{}])[0].get("trs", []):
        for translation in group.get("tr", []):
            meaning = clean(translation.get("l", {}).get("i"))
            if meaning:
                definitions.append("%s %s" % (clean(group.get("pos")), meaning))
    for group in root.get("expand_ec", {}).get("word", []):
        for translation in group.get("transList", []):
            content = translation.get("content", {})
            for sentence in content.get("sents", []):
                english = clean(sentence.get("sentSpeech") or sentence.get("sentOrig"))
                chinese = clean(sentence.get("sentTrans"))
                if english:
                    row = english + (" — " + chinese if chinese else "")
                    examples.append(row)
                    if sentence.get("sourceType") == "权威":
                        authority.append(row)
    for group in root.get("syno", {}).get("synos", []):
        synonyms.extend(clean(item.get("w")) for item in group.get("syno", {}).get("ws", []))
    for item in root.get("etym", {}).get("etyms", {}).get("en", []):
        value = clean(item.get("value"))
        if value:
            roots.append((clean(item.get("source")) + "：" if clean(item.get("source")) else "") + value)
    speech = simple.get("usspeech") or simple.get("ukspeech") or ""
    audio = ""
    if speech:
        base, _, kind = str(speech).partition("&type=")
        audio = "https://dict.youdao.com/dictvoice?audio=%s&type=%s" % (
            urllib.parse.quote(base), kind or "2",
        )
    return {
        "meaning": "\n".join(dict.fromkeys(definitions[:8])),
        "examples": "\n".join(dict.fromkeys(examples[:8])),
        "authority": "\n".join(dict.fromkeys(authority[:5])),
        "phonetic": " · ".join(phonetics[:3]),
        "synonyms": "；".join(dict.fromkeys(synonyms[:8])),
        "roots": "\n".join(roots[:3]),
        "audio": audio,
    }


class Bridge(QObject):
    event = pyqtSignal(str)
    result = pyqtSignal(str, object, object)
    write_result = pyqtSignal(str, object, object)
    status = pyqtSignal(str)


class NativeListener(threading.Thread):
    """Win32 global shortcut plus optional mouse-drag selection trigger."""

    def __init__(self, bridge, config, report_status=True):
        super().__init__(daemon=True)
        self.bridge = bridge
        self.config = dict(config)
        self.report_status = report_status
        self.thread_id = 0
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.registered = False
        self.registration_error = ''
        self.mouse_down = None
        self.hook = None
        self.hook_proc = None

    def stop(self):
        self.stop_event.set()
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)

    def _mouse_callback(self, code, message, data):
        if code >= 0:
            point = ctypes.cast(data, ctypes.POINTER(MSLLHOOKSTRUCT)).contents.pt
            if message == WM_LBUTTONDOWN:
                self.mouse_down = (point.x, point.y)
            elif message == WM_LBUTTONUP and self.mouse_down:
                dx, dy = point.x - self.mouse_down[0], point.y - self.mouse_down[1]
                self.mouse_down = None
                if dx * dx + dy * dy >= 25:
                    self.bridge.event.emit("auto")
        return ctypes.windll.user32.CallNextHookEx(self.hook, code, message, data)

    def run(self):
        user32 = ctypes.windll.user32
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        cfg = self.config
        register_hotkey = user32.RegisterHotKey
        register_hotkey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        register_hotkey.restype = wintypes.BOOL
        get_message = user32.GetMessageW
        get_message.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        get_message.restype = ctypes.c_int
        translate_message = user32.TranslateMessage
        translate_message.argtypes = [ctypes.POINTER(MSG)]
        dispatch_message = user32.DispatchMessageW
        dispatch_message.argtypes = [ctypes.POINTER(MSG)]
        if not register_hotkey(None, 1, int(cfg["modifiers"]), int(cfg["virtual_key"])):
            code = ctypes.windll.kernel32.GetLastError()
            self.registration_error = ('快捷键已被其他程序或系统占用' if code == 1409 else 'Windows 错误码 %s' % code)
            log_runtime("hotkey registration failed")
            if self.report_status:
                self.bridge.status.emit("全局快捷键注册失败：%s。" % self.registration_error)
        else:
            self.registered = True
            log_runtime("hotkey registered: %s" % format_shortcut(cfg["modifiers"], cfg["virtual_key"]))
            if self.report_status:
                self.bridge.status.emit("全局划词入 Anki 已启动（%s）。" %
                                         format_shortcut(cfg["modifiers"], cfg["virtual_key"]))
        if cfg["mode"] == "auto":
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
            self.hook_proc = callback_type(self._mouse_callback)
            get_module = ctypes.windll.kernel32.GetModuleHandleW
            get_module.argtypes = [wintypes.LPCWSTR]
            get_module.restype = wintypes.HMODULE
            set_hook = user32.SetWindowsHookExW
            set_hook.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
            set_hook.restype = wintypes.HHOOK
            self.hook = set_hook(WH_MOUSE_LL, self.hook_proc, get_module(None), 0)
            if not self.hook:
                self.bridge.status.emit("自动模式的鼠标监听未能启动，请改用快捷键模式。")
        message = MSG()
        # Create the thread message queue before reporting readiness so stop() can wake it.
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        self.ready.set()
        log_runtime("listener message loop ready; thread=%s" % self.thread_id)
        while not self.stop_event.is_set():
            result = get_message(ctypes.byref(message), None, 0, 0)
            if result <= 0:
                log_runtime("listener message loop ended: %s" % result)
                break
            if message.message == WM_HOTKEY:
                log_runtime("WM_HOTKEY received")
                self.bridge.event.emit("hotkey")
            translate_message(ctypes.byref(message))
            dispatch_message(ctypes.byref(message))
        user32.UnregisterHotKey(None, 1)
        if self.hook:
            user32.UnhookWindowsHookEx(self.hook)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT), ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM), ("time", wintypes.DWORD), ("pt", POINT)]


def key_event(vk, down):
    ctypes.windll.user32.keybd_event(vk, 0, 0 if down else 2, 0)


def send_copy():
    key_event(VK_CONTROL, True)
    key_event(VK_C, True)
    key_event(VK_C, False)
    key_event(VK_CONTROL, False)


def clone_clipboard(mime):
    from aqt.qt import QMimeData
    clone = QMimeData()
    if mime is None:
        return clone
    for fmt in mime.formats():
        clone.setData(fmt, mime.data(fmt))
    if mime.hasText():
        clone.setText(mime.text())
    if mime.hasHtml():
        clone.setHtml(mime.html())
    return clone


class PreviewDialog(QDialog):
    def __init__(self, word, details, confirm):
        super().__init__(mw)
        self.setWindowTitle("划词释义预览")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.WindowStaysOnTopHint)
        enable_click_away(self)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>%s</b>" % html.escape(word)))
        definition = details.get("meaning") or "词典暂无释义；确认后仍可添加单词。"
        label = QLabel(html.escape(definition).replace("\n", "<br>"))
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(QLabel("再次按全局快捷键或点击“添加”确认；超时或关闭则取消。"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("添加到 Anki")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(460, 220)


class ShortcutEdit(QLineEdit):
    """Capture a supported Windows system-wide shortcut combination."""
    feedback = pyqtSignal(str)

    def __init__(self, modifiers, virtual_key, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("点击此处，然后按快捷键组合")
        self.modifiers = int(modifiers)
        self.virtual_key = int(virtual_key)
        self.valid = True
        self._show_shortcut()

    def _show_shortcut(self):
        self.setText(format_shortcut(self.modifiers, self.virtual_key))

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.setText('正在录入：请按快捷键组合')
        self.feedback.emit('正在录入快捷键；请同时按修饰键和目标键，按 Esc 取消。')

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._show_shortcut()
        if not self.valid:
            self.valid = True
            self.feedback.emit('未录入有效组合，已保留原快捷键。')

    def keyPressEvent(self, event):
        key = int(event.key())
        qt_modifiers = event.modifiers()
        modifiers = 0
        if qt_modifiers & Qt.KeyboardModifier.ControlModifier:
            modifiers |= MOD_CONTROL
        if qt_modifiers & Qt.KeyboardModifier.AltModifier:
            modifiers |= MOD_ALT
        if qt_modifiers & Qt.KeyboardModifier.ShiftModifier:
            modifiers |= MOD_SHIFT
        if qt_modifiers & Qt.KeyboardModifier.MetaModifier:
            modifiers |= MOD_WIN

        if key == int(Qt.Key.Key_Escape):
            self.valid = True
            self._show_shortcut()
            self.feedback.emit('已取消录入，保留当前组合。')
            self.clearFocus()
            event.accept()
            return
        if key in (int(Qt.Key.Key_Control), int(Qt.Key.Key_Shift), int(Qt.Key.Key_Alt), int(Qt.Key.Key_Meta)):
            self.feedback.emit('正在录入：请继续按下字母、数字、功能键或导航键。')
            event.accept()
            return

        if 0x41 <= key <= 0x5A or 0x30 <= key <= 0x39:
            virtual_key = key
        elif 0x01000030 <= key <= 0x01000047:  # Qt F1-F24
            virtual_key = 0x70 + key - 0x01000030
        else:
            virtual_key = {
                0x01000006: 0x2D,  # Insert
                0x01000007: 0x2E,  # Delete
                0x01000010: 0x24,  # Home
                0x01000011: 0x23,  # End
                0x01000016: 0x21,  # PageUp
                0x01000017: 0x22,  # PageDown
                0x20: 0x20,       # Space
            }.get(key)
        if virtual_key is None:
            self.valid = False
            self.feedback.emit("录入失败：暂不支持此按键，请用字母、数字、F1–F24 或导航键。")
            return
        if not modifiers:
            self.valid = False
            self.feedback.emit("录入失败：请至少搭配 Ctrl、Alt、Shift 或 Win。")
            return
        self.modifiers = modifiers
        self.virtual_key = virtual_key
        self.valid = True
        self._show_shortcut()
        self.feedback.emit('已录入 %s；点击保存后注册。' % self.text())
        event.accept()


class Controller:
    def __init__(self):
        self.bridge = Bridge()
        self.bridge.event.connect(self.on_event)
        self.bridge.result.connect(self.on_result)
        self.bridge.write_result.connect(self.on_write_result)
        self.bridge.status.connect(lambda text: show_feedback(text, period=5000))
        self.listener = NativeListener(self.bridge, settings())
        self.listener.start()
        self.pending = None
        self.pending_dialog = None
        self.pending_timer = QTimer()
        self.pending_timer.setSingleShot(True)
        self.pending_timer.timeout.connect(self.cancel_pending)
        self.busy = False
        self.last_auto = ("", 0)
        self.review = DesktopReviewController(settings, api, show_feedback, log_runtime)

    def on_event(self, kind):
        log_runtime("controller event: %s" % kind)
        if kind == "hotkey" and self.pending:
            self.confirm_pending()
            return
        cfg = settings()
        if kind == "auto" and cfg["mode"] != "auto":
            return
        if kind == "hotkey" and cfg["mode"] == "auto":
            return
        if self.busy:
            if kind == "hotkey":
                show_feedback("上一个单词还在处理中，请稍候。", period=3000)
            return
        if kind == "hotkey":
            show_feedback("快捷键已触发，正在读取选区…", period=3000)
        self.capture_selection(kind)

    def capture_selection(self, kind):
        log_runtime("selection capture started: %s" % kind)
        clipboard = QApplication.clipboard()
        saved = clone_clipboard(clipboard.mimeData())
        sequence = ctypes.windll.user32.GetClipboardSequenceNumber()
        self.busy = True
        if kind == "hotkey":
            for vk in (VK_CONTROL, VK_SHIFT, VK_MENU):
                key_event(vk, False)
        send_copy()
        state = {"saved": saved, "sequence": sequence, "elapsed": 0, "kind": kind}
        self.copy_state = state
        QTimer.singleShot(45, lambda: self.poll_clipboard(state))

    def poll_clipboard(self, state):
        if state is not self.copy_state:
            return
        sequence = ctypes.windll.user32.GetClipboardSequenceNumber()
        clipboard = QApplication.clipboard()
        if sequence != state["sequence"]:
            word = clipboard.text().strip()
            log_runtime("clipboard changed; copied text length=%d" % len(word))
            copied_sequence = sequence
            if ctypes.windll.user32.GetClipboardSequenceNumber() == copied_sequence:
                clipboard.setMimeData(state["saved"])
            self.busy = False
            if not word:
                if state["kind"] == "hotkey":
                    show_feedback("没有检测到可复制的选区。", period=5000)
                return
            word = re.sub(r"\s+", " ", word)
            if len(word) > 120 or len(word.split()) > 12:
                show_feedback("仅支持 1–12 个词、最多 120 个字符。", period=5000)
                return
            cfg = settings()
            if cfg["mode"] == "auto":
                now = time.monotonic()
                if self.last_auto[0].casefold() == word.casefold() and now - self.last_auto[1] < 2.0:
                    return
                self.last_auto = (word, now)
            self.lookup_or_add(word, cfg["mode"] == "preview")
            return
        state["elapsed"] += 45
        if state["elapsed"] >= 1000:
            log_runtime("selection capture timed out")
            self.busy = False
            if state["kind"] == "hotkey":
                show_feedback("没有复制到选中文本；此应用可能不支持快捷复制。", period=5000)
            return
        QTimer.singleShot(45, lambda: self.poll_clipboard(state))

    def lookup_or_add(self, word, preview):
        self.busy = True

        def run():
            try:
                info = dictionary(word)
                log_runtime("dictionary lookup succeeded")
                self.bridge.result.emit(word, info, None)
            except Exception as exc:
                log_runtime("dictionary lookup failed: %s" % type(exc).__name__)
                self.bridge.result.emit(word, {}, str(exc))

        threading.Thread(target=run, daemon=True).start()
        self.pending_word = word
        self.pending_preview = preview

    def on_result(self, word, info, error):
        self.busy = False
        if self.pending_word != word:
            return
        if error:
            show_feedback("查词失败；单词仍可添加。" if not self.pending_preview else "查词失败，未添加单词。", period=5000)
            if self.pending_preview:
                return
        if self.pending_preview:
            self.pending = (word, info)
            self.pending_dialog = PreviewDialog(word, info, self.confirm_pending)
            self.pending_dialog.finished.connect(lambda _: self.cancel_pending())
            self.pending_dialog.show()
            self.pending_timer.start(int(settings()["confirm_seconds"]) * 1000)
        else:
            self.add_note(word, info)

    def confirm_pending(self):
        if not self.pending:
            return
        word, info = self.pending
        self.pending_timer.stop()
        self.pending = None
        if self.pending_dialog:
            dialog, self.pending_dialog = self.pending_dialog, None
            dialog.accept()
        self.add_note(word, info)

    def cancel_pending(self):
        self.pending_timer.stop()
        self.pending = None
        if self.pending_dialog:
            dialog, self.pending_dialog = self.pending_dialog, None
            dialog.close()

    def add_note(self, word, info):
        self.busy = True
        cfg = settings()
        show_feedback("正在写入 Anki…", period=3000)

        def run():
            try:
                message = self.write_note(word, info, cfg)
                self.bridge.write_result.emit(word, message, None)
            except Exception as exc:
                log_runtime("Anki write failed: %s" % type(exc).__name__)
                self.bridge.write_result.emit(word, None, str(exc))

        threading.Thread(target=run, daemon=True).start()

    def write_note(self, word, info, cfg):
        model = cfg["model"]
        fields = api("modelFieldNames", {"modelName": model})
        if cfg["front_field"] not in fields or cfg["back_field"] not in fields:
            raise RuntimeError("Anki 笔记类型或正面/解释字段不匹配，请打开全局划词设置。")
        note_ids = api("findNotes", {"query": '"%s"' % word.replace('"', '\\"')}) or []
        notes = api("notesInfo", {"notes": note_ids}) if note_ids else []
        normalized = re.sub(r"<[^>]*>", "", word).strip().casefold()
        note = next((candidate for candidate in notes if candidate.get("modelName") == model
                     and html.unescape(re.sub(r"<[^>]*>", "", candidate.get("fields", {}).get(cfg["front_field"], {}).get("value", ""))).strip().casefold() == normalized), None)
        back_old = note.get("fields", {}).get(cfg["back_field"], {}).get("value", "") if note else ""
        count_match = re.search(r"(?:全局划词收录次数：|Global capture count:)\s*(\d+)", back_old)
        count = int(count_match.group(1)) + 1 if count_match else 1
        meaning = html.escape(info.get("meaning", "")).replace("\n", "<br>")
        metadata = "全局划词收录次数：%d" % count
        if note:
            if count_match:
                back = re.sub(r"((?:全局划词收录次数：|Global capture count:)\s*)\d+",
                              lambda match: match.group(1) + str(count), back_old, flags=re.I)
            else:
                back = (back_old + "<br><br>" if back_old else "") + metadata
        else:
            back = meaning + ("<br><br>" if meaning else "") + metadata

        optional = {
            "例句": info.get("examples", ""), "权威例句": info.get("authority", ""),
            "词根": info.get("roots", ""), "近义词": info.get("synonyms", ""),
            "音标": info.get("phonetic", ""),
            "英语发音": ('<a href="%s">🔊 在线发音</a>' % html.escape(info["audio"])) if info.get("audio") else "",
            "标签": "Windows 全局划词收录",
        }
        if note:
            updates = {cfg["front_field"]: html.escape(word), cfg["back_field"]: back}
            for field, value in optional.items():
                if field in fields and value and not note.get("fields", {}).get(field, {}).get("value", "").strip():
                    updates[field] = html.escape(value).replace("\n", "<br>") if not value.startswith("<a ") else value
            api("updateNoteFields", {"note": {"id": note["noteId"], "fields": updates}})
            api("addTags", {"notes": [note["noteId"]], "tags": ANKI_TAG})
            if count_match:
                return "已更新重复词卡：%s（第 %s 次）" % (word, count)
            return "已补充到已有词卡：%s" % word

        values = {field: "" for field in fields}
        values[cfg["front_field"]] = html.escape(word)
        values[cfg["back_field"]] = back
        for field, value in optional.items():
            if field in values and value:
                values[field] = html.escape(value).replace("\n", "<br>") if not value.startswith("<a ") else value
        api("addNote", {"note": {"deckName": cfg["deck"], "modelName": model,
                                  "fields": values, "tags": [ANKI_TAG],
                                  "options": {"allowDuplicate": False}}})
        log_runtime("Anki addNote succeeded")
        return "已添加到 Anki：%s" % word

    def on_write_result(self, word, message, error):
        self.busy = False
        if error:
            show_feedback("没有写入 Anki：%s" % error, period=7000)
            return
        show_feedback(message, period=5000)

    def stop(self):
        self.cancel_pending()
        self.review.stop()
        self.listener.stop()


def open_settings(parent=None):
    if mw.col is None:
        show_feedback('请先打开 Anki 账户，再配置复习设置。', period=5000)
        return
    cfg = settings()
    original = dict(cfg)
    dialog = QDialog(parent if isinstance(parent, QWidget) else mw)
    dialog.setWindowTitle("全局划词入 Anki")
    style = '''
        QDialog, QWidget#settingsBody { background: #f4f6fb; color: #25334d; }
        QLabel, QCheckBox { color: #25334d; background: transparent; }
        QComboBox, QSpinBox, QDateEdit, QTimeEdit, QLineEdit { background: #ffffff; color: #25334d; border: 1px solid #dce4f1;
            border-radius: 7px; padding: 5px 9px; min-height: 24px; }
        QComboBox:disabled, QSpinBox:disabled, QDateEdit:disabled, QTimeEdit:disabled, QLineEdit:disabled {
            background: #edf1f7; color: #536179; }
        QLineEdit:focus, QSpinBox:focus, QTimeEdit:focus, QDateEdit:focus, QComboBox:focus { border: 2px solid #536bd6; }
        QComboBox QAbstractItemView { background: #ffffff; color: #25334d; selection-background-color: #e8edff; selection-color: #172554; }
        QPushButton { background: #ffffff; color: #25334d; border: 1px solid #dce4f1; border-radius: 7px; padding: 6px 12px; }
        QPushButton:disabled { color: #96a0b1; }
        QPushButton#saveSettings { background: #5668ca; color: #ffffff; border: none; font-weight: 600; }
        QPushButton#saveSettings:hover { background: #4557b5; }
        QPushButton#saveSettings:disabled { background: #dce1ec; color: #7b8798; }
        QScrollArea { border: none; background: #f4f6fb; }
        QGroupBox { background: #ffffff; color: #25334d; font-weight: 600; border: 1px solid #dce4f1; border-radius: 9px; margin-top: 12px; padding: 14px 10px 8px; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
    '''
    try:
        from aqt.theme import theme_manager
        dark = bool(theme_manager.night_mode)
    except (ImportError, AttributeError):
        dark = False
    if dark:
        for old, new in {
            '#f4f6fb': '#171c2b', '#25334d': '#e1e8f5', '#ffffff': '#252e40',
            '#dce4f1': '#4a5971', '#edf1f7': '#343d4c', '#536179': '#aab4c5',
            '#536bd6': '#aab8ff', '#e8edff': '#34415d', '#172554': '#f2f4ff',
            '#96a0b1': '#aab4c5', '#5668ca': '#596dd1', '#4557b5': '#6e80df',
            '#dce1ec': '#343d4c', '#7b8798': '#aab4c5',
        }.items():
            style = style.replace(old, new)
        style += '''
QPushButton#saveSettings { color: white; }
QScrollBar:vertical { background: #171c2b; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #596a84; border-radius: 5px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
'''
    dialog.setStyleSheet(style)
    outer = QVBoxLayout(dialog)
    scroll = QScrollArea(dialog)
    scroll.setWidgetResizable(True)
    form_widget = QWidget()
    form_widget.setObjectName('settingsBody')
    sections = QVBoxLayout(form_widget)
    def section(title):
        group = QGroupBox(title)
        layout = QFormLayout(group)
        sections.addWidget(group)
        return layout
    scroll.setWidget(form_widget)
    outer.addWidget(scroll)
    dialog.resize(620, 700)
    mode = QComboBox()
    mode.setObjectName('captureMode')
    mode.addItem("选中后按快捷键添加", "direct")
    mode.addItem("选中后自动添加（鼠标拖选）", "auto")
    mode.addItem("快捷键预览释义，再按一次添加", "preview")
    mode.setCurrentIndex(max(0, mode.findData(cfg["mode"])))
    deck = QComboBox()
    deck.setObjectName('reviewDeck')
    model = QComboBox()
    model.setObjectName('reviewModel')
    front = QComboBox()
    front.setObjectName('reviewFrontField')
    back = QComboBox()
    back.setObjectName('reviewBackField')
    deck_names = [item.name for item in mw.col.decks.all_names_and_ids(include_filtered=False)]
    model_names = [item.name for item in mw.col.models.all_names_and_ids()]
    def populate(combo, names, selected, optional=False):
        combo.clear()
        if optional:
            combo.addItem('不使用补充牌组', '')
        for name in names:
            combo.addItem(name, name)
        if selected and selected not in names:
            combo.addItem('%s（未找到）' % selected, selected)
        combo.setCurrentIndex(max(0, combo.findData(selected)))
    populate(deck, deck_names, cfg['deck'])
    main_review_deck = QComboBox()
    main_review_deck.setObjectName('mainReviewDeck')
    populate(main_review_deck, deck_names, cfg.get('review_main_deck') or cfg['deck'])
    populate(model, model_names, cfg['model'])
    def fields_for_model():
        note_type = mw.col.models.by_name(model.currentData()) if model.currentData() in model_names else None
        return mw.col.models.field_names(note_type) if note_type else []
    def refresh_fields(initial=False):
        names = fields_for_model()
        old_front = cfg['front_field'] if initial else front.currentData()
        old_back = cfg['back_field'] if initial else back.currentData()
        if not initial and names:
            if old_front not in names:
                old_front = names[0]
            if old_back not in names or old_back == old_front:
                old_back = next((name for name in names if name != old_front), old_front)
        populate(front, names, old_front)
        populate(back, names, old_back)
        update_validity()
    confirm_seconds = QComboBox()
    confirm_seconds.setObjectName('previewSeconds')
    for seconds in (5, 8, 10, 15):
        confirm_seconds.addItem("%d 秒" % seconds, seconds)
    confirm_seconds.setCurrentIndex(max(0, confirm_seconds.findData(int(cfg["confirm_seconds"]))))
    shortcut = ShortcutEdit(cfg["modifiers"], cfg["virtual_key"])
    shortcut_status = QLabel('点击输入框录入快捷键；保存时会检查是否注册成功。')
    shortcut_status.setWordWrap(True)
    shortcut.feedback.connect(shortcut_status.setText)
    review_enabled = QCheckBox("定时弹出单词复习")
    review_enabled.setChecked(bool(cfg["review_enabled"]))
    review_interval = QSpinBox()
    review_interval.setRange(5, 240)
    review_interval.setSuffix(" 分钟")
    review_interval.setValue(int(cfg["review_interval_minutes"]))
    review_batch = QSpinBox()
    review_batch.setObjectName('reviewBatch')
    review_batch.setRange(1, 10)
    review_batch.setSuffix(" 张")
    review_batch.setValue(int(cfg["review_batch_size"]))
    plan_mode = QComboBox()
    plan_mode.setObjectName('planMode')
    plan_mode.addItem('固定每组张数', 'fixed')
    plan_mode.addItem('根据每日目标自动分组', 'daily')
    plan_mode.setCurrentIndex(max(0, plan_mode.findData(cfg['review_plan_mode'])))
    daily_goal = QSpinBox()
    daily_goal.setObjectName('dailyGoal')
    daily_goal.setRange(0, 9999)
    daily_goal.setSpecialValueText('自动建议')
    daily_goal.setValue(int(cfg['review_daily_goal']))
    computer_hours = QSpinBox()
    computer_hours.setObjectName('computerHours')
    computer_hours.setRange(1, 24)
    computer_hours.setSuffix(' 小时')
    computer_hours.setValue(int(cfg['review_computer_hours']))
    windows_enabled = QCheckBox('只在以下时段自动弹出')
    windows_enabled.setObjectName('windowsEnabled')
    windows_enabled.setChecked(bool(cfg['review_windows_enabled']))
    windows_widget = QWidget()
    windows_layout = QVBoxLayout(windows_widget)
    windows_layout.setContentsMargins(0, 0, 0, 0)
    window_rows = []
    def add_window(value=None):
        value = value or {'enabled': True, 'start': '09:00', 'end': '10:00'}
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        enabled = QCheckBox('启用')
        enabled.setChecked(value.get('enabled', True))
        start, end = QTimeEdit(), QTimeEdit()
        for control, key in ((start, 'start'), (end, 'end')):
            control.setDisplayFormat('HH:mm')
            parsed = QTime.fromString(value.get(key, ''), 'HH:mm')
            control.setTime(parsed if parsed.isValid() else QTime(9, 0))
        remove = QPushButton('删除')
        for widget in (enabled, start, QLabel('至'), end, remove):
            layout.addWidget(widget)
        windows_layout.addWidget(row)
        window_rows.append((row, enabled, start, end, remove))
        def remove_row():
            if len(window_rows) > 3:
                window_rows.remove(next(entry for entry in window_rows if entry[0] is row))
                row.deleteLater()
                windows_changed()
        remove.clicked.connect(remove_row)
        for control, signal in ((enabled, 'toggled'), (start, 'timeChanged'), (end, 'timeChanged')):
            getattr(control, signal).connect(lambda *_: windows_changed())
    for value in cfg['review_windows']:
        add_window(value)
    while len(window_rows) < 3:
        add_window({'enabled': False, 'start': '09:00', 'end': '10:00'})
    add_period = QPushButton('添加时段')
    add_period.clicked.connect(lambda: (add_window({'enabled': False, 'start': '09:00', 'end': '10:00'}), windows_changed()))
    windows_layout.addWidget(add_period)
    def windows_value():
        return [{'enabled': enabled.isChecked(), 'start': start.time().toString('HH:mm'), 'end': end.time().toString('HH:mm')}
                for _, enabled, start, end, _ in window_rows]
    deadline_enabled = QCheckBox('设置考试截止日期')
    deadline_enabled.setChecked(bool(cfg['review_deadline']))
    deadline = QDateEdit()
    deadline.setCalendarPopup(True)
    parsed_date = QDate.fromString(cfg['review_deadline'], 'yyyy-MM-dd')
    deadline.setDate(parsed_date if parsed_date.isValid() else QDate.currentDate().addDays(30))
    deadline.setEnabled(deadline_enabled.isChecked())
    deadline_enabled.toggled.connect(deadline.setEnabled)
    exam = QComboBox()
    for label, value in [('手动设置 / 雅思 / 托福等', 'manual'), ('大学英语四级（笔试）', 'cet4'), ('大学英语六级（笔试）', 'cet6')]:
        exam.addItem(label, value)
    exam.setCurrentIndex(max(0, exam.findData(cfg['review_exam'])))
    exam_status = QLabel('四六级日期可从中国教育考试网获取；其他考试请按准考证设置。')
    exam_status.setWordWrap(True)
    fetch_exam = QPushButton('从官方更新考试日期')
    fetch_exam.setEnabled(exam.currentData() != 'manual')
    class ExamBridge(QObject):
        finished = pyqtSignal(str, str, str)
    exam_bridge = ExamBridge(dialog)
    exam_request_date = [None]
    def receive_exam(kind, value, error):
        fetch_exam.setEnabled(exam.currentData() != 'manual')
        if exam.currentData() != kind:
            return
        if error:
            exam_status.setText('自动获取失败：%s。请重试或手动设置日期。' % error)
        elif exam_request_date[0] != deadline.date():
            exam_status.setText('已保留手动修改的日期；官方日期为 %s。' % value)
        else:
            deadline_enabled.setChecked(True)
            deadline.setDate(QDate.fromString(value, 'yyyy-MM-dd'))
            exam_status.setText('日期来自中国教育考试网四六级报名首页；请以准考证为准。')
    exam_bridge.finished.connect(receive_exam)
    def request_exam():
        kind = exam.currentData()
        if kind == 'manual':
            return
        exam_request_date[0] = deadline.date()
        fetch_exam.setEnabled(False)
        exam_status.setText('正在读取中国教育考试网…')
        def work():
            try:
                value, error = fetch_cet(), ''
            except Exception as exc:
                value, error = '', str(exc) or '网络不可用'
            try:
                exam_bridge.finished.emit(kind, value, error)
            except RuntimeError:
                pass
        threading.Thread(target=work, daemon=True).start()
    def select_exam(_index):
        fetch_exam.setEnabled(exam.currentData() != 'manual')
        if exam.currentData() != 'manual':
            request_exam()
        else:
            exam_status.setText('请根据报名信息或准考证手动设置考试日期。')
    exam.currentIndexChanged.connect(select_exam)
    fetch_exam.clicked.connect(request_exam)
    plan_summary = QLabel()
    plan_summary.setWordWrap(True)
    review_auto_word = QCheckBox("揭晓后自动朗读单词")
    review_auto_word.setChecked(bool(cfg["review_auto_word"]))
    review_hint_audio = QCheckBox("字母提示时朗读该字母")
    review_hint_audio.setChecked(bool(cfg["review_hint_audio"]))
    review_auto_example = QComboBox()
    for label, value in (("第一条例句", "first"), ("不自动朗读", "off"), ("普通例句", "example"), ("权威例句", "authority"), ("所有例句", "all")):
        review_auto_example.addItem(label, value)
    review_auto_example.setCurrentIndex(max(0, review_auto_example.findData(cfg["review_auto_example_mode"])))
    review_core = QCheckBox("优先学习四六级核心词（到期复习仍优先）")
    review_core.setChecked(bool(cfg.get("review_core_enabled", True)))
    review_book = QComboBox()
    review_book.setObjectName('reviewBook')
    review_book.addItem('所选牌组', '')
    review_book.addItem('六级核心词汇', 'cet6_core')
    review_book.addItem('六级完整词书（ECDICT + 核心补充）', 'cet6_full')
    review_book.addItem('四级词书（KyleBing）', 'cet4_kyle')
    review_book.addItem('六级词书（KyleBing）', 'cet6_kyle')
    review_book.setCurrentIndex(max(0, review_book.findData(cfg.get('review_book', ''))))
    review_smart = QCheckBox("到期单词提前提醒（每 5 分钟检查）")
    review_smart.setChecked(bool(cfg["review_smart"]))
    selected_decks = review_decks(cfg)
    deck_choices = QWidget()
    deck_choices.setObjectName('reviewExtraDeck')
    deck_choices_layout = QVBoxLayout(deck_choices)
    deck_choices_layout.setContentsMargins(0, 0, 0, 0)
    deck_choices_layout.setSpacing(3)
    deck_checks = []
    for name in list(deck_names) + [name for name in selected_decks if name not in deck_names]:
        check = QCheckBox(name if name in deck_names else name + '（未找到）')
        check.setProperty('deckName', name)
        check.setChecked(name in selected_decks)
        deck_choices_layout.addWidget(check)
        deck_checks.append(check)
    def extra_decks_value():
        return [check.property('deckName') for check in deck_checks if check.isChecked()]
    def mark_main_deck(*_args):
        for check in deck_checks:
            name = check.property('deckName')
            main = name == main_review_deck.currentData()
            check.setText(name + ('（主牌组）' if main else '' if name in deck_names else '（未找到）'))
            if main:
                check.setChecked(True)
            check.setEnabled(not main)
    main_review_deck.currentIndexChanged.connect(mark_main_deck)
    mark_main_deck()
    review_position = QComboBox()
    review_position.addItem("屏幕右下角", "corner")
    review_position.addItem("屏幕中央", "center")
    review_position.setCurrentIndex(max(0, review_position.findData(cfg["review_position"])))
    review_theme = QComboBox()
    review_theme.addItem("浅色", "light")
    review_theme.addItem("深色", "dark")
    review_theme.setCurrentIndex(max(0, review_theme.findData(cfg["review_theme"])))
    review_modes_widget = QWidget()
    review_modes_widget.setObjectName('reviewModes')
    review_modes_layout = QVBoxLayout(review_modes_widget)
    review_modes_layout.setContentsMargins(0, 0, 0, 0)
    review_modes_layout.setSpacing(3)
    chosen_modes = selected_review_modes(cfg)
    mode_checks = []
    for label, value in (("英文选中文", "choice"), ("中文选英文", "reverse"),
                         ("释义拼写", "typing"), ("例句填空", "cloze"),
                         ("听音拼写", "listening"), ("单词释义判断", "judgment"),
                         ("口语回忆（自主评分）", "speaking")):
        check = QCheckBox(label)
        check.setProperty('reviewMode', value)
        check.setChecked(value in chosen_modes)
        review_modes_layout.addWidget(check)
        mode_checks.append(check)
    def review_modes_value():
        return [check.property('reviewMode') for check in mode_checks if check.isChecked()]
    known_style = QComboBox()
    for label, value in (("下划线", "underline"), ("加粗", "bold"), ("不特别标记", "none")):
        known_style.addItem(label, value)
    known_style.setCurrentIndex(max(0, known_style.findData(cfg["review_known_style"])))
    review_beautify = QCheckBox("美化本牌组的 Anki 单词卡")
    review_beautify.setChecked(bool(cfg["review_beautify"]))
    review_start_at_login = QCheckBox("Windows 登录时启动 Anki 后台复习")
    review_start_at_login.setChecked(bool(cfg["review_start_at_login"]))
    form = section('划词与 Anki 同步')
    form.addRow("收词方式", mode)
    form.addRow("Anki 牌组", deck)
    form.addRow("笔记类型", model)
    form.addRow("单词字段", front)
    form.addRow("释义字段", back)
    form.addRow("预览确认有效期", confirm_seconds)
    form.addRow("全局快捷键", shortcut)
    form.addRow(shortcut_status)
    form.addRow(QLabel("点击快捷键输入框后按组合键；自动收词会暂存并恢复剪贴板。"))
    form = section('复习提醒')
    form.addRow("随身复习", review_enabled)
    form.addRow("弹出间隔", review_interval)
    form.addRow("记忆复习", review_smart)
    form.addRow("核心词优先", review_core)
    form.addRow("复习词书", review_book)
    form.addRow("主复习牌组", main_review_deck)
    form.addRow("补充复习牌组（可多选）", deck_choices)
    extra_help = QLabel("选择“所选牌组”时，计划统计主复习牌组及勾选的牌组，并仅统计上方所选笔记类型；选择词书时按标签跨牌组统计。复习遵守 Anki 每日新卡额度。")
    extra_help.setWordWrap(True)
    form.addRow(extra_help)
    form.addRow("后台运行", review_start_at_login)
    form = section('学习计划与考试')
    form.addRow("学习方式", plan_mode)
    form.addRow("固定每组数量", review_batch)
    batch_help = QLabel()
    batch_help.setWordWrap(True)
    form.addRow(batch_help)
    form.addRow("每日目标（新词和复习合计）", daily_goal)
    form.addRow("每天使用电脑（未启用时段时）", computer_hours)
    form.addRow("学习时段", windows_enabled)
    form.addRow("每日时段（同一天内）", windows_widget)
    form.addRow("考试类型", exam)
    form.addRow("官方日期", fetch_exam)
    form.addRow(exam_status)
    exam_link = QLabel('<a href="https://cet-kw.neea.edu.cn/Home/Index">四六级</a>　'
                       '<a href="https://ielts.neea.cn/">雅思</a>　'
                       '<a href="https://toefl.neea.cn/">托福</a>　官方报名')
    exam_link.setOpenExternalLinks(True)
    form.addRow(exam_link)
    form.addRow("截止日期", deadline_enabled)
    form.addRow("考试日期", deadline)
    form.addRow("今日计划估算", plan_summary)
    form = section('卡片显示与朗读')
    form.addRow("弹出位置", review_position)
    form.addRow("弹窗主题", review_theme)
    form.addRow("练习形式（可多选）", review_modes_widget)
    mode_help = QLabel("从所选题型中随机出题；例句不足时使用其他已选题型。")
    mode_help.setWordWrap(True)
    form.addRow(mode_help)
    form.addRow("已收录单词标记", known_style)
    form.addRow("自动发音", review_auto_word)
    form.addRow("字母提示发音", review_hint_audio)
    form.addRow("例句发音", review_auto_example)
    form.addRow("卡片外观", review_beautify)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName('saveSettings')
    buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
    validity = QLabel()
    validity.setWordWrap(True)
    outer.addWidget(validity)
    def update_validity(*_args):
        fields = fields_for_model()
        problems = []
        if deck.currentData() not in deck_names or model.currentData() not in model_names:
            problems.append('请选择有效的牌组和笔记类型。')
        if not review_book.currentData() and main_review_deck.currentData() not in deck_names:
            problems.append('请选择有效的主复习牌组。')
        if front.currentData() not in fields or back.currentData() not in fields or front.currentData() == back.currentData():
            problems.append('单词字段和释义字段需要存在且不同。')
        if not review_modes_value():
            problems.append('请至少选择一种练习形式。')
        if not shortcut.valid:
            problems.append('请重新录入有效的快捷键。')
        if not review_book.currentData() and any(name not in deck_names for name in extra_decks_value()):
            problems.append('请取消选择未找到的补充牌组。')
        if plan_mode.currentData() == 'daily' and daily_goal.value() == 0:
            if not deadline_enabled.isChecked():
                problems.append('自动分组需要设置每日目标或考试日期。')
            elif deadline.date() < QDate.currentDate():
                problems.append('考试日期已过，请更新日期或设置每日目标。')
        if windows_enabled.isChecked() and not validate_windows(windows_value()):
            problems.append('学习时段须开始早于结束，且不能重叠。')
        buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(not problems)
        validity.setText('\n'.join(problems))
    model.currentIndexChanged.connect(lambda _index: refresh_fields())
    shortcut.feedback.connect(update_validity)
    for selector in (deck, main_review_deck, front, back):
        selector.currentIndexChanged.connect(update_validity)
    review_book.currentIndexChanged.connect(update_validity)
    for check in deck_checks + mode_checks:
        check.toggled.connect(update_validity)
    refresh_fields(initial=True)
    def update_plan(*_args):
        if plan_mode.currentData() != 'daily':
            plan_summary.setText('固定每组数量；复习时间由 Anki 决定。')
            return
        if deck.currentData() not in deck_names or model.currentData() not in model_names:
            plan_summary.setText('请选择有效牌组和笔记类型。')
            return
        preview = dict(cfg, deck=deck.currentData(), model=model.currentData(),
                       review_main_deck=main_review_deck.currentData(),
                       review_extra_decks=extra_decks_value(),
                       review_book=review_book.currentData(),
                       review_deadline=deadline.date().toString('yyyy-MM-dd') if deadline_enabled.isChecked() else '',
                       review_daily_goal=daily_goal.value(), review_computer_hours=computer_hours.value(),
                       review_windows_enabled=windows_enabled.isChecked(), review_windows=windows_value(),
                       review_interval_minutes=review_interval.value())
        try:
            plan = collection_plan(lambda _action, params: mw.col.find_cards(params['query']), preview)
            days = ('距截止日期含今天 %d 天；' % plan['days']) if plan['days'] is not None else ''
            plan_summary.setText(days + '今日新学：已学 %d / 目标 %d（剩余 %d）；复习：已复习 %d / 目标 %d（剩余 %d）；每组约 %d 张。'
                                 % (plan['new_done'], plan['new_goal'], plan['new_remaining'], plan['review_done'],
                                    plan['review_goal'], plan['review_remaining'], plan['batch']) +
                                 (' 当前可用组数不足，尚差约 %d 张的容量；可缩短间隔或增加学习时段。' % plan['capacity_shortfall'] if plan['capacity_shortfall'] else '') +
                                 ' 当前范围剩余新卡 %d 张；仅统计所选笔记类型。按 Anki 学习日统计，复习日期与每日上限由 Anki 控制。' % plan['remaining_new_total'])
        except Exception:
            plan_summary.setText('暂时无法读取牌组计划，请检查牌组。')
    for control, signal in ((plan_mode, 'currentIndexChanged'), (deck, 'currentIndexChanged'), (main_review_deck, 'currentIndexChanged'),
                            (review_book, 'currentIndexChanged'),
                            (model, 'currentIndexChanged'),
                            (daily_goal, 'valueChanged'), (computer_hours, 'valueChanged'),
                            (review_interval, 'valueChanged'), (deadline, 'dateChanged'),
                            (deadline_enabled, 'toggled')):
        getattr(control, signal).connect(update_plan)
    for check in deck_checks:
        check.toggled.connect(update_plan)
    for control, signal in ((plan_mode, 'currentIndexChanged'), (daily_goal, 'valueChanged'),
                            (deadline_enabled, 'toggled'), (deadline, 'dateChanged')):
        getattr(control, signal).connect(update_validity)
    def windows_changed(*_args):
        for _, _, _, _, remove in window_rows:
            remove.setEnabled(len(window_rows) > 3)
        windows_widget.setEnabled(windows_enabled.isChecked())
        update_dependencies()
        update_validity()
        update_plan()
    def update_dependencies(*_args):
        auto_plan = plan_mode.currentData() == 'daily'
        review_batch.setEnabled(not auto_plan)
        daily_goal.setEnabled(auto_plan)
        computer_hours.setEnabled(auto_plan and not windows_enabled.isChecked())
        batch_help.setText('自动计划决定每组张数，固定数量暂不生效；完成目标后手动开始为 1 张。' if auto_plan
                           else '按固定数量学习；切换为自动计划后，每组数量由每日目标计算。')
        confirm_seconds.setEnabled(mode.currentData() == 'preview')
        shortcut.setEnabled(mode.currentData() != 'auto')
        shortcut_status.setText('自动收词无需快捷键；切回快捷键模式后原设置仍保留。' if mode.currentData() == 'auto'
                                else '点击输入框录入快捷键；保存时会检查是否注册成功。')
    mode.currentIndexChanged.connect(update_dependencies)
    plan_mode.currentIndexChanged.connect(update_dependencies)
    windows_enabled.toggled.connect(windows_changed)
    windows_changed()
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    outer.addWidget(buttons)
    class WheelGuard(QObject):
        def __init__(self):
            super().__init__(dialog)
            self.active = None

        def eventFilter(self, watched, event):
            if not isinstance(watched, QWidget) or watched.window() is not dialog:
                return False
            widget = watched
            while widget is not None and widget is not dialog and not isinstance(widget, (QComboBox, QSpinBox, QDateEdit, QTimeEdit)):
                widget = widget.parentWidget()
            control = widget if isinstance(widget, (QComboBox, QSpinBox, QDateEdit, QTimeEdit)) else None
            if event.type() == QEvent.Type.MouseButtonPress and control is not None:
                self.active = control
            elif event.type() == QEvent.Type.MouseButtonPress and self.active is not None and not watched.isAncestorOf(self.active):
                self.active = None
            elif event.type() == QEvent.Type.Wheel and control is not None:
                focus = QApplication.focusWidget()
                if control is self.active and (control.hasFocus() or (focus is not None and control.isAncestorOf(focus))):
                    return False
                bar = scroll.verticalScrollBar()
                pixels = event.pixelDelta().y()
                delta = pixels if pixels else event.angleDelta().y() * bar.singleStep() * 3 / 120
                bar.setValue(bar.value() - int(delta))
                return True
            return False
    guard = WheelGuard()
    app = QApplication.instance()
    app.installEventFilter(guard)
    try:
        result = dialog.exec()
    finally:
        app.removeEventFilter(guard)
    if result != QDialog.DialogCode.Accepted:
        return
    cfg.update({"mode": mode.currentData(), "deck": deck.currentData(), "model": model.currentData(),
                "front_field": front.currentData(), "back_field": back.currentData(),
                "modifiers": shortcut.modifiers, "virtual_key": shortcut.virtual_key,
                "confirm_seconds": int(confirm_seconds.currentData()),
                "review_enabled": review_enabled.isChecked(),
                "review_interval_minutes": review_interval.value(),
                "review_batch_size": review_batch.value(),
                "review_plan_mode": plan_mode.currentData(),
                "review_daily_goal": daily_goal.value(),
                "review_computer_hours": computer_hours.value(),
                "review_deadline": deadline.date().toString('yyyy-MM-dd') if deadline_enabled.isChecked() else '',
                "review_exam": exam.currentData(),
                "review_windows_enabled": windows_enabled.isChecked(),
                "review_windows": windows_value(),
                "review_auto_word": review_auto_word.isChecked(),
                "review_hint_audio": review_hint_audio.isChecked(),
                "review_auto_example_mode": review_auto_example.currentData(),
                "review_smart": review_smart.isChecked(),
                "review_core_enabled": review_core.isChecked(),
                "review_main_deck": main_review_deck.currentData(),
                "review_book": review_book.currentData(),
                "review_extra_decks": extra_decks_value(),
                "review_position": review_position.currentData(),
                "review_theme": review_theme.currentData(),
                "review_modes": review_modes_value(),
                "review_known_style": known_style.currentData(),
                "review_beautify": review_beautify.isChecked(),
                "review_start_at_login": review_start_at_login.isChecked()})
    listener_changed = any(cfg[key] != original[key] for key in ('mode', 'modifiers', 'virtual_key'))
    if listener_changed:
        controller.cancel_pending()
        controller.listener.stop()
        controller.listener.join(timeout=2)
        if controller.listener.is_alive():
            show_feedback('快捷键设置失败：原监听器未退出，请稍后重试。', period=9000)
            return
        candidate = NativeListener(controller.bridge, cfg, report_status=False)
        candidate.start()
        if not candidate.ready.wait(2) or not candidate.registered:
            candidate.stop()
            candidate.join(timeout=2)
            controller.listener = NativeListener(controller.bridge, original, report_status=False)
            controller.listener.start()
            restored = controller.listener.ready.wait(2) and controller.listener.registered
            reason = candidate.registration_error or '监听器未能及时启动'
            show_feedback('快捷键设置失败：%s；%s。' % (reason, '已恢复原快捷键' if restored else '原快捷键未能恢复，请重启 Anki'), period=10000)
            return
        controller.listener = candidate
    startup_error = ''
    if cfg['review_start_at_login'] != original['review_start_at_login']:
        try:
            configure_login_start(cfg['review_start_at_login'])
        except Exception as error:
            startup_error = str(error)
            cfg['review_start_at_login'] = original['review_start_at_login']
    try:
        save_settings(cfg)
    except Exception as error:
        if listener_changed:
            controller.listener.stop()
            controller.listener.join(timeout=2)
            controller.listener = NativeListener(controller.bridge, original, report_status=False)
            controller.listener.start()
            controller.listener.ready.wait(2)
        show_feedback('设置保存失败：%s；请检查后重试。' % error, period=10000)
        return
    if not controller.review.dialog:
        controller.review.start()
    if startup_error:
        show_feedback('其他设置已保存；开机启动设置失败：%s。' % startup_error, period=10000)
    elif not controller.listener.registered:
        show_feedback('设置已保存，但快捷键未注册：%s。' % (controller.listener.registration_error or '监听器未启动'), period=10000)
    else:
        show_feedback("设置已保存；全局快捷键 %s 已注册。" % format_shortcut(cfg['modifiers'], cfg['virtual_key']), period=5000)


def menu_action():
    action = mw.form.menuTools.addAction("全局划词入 Anki 设置…")
    action.triggered.connect(open_settings)
    review_action = mw.form.menuTools.addAction("单词随身复习：立即弹出一张")
    review_action.triggered.connect(lambda: controller.review.show_next(True))
    core_action = mw.form.menuTools.addAction("四六级核心词：补充缺失词汇")
    core_action.triggered.connect(import_core_words)
    browse_action = mw.form.menuTools.addAction("四六级核心词：查看词表")
    browse_action.triggered.connect(browse_core_words)
    setup_books = mw.form.menuTools.addAction("六级词书：建立核心与完整词书")
    setup_books.triggered.connect(setup_cet6_books)
    core_book = mw.form.menuTools.addAction("六级词书：浏览核心词汇")
    core_book.triggered.connect(lambda: browse_cet6_book('cet6_core'))
    full_book = mw.form.menuTools.addAction("六级词书：浏览完整词汇")
    full_book.triggered.connect(lambda: browse_cet6_book('cet6_full'))
    cet4_kyle = mw.form.menuTools.addAction("四级词书（KyleBing）：查看词汇")
    cet4_kyle.triggered.connect(lambda: browse_cet6_book('cet4_kyle'))
    cet6_kyle = mw.form.menuTools.addAction("六级词书（KyleBing）：查看词汇")
    cet6_kyle.triggered.connect(lambda: browse_cet6_book('cet6_kyle'))
    listening = mw.form.menuTools.addAction("六级听力：本地真题与模拟")
    listening.triggered.connect(open_cet6_listening)
    return action, review_action


def import_core_words():
    cfg = dict(settings())
    show_feedback('正在核对核心词表；只补充缺失的词，请稍候。')
    def work():
        try:
            result = core_import.import_missing(api, cfg, dictionary)
            message = '核心词表：已有 %d 个，新增 %d 个' % (result['existing'], result['added'])
            if result['failed']:
                message += '；%d 个未取得释义或未能添加，可稍后重试。' % len(result['failed'])
        except Exception as error:
            message = '核心词表整理失败：%s' % error
        mw.taskman.run_on_main(lambda: show_feedback(message, period=10000))
    threading.Thread(target=work, daemon=True).start()


def setup_cet6_books():
    cfg = dict(settings())
    show_feedback('正在整理六级词书，保留已有卡片的学习进度…')
    def work():
        try:
            result = cet6_books.setup_books(api, cfg, dictionary)
            message = '六级词书已整理：完整词书已有 %d 个，核心已有 %d 个，新增 %d 个。' % (result['existing_full'], result['existing_core'], result['added'])
            if result['failed']:
                message += ' %d 个未添加，可重新整理。' % len(result['failed'])
        except Exception as error:
            message = '六级词书整理未完成：%s' % error
        mw.taskman.run_on_main(lambda: show_feedback(message, period=15000))
    threading.Thread(target=work, daemon=True).start()


def browse_cet6_book(book):
    def work():
        try:
            api('guiBrowse', {'query': 'tag:' + BOOK_TAGS[book]})
        except Exception as error:
            message = '无法打开词书：%s' % error
            mw.taskman.run_on_main(lambda: show_feedback(message, period=10000))
    threading.Thread(target=work, daemon=True).start()


def open_cet6_listening():
    existing = getattr(controller, 'cet6_listening_dialog', None)
    if existing and existing.isVisible():
        existing.raise_()
        existing.activateWindow()
        return
    dialog = cet6_listening.ListeningPractice(popup_style(settings()))
    controller.cet6_listening_dialog = dialog
    dialog.finished.connect(lambda _result: setattr(controller, 'cet6_listening_dialog', None))
    dialog.show()


def browse_core_words():
    cfg = dict(settings())
    def work():
        try:
            api('guiBrowse', {'query': core_import.browse_query(cfg)})
        except Exception as error:
            message = '无法打开核心词表：%s' % error
            mw.taskman.run_on_main(lambda: show_feedback(message, period=10000))
    threading.Thread(target=work, daemon=True).start()


def add_review_to_toolbar(links, toolbar):
    links.append(toolbar.create_link(
        'zvr-desktop-review', '单词复习', open_review_from_toolbar,
        tip='立即开始单词随身复习', id='zvr-desktop-review'))
    links.append(toolbar.create_link(
        'zvr-cet4-book', '四级词书', lambda: open_kyle_book('cet4_kyle'),
        tip='切换到四级词书并开始弹窗学习', id='zvr-cet4-book'))
    links.append(toolbar.create_link(
        'zvr-cet6-book', '六级词书', lambda: open_kyle_book('cet6_kyle'),
        tip='切换到六级词书并开始弹窗学习', id='zvr-cet6-book'))


def open_kyle_book(book):
    if mw.col is None or book not in ('cet4_kyle', 'cet6_kyle'):
        show_feedback('请先打开 Anki 账户。')
        return
    if controller.review.dialog or controller.review.busy:
        show_feedback('请先关闭当前复习卡，再切换词书。')
        return
    cfg = dict(settings())
    model = cfg['model'].replace('\\', '\\\\').replace('"', '\\"')
    if not mw.col.find_cards('note:"%s" tag:%s -is:suspended -is:buried' % (model, BOOK_TAGS[book])):
        show_feedback('该词书没有可用卡片，请检查词书是否已导入。')
        return
    try:
        cfg['review_book'] = book
        save_settings(cfg)
    except Exception as error:
        show_feedback('切换词书失败：%s' % error)
        return
    controller.review.show_next(True)


def add_study_dashboard(_browser, content):
    cfg = settings()
    if mw.col is None or (not cfg.get('review_deadline') and cfg.get('review_plan_mode') != 'daily'):
        return
    try:
        import datetime
        from aqt.theme import theme_manager
        today = datetime.date.today()
        plan = collection_plan(lambda _action, params: mw.col.find_cards(params['query']), cfg)
        selected = set()
        book_tag = BOOK_TAGS.get(cfg.get('review_book'))
        for deck_name in ([None] if book_tag else review_decks(cfg)):
            escaped_deck = (deck_name or '').replace('\\', '\\\\').replace('"', '\\"')
            escaped_model = cfg['model'].replace('\\', '\\\\').replace('"', '\\"')
            query = 'note:"%s" tag:%s' % (escaped_model, book_tag) if book_tag else 'deck:"%s" note:"%s"' % (escaped_deck, escaped_model)
            selected.update(mw.col.find_cards(query))
        start = datetime.datetime.combine(today - datetime.timedelta(days=27), datetime.time.min).timestamp()
        rows = mw.col.db.all('select cid, id from revlog where id >= ?', int(start * 1000))
        activity = activity_counts(rows, selected, today)
        content.stats += dashboard_html(today, cfg.get('review_deadline', ''), plan, activity,
                                        bool(theme_manager.night_mode), cfg.get('review_plan_mode') == 'daily')
    except Exception as error:
        log_runtime('study dashboard unavailable: %s' % type(error).__name__)


def open_review_from_toolbar():
    log_runtime('desktop review toolbar clicked')
    controller.review.show_next(True)


def ensure_anki_connect():
    addon_path = mw.addonManager.addonsFolder('2055492159')
    if os.path.isdir(addon_path):
        if not mw.addonManager.isEnabled('2055492159'):
            show_feedback('AnkiConnect 已安装但处于停用状态，启用并重启 Anki 后可同步。', period=10000)
        return
    def check():
        try:
            if api('version', {}, timeout=2):
                return
        except Exception:
            pass
        mw.taskman.run_on_main(install)
    def install():
        if os.path.isdir(addon_path):
            return
        try:
            from aqt.addons import download_addons, download_encountered_problem
            def done(log):
                if download_encountered_problem(log) or not os.path.isdir(addon_path):
                    show_feedback('AnkiConnect 自动安装失败，请检查网络后重启 Anki。', period=10000)
                else:
                    show_feedback('AnkiConnect 已安装，请重启 Anki 以启用同步。', period=12000)
            download_addons(mw, mw.addonManager, [2055492159], done)
        except Exception as error:
            log_runtime('AnkiConnect setup failed: %s' % type(error).__name__)
            show_feedback('AnkiConnect 自动安装未能启动，请检查网络和附加组件设置。', period=10000)
    threading.Thread(target=check, daemon=True).start()


def on_main_window_ready():
    mw.toolbar.redraw()
    ensure_anki_connect()
    if settings().get("review_start_at_login", False):
        try:
            configure_login_start(True)
            log_runtime("background review login startup configured")
        except Exception as error:
            log_runtime("login startup setup failed: %s" % type(error).__name__)
            QTimer.singleShot(1000, lambda message=str(error): show_feedback("后台开机启动未能设置：%s" % message, period=7000))
    if os.environ.pop("ZVR_BACKGROUND_REVIEW", "") == "1":
        QTimer.singleShot(1500, mw.showMinimized)


try:
    controller = Controller()
    controller.review.open_settings = open_settings
    controller.review.dictionary = dictionary
    controller.review.add_word = controller.add_note
    log_runtime("desktop review controller initialized")
    menu_action_ref = menu_action()
    gui_hooks.top_toolbar_did_init_links.append(add_review_to_toolbar)
    gui_hooks.card_will_show.append(controller.review.style_card)
    gui_hooks.deck_browser_will_render_content.append(add_study_dashboard)
    gui_hooks.profile_did_open.append(controller.review.start)
    gui_hooks.profile_will_close.append(controller.stop)
    gui_hooks.main_window_did_init.append(on_main_window_ready)
    QTimer.singleShot(1500, lambda: controller.review.start() if mw.col else None)
except Exception:
    log_path = os.path.join(tempfile.gettempdir(), "zotero_global_capture_startup_error.txt")
    with open(log_path, "w", encoding="utf-8") as error_log:
        traceback.print_exc(file=error_log)
    raise
