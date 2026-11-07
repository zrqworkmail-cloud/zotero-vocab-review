"""Windows global selection capture for Anki, using its existing AnkiConnect service."""

from __future__ import annotations

import ctypes
import datetime
import html
import json
import os
import re
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes

from aqt import gui_hooks, mw
from aqt.qt import (
    QApplication, QCheckBox, QComboBox, QDate, QDateEdit, QDialog, QDialogButtonBox, QEvent, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QRadioButton, QScrollArea, QTimer, QVBoxLayout,
    QWidget, QObject, pyqtSignal, Qt, QCursor, QSpinBox, QTime, QTimeEdit,
)

from .background import configure_login_start
from . import card_motion
from .review_popup import DesktopReviewController, enable_click_away, popup_style
from .review_logic import (BOOK_MIGRATION, apply_auto_sync_preference, book_clause, book_label, book_progress,
                           collection_plan, hide_instead_of_quit, background_instead_of_quit, install_sync_error_guard, resolve_book_decks,
                           study_book, study_book_id, study_books, selected_review_modes, sync_due,
                           MODE_LABELS, MODE_ORDER,
                           quit_request_path, take_quit_request, MASTERED_TAG,
                           validate_windows, window_minutes)
from .exam_dates import fetch_cet
from .study_dashboard import activity_counts, dashboard_html
from . import core_import, cet6_books, cet6_listening, audio_volume, speech, review_logic, review_quality


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
    "review_pin": True,
    "hide_main_on_close": True,
    "sync_background": True,
    "sync_background_minutes": 5,
    "anki_auto_sync_remembered": None,
    "review_smart": True,
    "review_core_enabled": True,
    "review_book": "",
    "study_book": "",
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
    # The answer face used to lay out every example the note carries, which is the tallest
    # block on the card and the one the learner reads least. On by default, because that is
    # what an existing install already does.
    "review_show_example": True,
    # 'suspend' is what 已掌握 has always meant; 'easy' hands the same judgement to the
    # scheduler instead of taking the word out of it. Switching never moves existing cards.
    "review_mastered_action": "suspend",
    "review_auto_example": False,
    "review_auto_example_mode": "first",
    # Anki's own text-to-speech sits around -21 dBFS, which reads as quiet on a laptop;
    # 100% means "leave Anki's player exactly as it is", so this is a gain, not a volume
    # that can only be turned down.
    "review_volume": audio_volume.DEFAULT,
    "review_known_style": "underline",
    "review_position": "corner",
    "review_theme": "light",
    "review_mode": "mixed",
    "review_beautify": True,
    # 拼写题的动效档位：full = 字母跳跃 + 庆祝徽章 + 星芒/彩带；calm = 只留跳跃与徽章；
    # off = 完全不画。默认 full 是用户 2026-11-04 批准样稿时定的。
    "review_motion": "full",
    "review_motion_hop": True,
    "review_motion_celebration": True,
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


def collection_api(action, params):
    """Adapt Anki's in-process collection to the action/params shape review_logic
    speaks, so the settings preview and the dashboard can share one code path."""
    if action == 'deckNames':
        return [entry.name for entry in mw.col.decks.all_names_and_ids(include_filtered=False)]
    return mw.col.find_cards(params['query'])


