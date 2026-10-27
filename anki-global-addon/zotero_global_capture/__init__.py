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
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTimer, QVBoxLayout,
    QWidget, QObject, pyqtSignal, Qt, QCursor, QSpinBox,
)

from .background import configure_login_start
from .review_popup import DesktopReviewController


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
    "review_position": "corner",
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
    value.update(mw.addonManager.getConfig(ADDON) or {})
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
        "QLabel { background: #202124; color: white; border: 1px solid #555; "
        "border-radius: 8px; padding: 12px 16px; font-size: 14px; }"
    )
    notice.setWindowFlags(
        Qt.WindowType.ToolTip | Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.WindowDoesNotAcceptFocus
    )
    notice.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    notice.adjustSize()
    screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
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

    def __init__(self, bridge, config):
        super().__init__(daemon=True)
        self.bridge = bridge
        self.config = dict(config)
        self.thread_id = 0
        self.stop_event = threading.Event()
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
            log_runtime("hotkey registration failed")
            self.bridge.status.emit("全局快捷键注册失败；请在设置中更换按键。")
        else:
            log_runtime("hotkey registered: %s" % format_shortcut(cfg["modifiers"], cfg["virtual_key"]))
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
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
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

    def __init__(self, modifiers, virtual_key, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("点击此处，然后按快捷键组合")
        self.modifiers = int(modifiers)
        self.virtual_key = int(virtual_key)
        self._show_shortcut()

    def _show_shortcut(self):
        self.setText(format_shortcut(self.modifiers, self.virtual_key))

    def keyPressEvent(self, event):
        key = int(event.key())
        qt_modifiers = int(event.modifiers())
        modifiers = 0
        if qt_modifiers & 0x04000000:
            modifiers |= MOD_CONTROL
        if qt_modifiers & 0x08000000:
            modifiers |= MOD_ALT
        if qt_modifiers & 0x02000000:
            modifiers |= MOD_SHIFT
        if qt_modifiers & 0x10000000:
            modifiers |= MOD_WIN

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
            self.setText("暂不支持此按键，请用字母、数字、F1–F24 或导航键")
            return
        if not modifiers:
            self.setText("请至少搭配 Ctrl、Alt、Shift 或 Win")
            return
        self.modifiers = modifiers
        self.virtual_key = virtual_key
        self._show_shortcut()


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


def open_settings():
    cfg = settings()
    dialog = QDialog(mw)
    dialog.setWindowTitle("全局划词入 Anki")
    form = QFormLayout(dialog)
    mode = QComboBox()
    mode.addItem("选中后按快捷键添加", "direct")
    mode.addItem("选中后自动添加（鼠标拖选）", "auto")
    mode.addItem("快捷键预览释义，再按一次添加", "preview")
    mode.setCurrentIndex(max(0, mode.findData(cfg["mode"])))
    deck = QLineEdit(str(cfg["deck"]))
    model = QLineEdit(str(cfg["model"]))
    front = QLineEdit(str(cfg["front_field"]))
    back = QLineEdit(str(cfg["back_field"]))
    confirm_seconds = QComboBox()
    for seconds in (5, 8, 10, 15):
        confirm_seconds.addItem("%d 秒" % seconds, seconds)
    confirm_seconds.setCurrentIndex(max(0, confirm_seconds.findData(int(cfg["confirm_seconds"]))))
    shortcut = ShortcutEdit(cfg["modifiers"], cfg["virtual_key"])
    review_enabled = QCheckBox("定时弹出单词复习")
    review_enabled.setChecked(bool(cfg["review_enabled"]))
    review_interval = QSpinBox()
    review_interval.setRange(5, 240)
    review_interval.setSuffix(" 分钟")
    review_interval.setValue(int(cfg["review_interval_minutes"]))
    review_position = QComboBox()
    review_position.addItem("屏幕右下角", "corner")
    review_position.addItem("屏幕中央", "center")
    review_position.setCurrentIndex(max(0, review_position.findData(cfg["review_position"])))
    review_mode = QComboBox()
    review_mode.addItem("选择题与英文填空混合", "mixed")
    review_mode.addItem("选择题", "choice")
    review_mode.addItem("英文填空", "typing")
    review_mode.setCurrentIndex(max(0, review_mode.findData(cfg["review_mode"])))
    review_beautify = QCheckBox("美化本牌组的 Anki 单词卡")
    review_beautify.setChecked(bool(cfg["review_beautify"]))
    review_start_at_login = QCheckBox("Windows 登录时启动 Anki 后台复习")
    review_start_at_login.setChecked(bool(cfg["review_start_at_login"]))
    form.addRow("收词方式", mode)
    form.addRow("Anki 牌组", deck)
    form.addRow("笔记类型", model)
    form.addRow("单词字段", front)
    form.addRow("释义字段", back)
    form.addRow("预览确认有效期", confirm_seconds)
    form.addRow("全局快捷键", shortcut)
    form.addRow("随身复习", review_enabled)
    form.addRow("弹出间隔", review_interval)
    form.addRow("弹出位置", review_position)
    form.addRow("练习形式", review_mode)
    form.addRow("卡片外观", review_beautify)
    form.addRow("后台运行", review_start_at_login)
    form.addRow(QLabel("点击输入框后按组合键。至少需要一个修饰键；支持字母、数字、F1–F24 和常用导航键。"))
    form.addRow(QLabel("自动模式在鼠标拖选后尝试复制选区；会暂存并恢复剪贴板。受保护窗口可能不支持。"))
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    try:
        configure_login_start(review_start_at_login.isChecked())
    except Exception as error:
        show_feedback("开机启动设置失败：%s" % error, period=7000)
        review_start_at_login.setChecked(False)
    cfg.update({"mode": mode.currentData(), "deck": deck.text().strip(), "model": model.text().strip(),
                "front_field": front.text().strip(), "back_field": back.text().strip(),
                "modifiers": shortcut.modifiers, "virtual_key": shortcut.virtual_key,
                "confirm_seconds": int(confirm_seconds.currentData()),
                "review_enabled": review_enabled.isChecked(),
                "review_interval_minutes": review_interval.value(),
                "review_position": review_position.currentData(),
                "review_mode": review_mode.currentData(),
                "review_beautify": review_beautify.isChecked(),
                "review_start_at_login": review_start_at_login.isChecked()})
    save_settings(cfg)
    controller.stop()
    controller.listener = NativeListener(controller.bridge, cfg)
    controller.listener.start()
    controller.review.start()
    show_feedback("全局划词设置已保存。", period=5000)


def menu_action():
    action = mw.form.menuTools.addAction("全局划词入 Anki 设置…")
    action.triggered.connect(open_settings)
    review_action = mw.form.menuTools.addAction("单词随身复习：立即弹出一张")
    review_action.triggered.connect(lambda: controller.review.show_next(True))
    return action, review_action


def on_main_window_ready():
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
    log_runtime("desktop review controller initialized")
    menu_action_ref = menu_action()
    gui_hooks.card_will_show.append(controller.review.style_card)
    gui_hooks.profile_did_open.append(controller.review.start)
    gui_hooks.profile_will_close.append(controller.stop)
    gui_hooks.main_window_did_init.append(on_main_window_ready)
    QTimer.singleShot(1500, lambda: controller.review.start() if mw.col else None)
except Exception:
    log_path = os.path.join(tempfile.gettempdir(), "zotero_global_capture_startup_error.txt")
    with open(log_path, "w", encoding="utf-8") as error_log:
        traceback.print_exc(file=error_log)
    raise