def local_tags():
    """Every tag registered in this collection, read through Anki's own tag API.

    Querying the tags table by SQL is wrong — it has no `name` column — and because
    the exception used to be swallowed here the settings list silently emptied
    instead of failing loudly. None now means "could not read", so the dialog can
    say that rather than claim the account has no tags.
    """
    try:
        return sorted(str(tag) for tag in mw.col.tags.all())
    except Exception as error:
        log_runtime("tag list unavailable: %s" % type(error).__name__)
        return None


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
    # Localhost must not ride the system proxy, and a brief AnkiConnect hiccup must not
    # cost a rating: retry transient connection failures, but leave the reason in the log.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            with opener.open(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
            if value.get("error"):
                raise RuntimeError(value["error"])
            return value.get("result")
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt >= attempts:
                log_runtime("AnkiConnect request failed: action=%s error=%s" % (action, error))
                raise
            log_runtime("AnkiConnect transient failure: action=%s attempt=%d/%d error=%s"
                        % (action, attempt, attempts, error))
            time.sleep(0.2 * attempt)


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
        self.main_close_filter = None
        self.sync_timer = None
        self.quit_timer = None

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
    def populate(combo, names, selected, optional=False, keep_missing=True):
        combo.clear()
        if optional:
            combo.addItem('不使用补充牌组', '')
        for name in names:
            combo.addItem(name, name)
        # The capture deck keeps its dead entry: silently moving where new words land
        # is worse than an ugly dropdown. The review deck drops it — it only ever
        # matched nothing, and the note under the picker says so.
        if keep_missing and selected and selected not in names:
            combo.addItem('%s（未找到）' % selected, selected)
        combo.setCurrentIndex(max(0, combo.findData(selected)))
    populate(deck, deck_names, cfg['deck'])
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
    hide_main = QCheckBox('点主窗口关闭按钮时只隐藏，不退出 Anki')
    hide_main.setObjectName('hideMainOnClose')
    hide_main.setChecked(bool(cfg.get('hide_main_on_close', True)))
    sync_back = QCheckBox('后台静默同步（不再在打开和关闭 Anki 时等待同步）')
    sync_back.setObjectName('syncBackground')
    sync_back.setChecked(bool(cfg.get('sync_background', True)))
    sync_minutes = QSpinBox()
    sync_minutes.setObjectName('syncBackgroundMinutes')
    sync_minutes.setRange(1, 120)
    sync_minutes.setSuffix(" 分钟")
    sync_minutes.setValue(int(cfg.get('sync_background_minutes', 5) or 5))
    review_interval = QSpinBox()
    review_interval.setRange(5, 240)
    review_interval.setSuffix(" 分钟")
    review_interval.setValue(int(cfg["review_interval_minutes"]))
    review_batch = QSpinBox()
    review_batch.setObjectName('reviewBatch')
    review_batch.setRange(1, 999)
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
    # Off means the answer face stops laying out 例句/权威例句 cards. 例句填空 keeps its
    # sentence (the question is the example), and the 例句 hint button stays offered — asking
    # for one is a choice the learner makes, and it counts as a hint.
    review_show_example = QCheckBox("答案面显示例句（例句填空和「例句」提示按钮不受影响）")
    review_show_example.setChecked(bool(cfg.get("review_show_example", True)))
    # 「已掌握」used to mean exactly one thing — suspend — which quietly contradicts spaced
    # repetition: a parked card is never tested again. The rate mode expresses the same
    # judgement in the scheduler's language. Default stays suspend, and switching modes does
    # not move the cards that are already suspended; the quality report lists them instead.
    review_mastered_action = QComboBox()
    review_mastered_action.setObjectName('masteredAction')
    review_mastered_action.addItem("挂起：不再出现，随时可恢复", "suspend")
    review_mastered_action.addItem("按 Easy 评分：留在排程里，间隔由 Anki 算", "easy")
    review_mastered_action.setCurrentIndex(max(0, review_mastered_action.findData(
        cfg.get("review_mastered_action", "suspend") or "suspend")))
    review_auto_example = QComboBox()
    for label, value in (("第一条例句", "first"), ("不自动朗读", "off"), ("普通例句", "example"), ("权威例句", "authority"), ("所有例句", "all")):
        review_auto_example.addItem(label, value)
    review_auto_example.setCurrentIndex(max(0, review_auto_example.findData(cfg["review_auto_example_mode"])))
    # Anki has no volume control, so this dial is the plug-in's own gain on the player that
    # speaks the word. It applies while it is being moved, and 试听 says a word at it, so
    # the setting can be judged by ear without closing the dialog and restarting Anki.
    review_volume = QSpinBox()
    review_volume.setObjectName('reviewVolume')
    review_volume.setRange(audio_volume.FLOOR, audio_volume.CEILING)
    review_volume.setSingleStep(10)
    review_volume.setSuffix(' %')
    review_volume.setValue(audio_volume.clamp(cfg.get('review_volume', audio_volume.DEFAULT)))
    volume_preview_button = QPushButton('试听')
    volume_preview_button.setObjectName('volumePreview')
    volume_widget = QWidget()
    volume_row = QHBoxLayout(volume_widget)
    volume_row.setContentsMargins(0, 0, 0, 0)
    volume_row.setSpacing(8)
    volume_row.addWidget(review_volume)
    volume_row.addWidget(volume_preview_button)
    volume_row.addStretch(1)
    review_volume.valueChanged.connect(lambda value: apply_review_volume(int(value)))
    volume_preview_button.clicked.connect(lambda _checked=False: volume_preview(int(review_volume.value())))
    review_core = QCheckBox("优先学习四六级核心词（到期复习仍优先）")
    review_core.setChecked(bool(cfg.get("review_core_enabled", True)))
    # The book list is the whole scope model now: pick one named book here and every
    # card says which book it came from. Books whose tag or deck is not actually in
    # this collection are not offered, so the list can never drift away from reality.
    known_tags = local_tags()
    available_books = [book for book in study_books(cfg)
                       if (book.get('tag') and known_tags and book['tag'] in known_tags)
                       or (book.get('deck') and book['deck'] in deck_names)]
    chosen_book = study_book_id(cfg)
    book_choices = QWidget()
    book_choices.setObjectName('studyBookList')
    book_choices_layout = QVBoxLayout(book_choices)
    book_choices_layout.setContentsMargins(0, 0, 0, 0)
    book_choices_layout.setSpacing(3)
    book_radios = []
    for book in available_books:
        radio = QRadioButton(book['name'])
        radio.setObjectName('studyBook')
        radio.setProperty('bookId', book['id'])
        radio.setToolTip('范围：%s' % (book.get('tag') or ('牌组 ' + book.get('deck', ''))))
        radio.setChecked(book['id'] == chosen_book)
        book_choices_layout.addWidget(radio)
        book_radios.append(radio)
    if not book_radios:
        book_choices_layout.addWidget(QLabel('这个账户里还没有可学的词书，请先导入词表或给卡片打标签。'))
    def book_value():
        return next((radio.property('bookId') for radio in book_radios if radio.isChecked()), '')
    review_smart = QCheckBox("到期单词提前提醒（每 5 分钟检查）")
    review_smart.setChecked(bool(cfg["review_smart"]))
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
    for value in MODE_ORDER:
        check = QCheckBox(MODE_LABELS[value])
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
    form.addRow("关闭主窗口", hide_main)
    form.addRow("后台同步", sync_back)
    form.addRow("同步间隔", sync_minutes)
    form.addRow("弹出间隔", review_interval)
    form.addRow("记忆复习", review_smart)
    form.addRow("核心词优先", review_core)
    form.addRow("学习词书（单选）", book_choices)
    extra_help = QLabel("选一本词书就开始学，卡片上会一直写着它的名字和进度。词书是标签视图，不是牌组：六级核心本来就是六级全表的一部分，而一张卡只能属于一个牌组，所以用标签才能并列。每日新卡上限仍按牌组计，由 Anki 控制。")
    extra_help.setObjectName('scopeHelp')
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
    form.addRow(review_show_example)
    form.addRow("「已掌握」按钮", review_mastered_action)
    form.addRow("例句发音", review_auto_example)
    form.addRow("朗读音量", volume_widget)
    volume_help = QLabel("100% 表示什么都不改。高于 100% 时，插件会用同一套系统语音把单词重新录一遍，"
                         "并把它推到接近满刻度（不会削波），再交给 Anki 播放——只影响插件朗读的单词和例句，"
                         "不会改动你自己牌组的音频。拖动即时生效，点「试听」当场听。")
    volume_help.setWordWrap(True)
    form.addRow(volume_help)
    form.addRow("卡片外观", review_beautify)
    # Two switches, not one three-way radio: the letter hop is feedback while you type and the
    # badge is the reward after it, and "letters still, no pop-up" is a thing people want.
    # A saved older `review_motion` still decides both when these two have never been written.
    motion_hop = QCheckBox("拼写时字母跳动")
    motion_hop.setObjectName('motionHop')
    motion_hop.setToolTip("打对字母在原格子里轻轻跳一下，打错左右抖一下。")
    motion_celebration = QCheckBox("答对时弹出庆祝特效")
    motion_celebration.setObjectName('motionCelebration')
    motion_celebration.setToolTip("一次写对时弹出金色立体庆祝字（UNBELIEVABLE / PERFECT / GREAT / NICE），"
                                  "高档还带星芒、三星和彩带。答错永远不弹。")
    motion_hop.setChecked(card_motion.hop_allowed(cfg))
    motion_celebration.setChecked(card_motion.celebration_allowed(cfg))
    form.addRow(motion_hop)
    form.addRow(motion_celebration)
    motion_help = QLabel("分工：第一个勾只管打字过程中的字母反馈（打对向上跳、打错左右抖），"
                         "第二个勾只管答对之后弹出的庆祝特效（立体字、星芒、缎带、宝石、彩带）。"
                         "两个互不影响：只关庆祝，字母照样跳；只关跳动，答对仍然弹徽章。都不勾就什么都不动。"
                         "卡片上再没有别的动效受这两个勾控制，评分、建议与排程也完全不受影响。")
    motion_help.setWordWrap(True)
    form.addRow(motion_help)
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
        if not book_value():
            problems.append('请选择一本要学的词书。')
        if front.currentData() not in fields or back.currentData() not in fields or front.currentData() == back.currentData():
            problems.append('单词字段和释义字段需要存在且不同。')
        if not review_modes_value():
            problems.append('请至少选择一种练习形式。')
        if not shortcut.valid:
            problems.append('请重新录入有效的快捷键。')
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
    for selector in (deck, front, back):
        selector.currentIndexChanged.connect(update_validity)
    for radio in book_radios:
        radio.toggled.connect(update_validity)
    for check in mode_checks:
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
                       study_book=book_value(),
                       review_deadline=deadline.date().toString('yyyy-MM-dd') if deadline_enabled.isChecked() else '',
                       review_daily_goal=daily_goal.value(), review_computer_hours=computer_hours.value(),
                       review_windows_enabled=windows_enabled.isChecked(), review_windows=windows_value(),
                       review_interval_minutes=review_interval.value())
        try:
            plan = collection_plan(collection_api, preview)
            days = ('距截止日期含今天 %d 天；' % plan['days']) if plan['days'] is not None else ''
            plan_summary.setText(days + '今日新学：已学 %d / 目标 %d（剩余 %d）；复习：已复习 %d / 目标 %d（剩余 %d）；每组约 %d 张。'
                                 % (plan['new_done'], plan['new_goal'], plan['new_remaining'], plan['review_done'],
                                    plan['review_goal'], plan['review_remaining'], plan['batch']) +
                                 (' 今天 Anki 只会给到 %d 张，比目标少 %d 张；要一次学更多得提高牌组的每日新词上限（Anki 牌组选项）。'
                                  % (int(plan.get('available_new', 0)) + int(plan.get('available_due', 0)),
                                     plan['capacity_shortfall']) if plan['capacity_shortfall'] else '') +
                                 ' 当前范围剩余新卡 %d 张；仅统计所选笔记类型。按 Anki 学习日统计，复习日期与每日上限由 Anki 控制。' % plan['remaining_new_total'])
        except Exception:
            plan_summary.setText('暂时无法读取牌组计划，请检查牌组。')
    for control, signal in ((plan_mode, 'currentIndexChanged'), (deck, 'currentIndexChanged'),
                            (model, 'currentIndexChanged'),
                            (daily_goal, 'valueChanged'), (computer_hours, 'valueChanged'),
                            (review_interval, 'valueChanged'), (deadline, 'dateChanged'),
                            (deadline_enabled, 'toggled')):
        getattr(control, signal).connect(update_plan)
    for check in book_radios:
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
                           else '固定数量不设上限：写多少就一组学多少，学到词书没有了、或今天 Anki 的每日上限用尽才会停。'
                                '每组结束仍有 3 秒倒计时，随时可以收。')
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
        # The dial takes effect as it is moved so it can be heard at once; cancelling has to
        # put back whatever was saved, or closing the dialog would leave Anki playing louder.
        apply_review_volume(original.get('review_volume'))
        return
    cfg.update({"mode": mode.currentData(), "deck": deck.currentData(), "model": model.currentData(),
                "front_field": front.currentData(), "back_field": back.currentData(),
                "modifiers": shortcut.modifiers, "virtual_key": shortcut.virtual_key,
                "confirm_seconds": int(confirm_seconds.currentData()),
                "review_enabled": review_enabled.isChecked(),
                "hide_main_on_close": hide_main.isChecked(),
                "sync_background": sync_back.isChecked(),
                "sync_background_minutes": sync_minutes.value(),
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
                "review_show_example": review_show_example.isChecked(),
                "review_mastered_action": review_mastered_action.currentData(),
                "review_auto_example_mode": review_auto_example.currentData(),
                "review_volume": review_volume.value(),
                "review_smart": review_smart.isChecked(),
                "review_core_enabled": review_core.isChecked(),
                "study_book": book_value(),
                "review_position": review_position.currentData(),
                "review_theme": review_theme.currentData(),
                "review_modes": review_modes_value(),
                "review_known_style": known_style.currentData(),
                "review_beautify": review_beautify.isChecked(),
                "review_motion_hop": motion_hop.isChecked(),
                "review_motion_celebration": motion_celebration.isChecked(),
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
    refresh_toolbar()
    apply_sync_preference()
    if not controller.review.dialog:
        controller.review.start()
    if startup_error:
        show_feedback('其他设置已保存；开机启动设置失败：%s。' % startup_error, period=10000)
    elif not controller.listener.registered:
        show_feedback('设置已保存，但快捷键未注册：%s。' % (controller.listener.registration_error or '监听器未启动'), period=10000)
    else:
        show_feedback("设置已保存；全局快捷键 %s 已注册。" % format_shortcut(cfg['modifiers'], cfg['virtual_key']), period=5000)


def menu_action():
    """Two entries in Anki's Tools menu, not eleven.

    The plug-in had grown to eleven top-level items, and the three things used every day
    were buried under seven word-list maintenance actions nobody runs twice. The daily three
    go into one submenu, the maintenance seven one level further down, and the settings entry
    stays where people look for it. Nothing here is dropped — only moved.
    """
    action = mw.form.menuTools.addAction("全局划词入 Anki 设置…")
    action.triggered.connect(open_settings)
    review_menu = mw.form.menuTools.addMenu("单词随身复习")
    review_action = review_menu.addAction("立即弹出一张")
    review_action.triggered.connect(lambda: controller.review.show_next(True))
    study_book_menu(review_menu)
    listening = review_menu.addAction("六级听力：本地真题与模拟")
    listening.triggered.connect(open_cet6_listening)
    review_menu.addSeparator()
    report = review_menu.addAction("生成复习质量报告（只读）")
    report.triggered.connect(write_quality_report)
    manage = review_menu.addMenu("词书与词表管理")
    for label, handler in (("四六级核心词：补充缺失词汇", import_core_words),
                           ("四六级核心词：查看词表", browse_core_words),
                           ("六级词书：建立核心与完整词书", setup_cet6_books),
                           ("六级词书：浏览核心词汇", lambda: browse_cet6_book('cet6_core')),
                           ("六级词书：浏览完整词汇", lambda: browse_cet6_book('cet6_full')),
                           ("四级词书（KyleBing）：查看词汇", lambda: browse_cet6_book('cet4_kyle')),
                           ("六级词书（KyleBing）：查看词汇", lambda: browse_cet6_book('cet6_kyle'))):
        manage.addAction(label).triggered.connect(handler)
    return action, review_menu


def write_quality_report():
    """Measure this collection against its own promises, and write the answer out as a file.

    Read-only by construction: two SELECTs and one card search — no write, no reschedule, and
    nothing unsuspended. `desiredRetention = 0.9` is a claim about the learner's future memory
    and revlog is the only place that claim can be checked, which is the whole reason this
    menu entry exists. The 已掌握 table says the same about parked cards: there is no retention
    to report for a card that is never tested again, only how long it has been since it was.

    Runs on the GUI thread on purpose: `col.db` and `find_cards` are not thread-safe, and the
    queries here measured under a second against 6,885 notes.
    """
    if mw.col is None:
        show_feedback('Anki 还没打开账户，暂时读不到复习记录。')
        return
    cfg = settings()
    try:
        # The column is `ease`, not `rating` (measured against the live schema 2026-11-06 —
        # the query I first wrote raised OperationalError, which is exactly why this report
        # was run outside Anki before being trusted). Rows with ease 0 are not learner answers
        # at all (385 of them here: state changes and syncs), and counting them as successes
        # would inflate the retention the report is supposed to audit.
        retention = [(int(row[0]), int(row[1])) for row in mw.col.db.all(
            'select lastIvl, ease from revlog where lastIvl >= 1 and ease between 1 and 4')]
    except Exception as error:
        show_feedback('复习记录读不出来：%s' % type(error).__name__)
        return
    parked = []
    try:
        ids = [int(cid) for cid in mw.col.find_cards('is:suspended tag:"%s"' % MASTERED_TAG)]
        if ids:
            # `revlog.id` is milliseconds since the epoch (measured: 1793967780194 next to a
            # wall clock of 1793967939.235 s), and there is no `date` column in this schema.
            answers = {}
            for row in mw.col.db.all('select cid, max(id) from revlog where cid in (%s)'
                                     ' group by cid' % ','.join(str(cid) for cid in ids)):
                answers[int(row[0])] = int(row[1] or 0)
            now_ms = time.time() * 1000
            parked = [None if not answers.get(cid) else int((now_ms - answers[cid]) / 86400000)
                      for cid in ids]
    except Exception as error:
        log_runtime('parked card survey failed: %s' % type(error).__name__)
    summary = review_quality.summarize(retention, parked)
    # The ceilings and the promised retention come from AnkiConnect, and AnkiConnect is served
    # by this very GUI thread — asking it from here waits on yourself and times out (measured:
    # `deck limits unavailable: TimeoutError`, 2026-11-06, the first time this menu was used).
    # So the collection reads happen now, and the questions that need AnkiConnect go to a
    # thread, which is how every other maintenance action in this file already works.
    show_feedback('正在读牌组额度…')

    def work():
        limits_text, promised = '', 0.9
        try:
            limits = review_logic.deck_limits(api, dict(cfg))
            limits_text = review_logic.render_deck_limits(limits)
            promised = next((float(item['desired_retention']) for item in limits
                             if item.get('desired_retention')), 0.9)
        except Exception as error:
            log_runtime('deck limits unavailable: %s' % type(error).__name__)
        body = review_quality.render_markdown(
            review_quality.summarize(retention, parked, promised=promised), limits_text)
        folder = os.path.join(os.path.dirname(__file__), 'user_files', 'reports')
        path = os.path.join(folder, 'quality-%s.md' % time.strftime('%Y%m%d-%H%M%S'))
        try:
            os.makedirs(folder, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(body)
        except OSError as error:
            mw.taskman.run_on_main(lambda: show_feedback('报告没能写出：%s' % type(error).__name__))
            return
        log_runtime('quality report written: %s' % path)
        measured = '—' if summary['measured'] is None else '%.0f%%' % (100 * summary['measured'])
        mw.taskman.run_on_main(lambda: show_feedback(
            '复习质量报告已写出：%s\n到期作答 %d 次，实测保持率 %s（承诺 %.0f%%）；挂起 %d 张。'
            '评分对照请用 tools/analyze-grading-agreement.py。' % (
                path, summary['answers'], measured, 100 * promised, summary['parked_total']),
            period=15000))

    threading.Thread(target=work, daemon=True).start()


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
    cfg = settings()
    wanted = BOOK_MIGRATION.get(book, book)
    target = next((item for item in study_books(cfg) if item['id'] == wanted), None)
    if target is None:
        show_feedback('没有这本词书。')
        return
    query = 'note:"%s"%s' % (str(settings()['model']).replace('\\', '\\\\').replace('"', '\\"'), book_clause(target))
    def work():
        try:
            api('guiBrowse', {'query': query})
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
    # Links are rebuilt as HTML strings each time Anki runs this hook, so the current
    # scope can be named here; a saved change shows up on the next toolbar rebuild.
    book = study_book(settings())
    name = book['name'] if book else '未选词书'
    links.append(toolbar.create_link(
        'zvr-desktop-review', '开始学习 · %s' % name, open_review_from_toolbar,
        tip='立即弹出「%s」的学习卡；换词书在 工具 → 切换词书' % name, id='zvr-desktop-review'))


def refresh_toolbar():
    """Rebuild the toolbar after the book changes so its name is not stale until restart."""
    try:
        mw.toolbar.draw()
    except Exception as error:
        log_runtime('toolbar refresh failed: %s' % type(error).__name__)


def choose_study_book(book_id, start=True):
    cfg = settings()
    if mw.col is None or book_id not in {book['id'] for book in study_books(cfg)}:
        show_feedback('请先打开 Anki 账户。')
        return
    if controller.review.dialog or controller.review.busy:
        show_feedback('请先关闭当前复习卡，再切换词书。')
        return
    cfg = dict(settings())
    cfg['study_book'] = book_id
    try:
        save_settings(cfg)
    except Exception as error:
        show_feedback('切换词书失败：%s' % error)
        return
    refresh_toolbar()
    if start:
        controller.review.show_next(True)


def book_card_count(book):
    if mw.col is None:
        return 0
    query = 'note:"%s"%s -is:suspended -is:buried' % (
        str(settings()['model']).replace('\\', '\\\\').replace('"', '\\"'), book_clause(book))
    try:
        return len(mw.col.find_cards(query))
    except Exception:
        return 0


def study_book_menu(tools):
    """Switching books is a daily action, so it sits with the other tools rather than
    buried in settings. Counts are filled in on open: a book showing zero is exactly
    the thing that needs to be visible."""
    menu = tools.addMenu('切换词书')

    def refresh():
        cfg = settings()
        current = study_book_id(cfg)
        menu.clear()
        for book in study_books(cfg):
            action = menu.addAction('%s　%d 张' % (book['name'], book_card_count(book)))
            action.setCheckable(True)
            action.setChecked(book['id'] == current)
            action.triggered.connect(lambda _checked=False, key=book['id']: choose_study_book(key))
    menu.aboutToShow.connect(refresh)
    return menu


def add_study_dashboard(_browser, content):
    cfg = settings()
    if mw.col is None or (not cfg.get('review_deadline') and cfg.get('review_plan_mode') != 'daily'):
        return
    try:
        import datetime
        from aqt.theme import theme_manager
        today = datetime.date.today()
        plan = collection_plan(collection_api, cfg)
        try:
            plan['book_learned'], plan['book_total'] = book_progress(collection_api, cfg)
        except Exception as error:
            plan['book_learned'] = plan['book_total'] = 0
            log_runtime('book totals unavailable: %s' % type(error).__name__)
        selected = set()
        escape = lambda value: str(value).replace('\\', '\\\\').replace('"', '\\"')
        base = 'note:"%s"%s -is:suspended -is:buried' % (escape(cfg['model']), book_clause(study_book(cfg)))
        for deck_name in resolve_book_decks(collection_api, cfg):
            selected.update(mw.col.find_cards('deck:"%s" %s' % (escape(deck_name), base)))
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


def abort_media_sync():
    """Let a shutdown finish: Anki waits for a media sync to end before it exits.

    Three restarts today hung exactly there — the event loop kept answering while the
    window refused to go away, because the media syncer was still syncing against a proxy
    that no longer reaches AnkiWeb. Aborting the sync is what Anki's own abort button does,
    and it lets the normal shutdown (and its exit backup) complete.
    """
    try:
        syncer = mw.media_syncer
        if syncer is not None and syncer.is_syncing():
            syncer.abort()
            log_runtime("media sync aborted so Anki could finish closing")
    except Exception as error:
        log_runtime("media sync abort failed: %s" % type(error).__name__)


def watch_shutdown():
    """Mark how far Anki's own shutdown gets.

    Four restarts today had to be finished with a kill: the close event reached Anki, the
    log said `-> quit`, and the window still never went away — with the media syncer idle,
    so it was not that. Anki waits for a running backup inside `cleanupAndExit`, and every
    add-on gets `profile_will_close` first, so this records which side of that we reach.
    """
    try:
        gui_hooks.profile_will_close.append(
            lambda: log_runtime("anki is closing the profile (profile_will_close)"))
        log_runtime("shutdown watch installed")
    except Exception as error:
        log_runtime("shutdown watch unavailable: %s" % type(error).__name__)


class MainWindowCloseFilter(QObject):
    """Let the user close Anki's window while a card is up, without killing the card.

    Anki quits when its main window closes, which takes the study popup with it. With a
    card on screen the close button hides the window instead; with none it still quits
    normally, so Anki never turns into a process the user cannot close.

    Only the X button is ambiguous. The tray add-on's own 退出 and our card's 「退出 Anki」
    both say so before they call `mw.close()`, and either one outranks a card being on
    screen — an exit the user asked for is never turned into a hide.
    """

    def eventFilter(self, watched, event):
        try:
            if event.type() != QEvent.Type.Close:
                return False
            forced = bool(getattr(mw, "zvr_force_quit", False))
            # 'Minimize to Tray 2' raises its own flag inside onExit, one step before it
            # calls mw.close(). Reading it is the whole difference between "the X was
            # pressed" and "the user asked Anki to quit"; ignoring it made the tray icon
            # unable to exit at all while a card happened to be on screen (2026-11-06).
            exit_flag = bool(getattr(mw, "closeEventFromAction", False))
            forcing = forced or exit_flag
            tray = hasattr(mw, "closeEventFromAction")
            card_open = controller.review.card_on_screen()
            hiding = hide_instead_of_quit(
                card_open, bool(settings().get("hide_main_on_close", True)), forcing)
            if not hiding and background_instead_of_quit(tray, forcing):
                # The user runs a tray add-on: with no card on screen this close is "go to
                # background", not a shutdown. Hand it to that add-on and keep the popup and
                # sync timers running — stopping them here is what left Anki sitting in the
                # tray for an hour without ever showing a card (2026-11-04). With a card up,
                # the branch below still keeps that card visible instead of hiding it too.
                log_runtime("main window close: tray=on exit=no -> background (timers kept)")
                return False
            # Two restarts today needed a forced kill, and the log could not say why the
            # polite close was refused. Record the inputs to that decision.
            log_runtime("main window close: card=%s setting=%s force=%s exit=%s tray=%s -> %s" % (
                card_open, settings().get("hide_main_on_close", True),
                "yes" if forced else "no", "yes" if exit_flag else "no",
                "yes" if tray else "no", "hide" if hiding else "quit"))
            if not hiding:
                # A real close: stop both timers first. Otherwise the scheduled popup
                # can open a window in the middle of shutdown, or the background sync
                # can restart it, and Anki then never finishes quitting — this was seen
                # leaving a running Anki with no windows at all.
                mw.zvr_closing = True
                controller.review.stop()
                if controller.sync_timer is not None:
                    controller.sync_timer.stop()
                abort_media_sync()
            if hiding:
                event.ignore()
                mw.hide()
                show_feedback('已隐藏 Anki 主窗口，随身复习卡继续。要真正退出，点卡片右上角「…」里的「退出 Anki」。', period=8000)
                return True
        except Exception as error:
            log_runtime("main window close filter failed: %s" % type(error).__name__)
        return False


sync_state = {"last": None, "running": False, "guard": None, "error": None}


def aqt_sync_module():
    """Anki installs its modal sync-error box in aqt.sync, which is what we have to swap."""
    try:
        import aqt.sync
        return aqt.sync
    except Exception as error:
        log_runtime("sync module unavailable: %s" % type(error).__name__)
        return None


def sync_is_logged_in():
    """Anki answers a missing login with a modal sync dialog, so ask before triggering one."""
    try:
        return bool(mw.pm.sync_auth())
    except Exception as error:
        log_runtime("sync login check failed: %s" % type(error).__name__)
        return False


def end_background_sync():
    """Give Anki back its own error box and let another idle sync be tried."""
    sync_state["running"] = False
    restore, sync_state["guard"] = sync_state["guard"], None
    if restore is not None:
        restore()


def pause_background_sync(reason):
    """One failure is enough: stop asking and say so without a modal."""
    end_background_sync()
    if controller.sync_timer is not None:
        controller.sync_timer.stop()
    log_runtime("background sync paused: %s" % reason)
    show_feedback("后台同步已暂停：" + short_sync_reason(reason) +
                  "。保存一次设置可以重新开始，也可以直接点 Anki 的同步按钮。", period=9000)


def short_sync_reason(reason):
    reason = re.sub(r"^(RuntimeError|Exception|SyncError|NetworkError):\s*", "", str(reason or "")).strip()
    return (reason[:90] + "…") if len(reason) > 90 else (reason or "网络错误")


def start_sync_timer():
    """(Re)arm the idle sync timer, unless the feature is off."""
    if not settings().get("sync_background", True):
        return
    if controller.sync_timer is None:
        controller.sync_timer = QTimer()
        controller.sync_timer.timeout.connect(run_background_sync)
    sync_state["last"] = None
    controller.sync_timer.start(60000)


def quit_request_file():
    """The note a restart tool leaves when it needs Anki to really exit."""
    return quit_request_path(os.environ.get("TEMP") or os.path.expanduser("~"))


def poll_quit_request():
    """Answer a quit request with the tray add-on's own exit protocol.

    The user keeps Anki in 'Minimize to Tray 2', so every window close — WM_CLOSE,
    AnkiConnect's guiExitAnki, even our own exit — is only a hide unless
    `closeEventFromAction` is set first. That flag lives on mw, so this add-on is the only
    thing on the machine that can ask for a real quit; a tool that cannot reach it has to
    escalate to a kill and skip Anki's exit backup.
    """
    if not take_quit_request(quit_request_file()):
        return
    log_runtime("quit request seen: exiting Anki through the tray protocol")
    mw.zvr_force_quit = True
    if hasattr(mw, "closeEventFromAction"):
        mw.closeEventFromAction = True
    mw.close()


def start_quit_request_timer():
    """Listen for restart-tool quit requests. One os.path.exists every five seconds."""
    if controller.quit_timer is None:
        controller.quit_timer = QTimer()
        controller.quit_timer.timeout.connect(poll_quit_request)
    controller.quit_timer.start(5000)


def apply_sync_preference():
    """Move Anki's sync off the open/close path and onto the idle timer."""
    cfg = settings()
    remembered = apply_auto_sync_preference(mw.pm.profile, bool(cfg.get("sync_background", True)),
                                            cfg.get("anki_auto_sync_remembered"))
    if remembered != cfg.get("anki_auto_sync_remembered"):
        merged = dict(cfg)
        merged["anki_auto_sync_remembered"] = remembered
        try:
            save_settings(merged)
        except Exception as error:
            log_runtime("sync preference not recorded: %s" % type(error).__name__)
    if cfg.get("sync_background", True):
        start_sync_timer()
    elif controller.sync_timer is not None:
        controller.sync_timer.stop()


volume_control = audio_volume.VolumeControl()
# Which player Anki would answer a word with, and therefore which stage owns its loudness.
# Filled by `log_tts_routing` at profile open; until it is known the player keeps the gain.
speech_routing = {"via_file": False}


def apply_review_volume(value=None):
    """How loud Anki plays, for as long as this add-on is loaded.

    Anki has no volume control of its own and hands every clip to the bundled mpv, so the
    gain goes onto that process — both the one already running and the argument list it
    will spawn from next. Nothing is written to disk: at 100% Anki's command line is
    byte-for-byte what it is, and closing Anki forgets all of it.

    When the word is being rendered by `speech` instead (this machine: SAPI speaks straight
    to the sound card), the render stage owns the loudness and the player must stay neutral.
    Both stages at full height is what stacked into the distorted, shouty sound the user
    rejected — one lever per signal.
    """
    if value is None:
        value = settings().get("review_volume", audio_volume.NEUTRAL)
    value = audio_volume.clamp(value)
    player_value = audio_volume.NEUTRAL if speech_routing["via_file"] else value
    try:
        from aqt.sound import av_player
    except Exception as error:
        log_runtime("review volume %d%% unavailable: %s" % (value, type(error).__name__))
        return {"spec": None, "touched": [], "errors": [str(error)]}
    applied = volume_control.set(av_player.players, player_value)
    log_runtime("review volume %d%% (player %d%%, via-file=%s): spec=%s touched=%s errors=%s live-af=%s" % (
        value, player_value, speech_routing["via_file"], applied["spec"] or "-",
        ",".join(applied["touched"]) or "-", "; ".join(applied["errors"]) or "-",
        "no" if applied["af_failed"] else "yes"))
    return applied


def volume_preview(value):
    """Set the dialled gain and say one word at it, so the setting can be heard.

    This goes through the same routing as the card: previewing the plain SAPI path would
    prove nothing about the gain the dial just asked for.
    """
    applied = apply_review_volume(value)
    try:
        from aqt.sound import av_player
        speech.speak(av_player, mw.taskman, ['example'], value, tts_tag,
                     on_error=lambda error: show_feedback('试听失败：%s' % error, period=8000))
    except Exception as error:
        log_runtime("volume preview unavailable: %s" % type(error).__name__)
    return applied


def tts_tag(text):
    from anki.sound import TTSTag
    return TTSTag(field_text=str(text)[:500], lang='en_US', voices=[], speed=1.0, other_args=[])


def log_tts_routing():
    """Record which player Anki would pick for a word, without playing anything.

    The gain lives on mpv; if Anki answers a TTSTag with SAPI instead, the dial cannot be
    heard at all, and that distinction is invisible from the outside. Asking
    `rank_for_tag` for the tag we actually build answers it in one log line — and on this
    machine it answered `chosen=WindowsTTSPlayer`, which is why the card now renders the
    word into a wav and lets the file player speak it (see `speech.speak`).
    """
    try:
        from aqt.sound import av_player
        tag = tts_tag('example')
        chosen = av_player._best_player_for_tag(tag)
        direct = speech.speaks_directly(chosen)
        speech_routing["via_file"] = direct
        log_runtime("tts routing: %s | chosen=%s | speaks-directly=%s" % (
            audio_volume.describe_players(av_player.players, tag),
            type(chosen).__name__ if chosen is not None else "None", direct))
    except Exception as error:
        log_runtime("tts routing unavailable: %s: %s" % (type(error).__name__, error))


def study_is_idle():
    review = controller.review
    if mw.col is None or review.card_on_screen():
        return False
    if review.busy or mw.state == "review":
        return False
    try:
        return not mw.media_syncer.is_syncing()
    except Exception:
        return not sync_state["running"]


def run_background_sync():
    """Sync in a quiet moment, so opening and closing Anki costs nothing."""
    if getattr(mw, "zvr_closing", False):
        return
    cfg = settings()
    if not cfg.get("sync_background", True) or sync_state["running"]:
        return
    now = datetime.datetime.now()
    if not sync_due(now, sync_state["last"], cfg.get("sync_background_minutes", 5), study_is_idle()):
        return
    if not sync_is_logged_in():
        log_runtime("background sync waiting for a sync login")
        return
    sync_state["last"] = now
    sync_state["running"] = True
    sync_state["error"] = None
    sync_state["guard"] = install_sync_error_guard(aqt_sync_module(), sync_state, pause_background_sync)
    log_runtime("background sync started")
    try:
        # Anki's own sync path, on the main thread: it runs the work in a background task,
        # refreshes afterwards, and still asks the user if a full sync is really needed.
        # The only thing changed is where a failure goes — see install_sync_error_guard.
        mw.on_sync_button_clicked()
    except Exception as error:
        log_runtime("background sync failed: %s" % type(error).__name__)
        pause_background_sync(short_sync_reason("%s: %s" % (type(error).__name__, error)))
        return
    # Anki reports no completion we can hook, so hand its error box back shortly after a
    # sync would normally be over; a finished or failed sync already gave it back earlier.
    QTimer.singleShot(120000, end_background_sync)


def on_main_window_ready():
    mw.toolbar.redraw()
    ensure_anki_connect()
    controller.main_close_filter = MainWindowCloseFilter(mw)
    mw.installEventFilter(controller.main_close_filter)
    watch_shutdown()
    apply_sync_preference()
    start_sync_timer()
    start_quit_request_timer()
    # A new main window means a new player process, so whatever the last one was told no
    # longer exists; forgetting it keeps the first change a plain add rather than a removal
    # against a socket that never had the filter.
    volume_control.reset()
    log_tts_routing()
    apply_review_volume()
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
    gui_hooks.profile_did_open.append(apply_sync_preference)
    gui_hooks.profile_will_close.append(controller.stop)
    gui_hooks.main_window_did_init.append(on_main_window_ready)
    QTimer.singleShot(1500, lambda: controller.review.start() if mw.col else None)
except Exception:
    log_path = os.path.join(tempfile.gettempdir(), "zotero_global_capture_startup_error.txt")
    with open(log_path, "w", encoding="utf-8") as error_log:
        traceback.print_exc(file=error_log)
    raise
