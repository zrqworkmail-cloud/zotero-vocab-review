"""A small, non-modal vocabulary review window for the configured Anki deck."""

import html
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import threading
import time

from aqt import mw
from aqt.qt import (
    QApplication, QColor, QCursor, QDesktopServices, QDialog, QEvent, QFontMetrics, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QObject,
    QPainter, QPushButton, QScrollArea, QStyle, QTimer, QUrl, QVBoxLayout, QWidget, pyqtSignal, Qt,
)

try:  # aqt.qt does not re-export every name on every Anki build (same pattern as card_icons)
    from aqt.qt import QSizePolicy
except ImportError:
    from PyQt6.QtWidgets import QSizePolicy

try:
    from aqt.qt import QPen
except ImportError:
    from PyQt6.QtGui import QPen

try:
    from aqt.qt import QPoint, QRect
except ImportError:
    from PyQt6.QtCore import QPoint, QRect

from .review_logic import (answer_report, answer_matches, BOOK_LABEL_SOURCES, clean_detail, clean_text, cloze_sentence, collection_plan, EASE_NAMES, end_of_session_reason, example_groups, exam_word_labels, format_meaning, grading_log_line, link_example_html, literature_example_html, masked_example, mask_answer_clues, meaning_table, next_check_delay, plan_limits_new, root_detail_html,
                           next_hint_index, prepare_question, hint_share, book_availability, book_label, book_progress, book_suspended, due_outside_book, selected_mode_labels, selection_entries, selection_summary, study_state_label, show_examples, STUDY_STATE_NOTES, meaning_markers, session_batch_size, should_style_card, spelling_hint, letter_hint_label, phonetic_available, pulse_bright, spoken_examples, submit_review, suggested_ease, today_remaining, updated_session_target, window_wait)
from . import morphology, word_relations, speech, motion_view
from . import card_motion
from .card_motion import tier_for
from .card_icons import pin_icon, speaker_icon
from . import input_mode
from .input_mode import ReviewInputMode


# The 【解释】 body sits this far in from its heading, so the part-of-speech lines
# read as the content of the heading rather than as a sibling block.
MEANING_INDENT = 20

# The speaker disc is drawn to the height of the letters beside it: the word is 27px in
# the stylesheet and a card heading 12px. One size for both made the word's disc look like
# a dot and the heading's like a plate.
WORD_SPEAKER = 28
# Question types whose prompt already shows the English word. Hearing it adds an ear, not
# an answer, so these get Enter + a speaker on the front face and no hint accounting.
# 中文选英文 is excluded on purpose: there the word is what the learner must produce.
FRONT_AUDIO_MODES = ('choice', 'judgment')
HEADING_SPEAKER = 20

# The letter boxes show no text caret at all (learner 2026-11-06: 「光标会和字母混在一起
# 看不清字母是什么样子」 -- and by construction they must collide, because
# `next_hint_index` gives the hint to the box that already has focus, and the caret of an
# empty centred box sits exactly where the centred hint letter is drawn). Where you are
# typing is now shown by the box's own frame breathing, on Qt's caret period.
LETTER_PULSE_MS = 530
FOCUS_RING = {'dark': ('#8fa2ff', '#4d5c96'), 'light': ('#5668ca', '#c3ccef')}

# The word-list pills at the foot of the card. These are the stylesheet's own numbers:
# the card is measured against them before anything is shown, so a pill cannot be sized
# from one set of padding and painted from another.
CHIP_FONT_PX = 12
CHIP_PADDING_X = 7
CHIP_PADDING_Y = 2
CHIP_GAP = 6

POPUP_STYLE = """
QDialog { background: #f4f6fb; color: #1e293b; font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; }
QLabel { color: #334155; font-size: 13px; }
QLabel#eyebrow { color: #5968b3; font-size: 12px; font-weight: 700; letter-spacing: 1px; }
QLabel#question { color: #172554; font-size: 27px; font-weight: 700; padding: 8px 0; }
QLabel#meaning { color: #233149; font-size: 15px; font-weight: normal; line-height: 1.5; }
QLabel#sentence { background: #e9effa; color: #374866; border-radius: 10px; padding: 12px; font-size: 15px; }
QLabel#hint { color: #5869b5; font-size: 21px; letter-spacing: 4px; font-weight: 600; }
QLabel#answer { color: #27344d; background: #ffffff; border: 1px solid #e0e7f2;
                border-radius: 12px; padding: 12px; font-size: 14px; }
QLabel#result { font-size: 18px; font-weight: 700; padding: 6px; }
QLabel#status { color: #66758d; font-size: 12px; }
/* The one line that decides whether the session continues has to be readable at a glance,
   not 12px grey like ordinary status text (user 2026-11-04: 把字弄的大一点醒目一点). */
QLabel#breakHint { color: #172554; font-size: 20px; font-weight: 700; }
QLabel#cardHeading { color: #64749a; font-size: 12px; font-weight: 700; background: transparent; }
QLabel#meaningHeading { color: #64749a; font-size: 15px; font-weight: 700; background: transparent; }
QLabel#cardText { color: #27344d; font-size: 14px; font-weight: normal; background: transparent; }
QPushButton { background: #ffffff; color: #27344d; border: 1px solid #dce4f1;
              border-radius: 10px; padding: 9px 12px; text-align: center; font-size: 13px; }
/* A push button cannot word-wrap, which is why an option used to be cut at 45
   characters. The row keeps the letter in its own column so a wrapped meaning
   hangs aligned under the text, not under the letter. */
QWidget#choice { background: #ffffff; border: 1px solid #dce4f1; border-radius: 10px; }
QWidget#choice:hover { background: #eef2ff; border-color: #8996e8; }
QLabel#choiceLetter { color: #5668ca; font-size: 14px; font-weight: 700; background: transparent; }
QLabel#choiceText { color: #27344d; font-size: 14px; background: transparent; }
QPushButton:hover { background: #eef2ff; border-color: #8996e8; }
QPushButton:disabled { color: #8c98aa; background: #f0f2f6; }
/* The hint row's aids: the card's own button, one size shorter. Flattening them to grey
   text (variant D on 2026-11-05) was the learner's pick from the mockup, and a week of
   real use later he could not tell they were clickable at all -- so they keep the button
   chrome and differ from 检查拼写 by being unfilled instead of by being invisible. */
QPushButton#aid { padding: 5px 11px; font-size: 12px; }
QPushButton#primary { background: #5668ca; color: white; border: none; text-align: center; font-weight: 600; }
QPushButton#primary:hover { background: #4557b5; }
/* The suggestion is an outline, so it reads as "Enter would use this" rather than
   "this is already decided". Only the button the user actually picks fills in. */
QPushButton#suggest { background: #eef2ff; color: #27344d; border: 1px solid #8996e8; text-align: center; }
QPushButton#suggest:hover, QPushButton#suggest:focus { background: #e3eafd; border-color: #5668ca; }
QPushButton#chosen { background: #5668ca; color: white; border: 1px solid #4557b5; text-align: center; font-weight: 600; }
QPushButton#chosen:disabled { background: #5668ca; color: white; }
QPushButton#secondary { background: transparent; border: none; color: #728096; text-align: center; }
QLineEdit { background: white; color: #172554; border: 1px solid #dce4f1; border-radius: 10px;
            padding: 10px 12px; font-size: 16px; }
QLineEdit:focus { border: 1px solid #7080dd; }
QScrollArea { border: none; background: transparent; }
QWidget#answerContent { background: #f4f6fb; }
QWidget#letterRow { background: #f4f6fb; }
QWidget#questionBlock { background: #f4f6fb; }
QWidget#breakCard { background: #f4f6fb; }
QWidget#detailCard { background: white; border: 1px solid #e0e7f2; border-radius: 12px; }
QPushButton#speaker { background: transparent; border: none; padding: 0; }
QPushButton#speaker:hover, QPushButton#speaker:focus { background: transparent; border: none; }
QPushButton#cardMenu { background: transparent; border: none; color: #64749a; font-size: 22px; padding: 0; }
QPushButton#pin { background: transparent; border: 1px solid #dce4f1; padding: 2px; }
QPushButton#pin:hover, QPushButton#pin:checked { background: #eef2ff; border-color: #8996e8; }
QLabel#bookChip { color: #5668ca; background: #eef2ff; border-radius: 8px; padding: 2px 7px;
                  margin: 0; font-size: 12px; font-weight: 600; }
QWidget#bookChipRow { background: transparent; }
QMenu { background: #ffffff; color: #27344d; border: 1px solid #dce4f1; }
QMenu::item:selected { background: #eef2ff; color: #27344d; }
"""


# Keep every foreground/background pair explicit, including disabled controls.
_DARK_COLORS = {
    '#f4f6fb': '#171c2b', '#1e293b': '#edf1fa', '#334155': '#d9e1f0',
    '#5968b3': '#aab9ff', '#172554': '#eef1ff', '#233149': '#e1e8f5',
    '#e9effa': '#28344a', '#374866': '#dbe5f7', '#5869b5': '#bac5ff',
    '#27344d': '#e2e9f6', '#ffffff': '#252e40', '#e0e7f2': '#47556c',
    '#66758d': '#b2bfd2', '#64749a': '#b9c8e7', '#dce4f1': '#4a5971',
    '#eef2ff': '#34415d', '#8996e8': '#aab8ff', '#8c98aa': '#aab4c5',
    '#e3eafd': '#3d4a6b',
    '#f0f2f6': '#343d4c', '#5668ca': '#596dd1', '#4557b5': '#6e80df',
    '#728096': '#b5c0d1', '#7080dd': '#aab8ff', 'background: white': 'background: #252e40',
}

def popup_style(cfg):
    style = POPUP_STYLE
    if cfg.get('review_theme', 'light') == 'dark':
        for old, new in _DARK_COLORS.items():
            style = style.replace(old, new)
    return style


# The speaker disc and glyph per theme: the platform volume icon is dark, so the light
# theme needs a dark glyph on a pale disc, and the dark theme the other way round.
SPEAKER_COLORS = {'light': ('#27344d', '#eef2ff', '#8996e8'),
                  'dark': ('#1b2333', '#cdd9ff', '#8fa0e8')}
PIN_COLORS = {'light': '#5668ca', 'dark': '#aab9ff'}


CARD_STYLE = """
<style id="zvr-vocabulary-theme">
body.card { max-width: 780px !important; margin: 32px auto !important; padding: 0 20px 32px !important;
  background: #f3f6fb !important; color: #1e293b !important; font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif !important; }
.card .section { background: #fff !important; color: #334155 !important; border-radius: 18px !important;
  border: 1px solid #e3e9f3 !important; box-shadow: 0 12px 32px rgba(43,58,92,.08) !important;
  padding: 10px 18px !important; margin: 16px 0 !important; line-height: 1.65 !important; }
.card .items { padding: 12px 0 !important; overflow-wrap: anywhere; }
.card #front { color: #253576 !important; font-size: 2.35em !important; font-weight: 750 !important; letter-spacing: -.025em; line-height: 1.2 !important; text-align: center !important; }
.card #back { color: #243450 !important; font-size: 1.15em !important; line-height: 1.7 !important; }
.card #front-extra1 { color: #7184ad !important; font-size: 1em !important; }
.card hr { border: 0 !important; border-top: 1px solid #e8edf5 !important; }
.card a { color: #5668ca !important; }
.card img { max-width: 100%; height: auto; }
html.nightMode body.card, body.card.nightMode { background: #171c2b !important; color: #e8eef9 !important; }
html.nightMode .card .section, .card.nightMode .section { background: #252e40 !important; color: #e1e8f5 !important; border-color: #46556d !important; }
html.nightMode .card #front, .card.nightMode #front { color: #eef1ff !important; }
html.nightMode .card #back, .card.nightMode #back { color: #e1e8f5 !important; }
html.nightMode .card #front-extra1, .card.nightMode #front-extra1 { color: #b9c8e7 !important; }
html.nightMode .card hr, .card.nightMode hr { border-top-color: #46556d !important; }
html.nightMode .card a, .card.nightMode a { color: #aab8ff !important; }
</style>
"""


def _plain_label(text, name=None):
    label = QLabel(str(text))
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    return label


def syllable_display(word):
    """Real syllable breaks belong on the word itself; a mechanical letter grouping
    stays down in the detail list, because dressing the word up with something that
    is not syllables would be worse than not showing it at all."""
    try:
        chunks = morphology.spelling_chunks(word)
    except Exception:
        return word
    if chunks and chunks[0] == '音节分段':
        return '·'.join(chunks[1])
    return word


def _meaning_label(text, name):
    label = _plain_label('', name)
    font = label.font()
    font.setPixelSize(15 if name == 'meaning' else 14)
    metrics = QFontMetrics(font)
    parts = meaning_markers(text)
    width = max((metrics.horizontalAdvance(part) for part in parts), default=0) + 8
    label.setTextFormat(Qt.TextFormat.RichText)
    # Indented so the adj./n. lines read as the body of the 【解释】 heading above them.
    label.setText(meaning_table(text, width, MEANING_INDENT))
    return label


def size_rating_button(button):
    """Let each rating button keep its own width, and widen the card to fit the row.

    `Ignored` was the first attempt: the row would share whatever width the card had, so the
    window could never jump mid-answer. But Ignored also hides a button's size hint from the
    layout's arithmetic — and a push button's hint carries the style's own minimum button
    width — so the card's computed minimum came out ~45 px narrower than the row really is,
    and the last button fell off the right edge on every real card. `Minimum` keeps the hint
    in the arithmetic; the row is centred, so the gap left of A equals the gap right of E.
    """
    policy = button.sizePolicy()
    policy.setHorizontalPolicy(type(policy.horizontalPolicy()).Minimum)
    button.setSizePolicy(policy)
    return button


class ClickAwayFilter(QObject):
    def __init__(self, popup):
        super().__init__(popup)
        self.popup = popup

    def eventFilter(self, watched, event):
        # An embedded card lives inside the host window, so the host and its leftover
        # widgets are not "outside the card"; treating them as outside rejected the
        # active card on any click that landed on the host. The host keeps its own
        # filter, so a real click outside the window still ends the session.
        if getattr(self.popup, '_embedded', False):
            return False
        if (self.popup.isVisible() and event.type() == QEvent.Type.MouseButtonPress and
                isinstance(watched, QWidget) and watched is not self.popup and
                not self.popup.isAncestorOf(watched)):
            self.popup.reject()
        return False


def enable_click_away(popup):
    app = QApplication.instance()
    if app:
        popup._click_away_filter = ClickAwayFilter(popup)
        app.installEventFilter(popup._click_away_filter)
        popup.finished.connect(lambda _result: app.removeEventFilter(popup._click_away_filter))


class LetterBox(QLineEdit):
    def __init__(self, parent, index):
        super().__init__()
        self.owner, self.index = parent, index
        self.setMaxLength(1)
        self.setInputMethodHints(Qt.InputMethodHint.ImhLatinOnly | Qt.InputMethodHint.ImhNoPredictiveText)
        # Measured on this machine (tools/probe-ime-api.py): `ImhLatinOnly` alone leaves the
        # IME context attached and 微软拼音 keeps composing, which is why the learner still
        # saw candidates here. The flag below is the one the manual run showed working.
        input_mode.make_latin_only(self)
        self.setFixedSize(38, 40)
        self.changed('')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.textChanged.connect(self.changed)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.owner.input_mode.enable(int(self.owner.winId()))
        self.owner.start_box_pulse()

    def changed(self, value):
        expected = self.owner.letter_positions[self.index][1]
        if value and value.casefold() != expected.casefold() and not self.owner.answer_shown:
            self.owner.incorrect_letters += 1
        dark = self.owner.cfg.get('review_theme') == 'dark'
        color = ('#71e0b5' if dark else '#198765') if value.casefold() == expected.casefold() else ('#ff99a9' if dark else '#d34d61')
        base = ('background: #252e40; color: #edf1fa; border: 1px solid #4a5971;' if dark else 'background: white; border: 1px solid #dce4f1;') + ' border-radius: 8px; padding: 2px; font-size: 18px;'
        self.setStyleSheet(base + (' color: %s; font-weight: 700;' % color if value else ''))
        if value and self.owner.letter_motion_allowed():
            # Land it or shake it: the difference the learner is trying to learn from is
            # right there in the box they just typed into.
            if value.casefold() == expected.casefold():
                motion_view.hop(self)
            else:
                motion_view.shake(self)
        if value and self.index + 1 < len(self.owner.letter_boxes):
            self.owner.letter_boxes[self.index + 1].setFocus()

    def paintEvent(self, event):
        super().paintEvent(event)
        ring, bright = self.owner.focus_ring(self)
        hint = self.hasFocus() and not self.text() and self.placeholderText()
        # Qt still paints a text caret here, and this build gives no way to switch it off:
        # `caret-color: transparent` parses but does nothing for a QLineEdit (measured -- the
        # caret column is unchanged with and without it), and PyQt6 6.11 exposes no
        # setCursorWidth. So the column is painted back with the box's own background -- the
        # only place it can be, because an empty centred box puts the caret exactly where the
        # centred hint letter is drawn (learner 2026-11-06: 光标和字母混在一起看不清).
        if self.hasFocus() and not self.text():
            dark = self.owner.cfg.get('review_theme') == 'dark'
            # The caret column is taken from the box's own geometry rather than
            # `cursorRect()`: an empty centred box puts the caret at the centre (measured
            # cursorRect (13,8,10,25) in a 38 px box, bar at x=18, centre 19), and a fixed
            # 5 px column covers it without asking the line control to re-lay itself out
            # mid-paint.
            centre = self.rect().center().x()
            top = self.rect().top() + 8
            height = self.height() - 16
            painter = QPainter(self)
            painter.fillRect(centre - 2, top, 5, height,
                             QColor('#252e40' if dark else '#ffffff'))
            painter.end()
        if not ring and not hint:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if ring:
            accent, faded = FOCUS_RING['dark' if self.owner.cfg.get('review_theme') == 'dark'
                                        else 'light']
            pen = QPen(QColor(accent if bright else faded))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 8, 8)
        if hint:
            painter.setFont(self.font())
            painter.setPen(QColor('#7b86a5'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.placeholderText())
        painter.end()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.owner.add_hint()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            # One gesture, one level up: Space gives a letter, Shift+Space gives the
            # transcription. Measured free on both faces (tools/probe-free-keys.py), and it
            # stays inside the letter box so the learner never has to reach for the mouse.
            self.owner.request_phonetic_hint()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self.owner.input_complete_and_correct():
                texts = [self.owner.question.get('answer_form', self.owner.question['word'])]
                (self.owner.speak_many if self.owner.question['mode'] == 'listening' else self.owner.hear_hint)(texts)
            else:
                self.owner.check_input()
            event.accept()
            return
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            text = ''.join(char for char in QApplication.clipboard().text() if char.isalpha())
            for box, char in zip(self.owner.letter_boxes[self.index:], text):
                box.setText(char)
            return
        if event.key() == Qt.Key.Key_Backspace and not self.text() and self.index:
            previous = self.owner.letter_boxes[self.index - 1]
            previous.clear()
            previous.setFocus()
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            offset = -1 if event.key() == Qt.Key.Key_Left else 1
            index = self.index + offset
            if 0 <= index < len(self.owner.letter_boxes):
                self.owner.letter_boxes[index].setFocus()
            return
        if event.text().isalpha() and self.text():
            self.selectAll()
        super().keyPressEvent(event)


class _ChoiceRow(QWidget):
    """One answer: a letter column plus a meaning column that wraps on its own.

    QPushButton cannot word-wrap, so options used to be truncated at 45 characters
    and the letter sat inside the text. Here the letter keeps a fixed column and the
    wrapped lines line up under the text instead of under the letter.
    """
    clicked = pyqtSignal()

    def __init__(self, letter, text, parent=None):
        super().__init__(parent)
        self.setObjectName('choice')
        # Without this Qt paints the widget with the plain palette and ignores the
        # stylesheet's background and border, so the option looked like loose text
        # instead of a boxed choice.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(10)
        # Fixed vertically: the default `Preferred` policy lets Qt hand the window's leftover
        # height to the option boxes, which turned a two-option 判断题 into two 190 px blocks
        # (the user's screenshot on 2026-11-04). An option is now exactly as tall as its own
        # text, wrapped lines included, because sizeHint already accounts for them.
        policy = self.sizePolicy()
        policy.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        self.setSizePolicy(policy)
        # The boxes are stretched to share the answer area, so the letter and its meaning
        # have to sit in the middle of the box instead of clinging to its top edge.
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.letter_label = QLabel(letter)
        self.letter_label.setObjectName('choiceLetter')
        self.letter_label.setFixedWidth(18)
        self.letter_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.text_label = QLabel(text)
        self.text_label.setObjectName('choiceText')
        self.text_label.setWordWrap(True)
        # Top-aligned like the letter column: a vertically centred label would drop the
        # first line below the letter whenever the row is stretched.
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.text_label.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.letter_label)
        row.addWidget(self.text_label, 1)

    def click(self):
        self.clicked.emit()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.click()
            event.accept()
            return
        super().mouseReleaseEvent(event)


def stop_speech():
    """Cut whatever Anki is still reading out.

    Speech runs on Anki's own audio thread, so without this the next card would keep
    hearing the previous word, and a dismissed card would keep talking in the dark.
    """
    try:
        from aqt.sound import av_player
        stop = getattr(av_player, 'stop_and_clear_queue', None)
        if stop:
            stop()
    except Exception:
        pass


def set_topmost_band(window, pinned):
    """Move the window between the topmost and normal bands, and report whether it worked.

    Clearing `WindowStaysOnTopHint` takes the style bit off, but Windows keeps a window in
    the top band until `SetWindowPos` is told otherwise — which is how the unpin button
    could look dead even while the flag was correct. Qt does this itself on some paths and
    not on others, so the card asks explicitly. Off Windows, and under the offscreen test
    platform, there is no band to change and this just reports False.
    """
    try:
        import ctypes
        handle = int(window.winId())
        if not handle:
            return False
        band = ctypes.c_void_p(-1 if pinned else 0)     # HWND_TOPMOST / HWND_NOTOPMOST
        flags = 0x0001 | 0x0002 | 0x0010               # NOMOVE | NOSIZE | NOACTIVATE
        return bool(ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(handle), band,
                                                      0, 0, 0, 0, flags))
    except Exception:
        return False


class ReviewDialog(QDialog):
    pin_changed = pyqtSignal(bool)
    # 回看上一张: the card asks, the controller decides — only it knows what was already
    # answered, and a look-back must never reach the scheduler.
    review_requested = pyqtSignal(object)
    review_back_requested = pyqtSignal(object)
    # On the class, not only in __init__: an event can reach `eventFilter` before the
    # constructor has run as far as the stylesheet, and reading a missing attribute inside
    # an event filter aborts the process instead of raising a catchable error.
    review_note = None
    suppress_speech = False
    # Counts speech requests across every card, so a render that finishes after the next
    # card has taken the screen is dropped instead of speaking the older word.
    speech_generation = 0
    # Same reason as above: the hint breakdown is read while painting the answer face, and
    # an event can arrive before __init__ reaches these lines.
    audio_hint_uses = 0
    other_hint_uses = 0
    revealed_indices = ()
    # The celebration overlay is built on the first spelling card that earns one, and it is
    # a child of this card, so hiding the card must hide it with it.
    celebration = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        child = getattr(self, '_embedded_dialog', None)
        if child is not None:
            child.setGeometry(self.rect())

    def __init__(self, question, position, grade, cfg=None, progress='', open_settings=None, open_word=None, lookup_example=None):
        super().__init__(None)
        self.question, self.position, self.grade = question, position, grade
        self.answer_form = question.get('answer_form') or question['word']
        self.cfg = cfg or {}
        self.open_word = open_word
        self.lookup_example = lookup_example
        self.known_words = set()
        self.example_labels = []
        self.relations = {}
        self.relations_shown = set()
        self._flipping = False
        self._relations_dirty = False
        self.relation_labels = {}
        self.answer_shown = False
        # 看回题目: whichever widgets the answer face folded away are remembered, so F can
        # bring back exactly what was there — and the card knows which face it is showing.
        self.front_widgets = []
        self.showing_front = False
        self.input_mode = ReviewInputMode()
        self.finished.connect(lambda _result: self.input_mode.restore())
        # The thread layout is the lever that actually bypasses a TSF input method such as
        # 微软拼音; the IMM32 switch above is kept because legacy engines do honour it.
        self.keyboard = input_mode.ThreadKeyboardLayout()
        self.finished.connect(lambda _result: self.keyboard.restore())
        self.enter_ease = None
        self.answer_seconds = None
        self.shown_at = None
        self.grading = False
        self.force_again = False
        self.completed = False
        self.skipped = False
        self.hints = 0
        self.hint_uses = 0
        # The three kinds of hint are priced differently now (2026-11-04): listening to the
        # word once is nearly free, a revealed letter costs what its position is worth, and
        # 释义/例句 still hands over the direction of the answer. `hint_uses` stays the total
        # for the scheduler-facing rules, these feed the recommendation.
        self.audio_hint_uses = 0
        self.other_hint_uses = 0
        self.revealed_indices = set()
        self.incorrect_letters = 0
        self.failed_attempts = 0
        self.setWindowTitle('单词随身复习')
        # A normal window, not a Qt tool window: tool windows have no taskbar button and
        # Windows hides them the moment the app loses focus, which is how an unpinned card
        # "disappeared" when the user clicked elsewhere. The minimise and maximise buttons
        # are what make Windows offer its snap layouts when the card is dragged to a screen
        # edge. Pinning is per pop-up — a new card always starts on top.
        flags = (Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint
                 | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        if self.cfg.get('review_pin', True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        try:
            # The taskbar button should look like Anki, not like an anonymous Qt window.
            self.setWindowIcon(mw.windowIcon())
        except Exception:
            pass
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setStyleSheet(popup_style(self.cfg))
        self.resize(510, 570)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(10)
        top = QHBoxLayout()
        # The card must say which book it came from and how far that book has been
        # studied, so a 四级 and a 六级 session are tellable at a glance.
        book = book_label(self.cfg)
        learned, total = self.cfg.get('_book_progress') or (0, 0)
        state = study_state_label(question['kind'], question.get('learning'))
        parts = [book or '未选词书', ('%d/%d' % (learned, total)) if total else '', state]
        eyebrow = _plain_label('VOCABULARY  ·  %s' % '  ·  '.join(part for part in parts if part), 'eyebrow')
        # The three labels are easy to confuse and the card itself does not explain them, so
        # the tooltip says what each one claims about Anki's own schedule.
        eyebrow.setToolTip('当前词书：%s%s\n%s：%s' % (
            book or '未选择', '，已学 %d / 共 %d' % (learned, total) if total else '',
            state, STUDY_STATE_NOTES[state]))
        eyebrow.setWordWrap(False)
        top.addWidget(eyebrow, 1)
        self.pin_button = QPushButton()
        self.pin_button.setObjectName('pin')
        self.pin_button.setCheckable(True)
        self.pin_button.setFixedSize(30, 30)
        self.pin_button.setChecked(bool(self.cfg.get('review_pin', True)))
        self._set_pin_icon()
        self.pin_button.toggled.connect(self.apply_pin)
        top.addWidget(self.pin_button)
        menu_button = QPushButton('...')
        menu_button.setObjectName('cardMenu')
        menu_button.setFixedSize(32, 32)
        menu_button.setToolTip('卡片设置和功能')
        menu = QMenu(menu_button)
        settings_action = menu.addAction('卡片设置…')
        settings_action.setEnabled(open_settings is not None)
        settings_action.triggered.connect(lambda: open_settings(self) if open_settings else None)
        mechanism = menu.addAction('评分与复习机制')
        mechanism.triggered.connect(lambda: QMessageBox.information(self, '评分与复习机制',
            '答错或直接显示答案按 Again。答对时会根据拼写错误和提示次数建议评分；你也可以自己调整。复习日期由 Anki 排程决定。'))
        # The answer face used to carry a whole row of its own for this one action
        # (「不评分，结束」). Escape already did it, the row cost vertical space the
        # explanations need, so the action moved here and the row went away.
        ungraded = menu.addAction('不评分，结束')
        ungraded.triggered.connect(self.reject)
        front_action = menu.addAction('看回题目（Shift+F）')
        front_action.triggered.connect(lambda _checked=False: self.toggle_front())
        look_back = menu.addAction('回看上一张（P）')
        look_back.triggered.connect(lambda _checked=False: self.review_requested.emit(self))
        zotero = menu.addAction('Zotero 配套插件介绍与下载')
        zotero.triggered.connect(lambda: QDesktopServices.openUrl(QUrl('https://github.com/zrqworkmail-cloud/zotero-vocab-review')))
        # The card outlives the deck browser for this user, so the two window decisions
        # belong here rather than in a menu they have to go back to Anki to find.
        hide_main = menu.addAction('隐藏 Anki 主窗口')
        hide_main.triggered.connect(self.hide_main_window)
        quit_anki = menu.addAction('退出 Anki')
        quit_anki.triggered.connect(self.quit_anki)
        menu_button.setMenu(menu)
        top.addWidget(menu_button)
        layout.addLayout(top)
        remaining = question.get('_today_remaining')
        today_text = ('今日计划剩余：%d 张%s' % (remaining, '（含当前卡）' if remaining else '（目标已完成）')
                      if remaining is not None else '今日计划剩余：暂无计划数据')
        progress_text = '本组 %s  ·  %s' % (progress, today_text)
        progress_label = _plain_label(progress_text, 'status')
        progress_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(progress_label)
        mode = question['mode']
        prompt = {'choice': '选择正确的中文释义', 'reverse': '选择对应的英文单词',
                  'typing': '根据释义拼写单词原形', 'cloze': '根据例句与释义填写句中词形',
                  'listening': '听写题：听发音，拼写单词原形', 'judgment': '这个单词与释义匹配吗？',
                  'speaking': '看释义，说出英文单词，再自主评分'}[mode]
        self.prompt_label = _plain_label(prompt, 'status')
        layout.addWidget(self.prompt_label)
        mask = lambda text: mask_answer_clues(text, question['word'], question.get('source_form', ''))
        content = question['word'] if mode in ('choice', 'judgment') else mask(question['meaning'])[:320]
        if mode not in ('choice', 'judgment'):
            self.question_block = QWidget()
            self.question_block.setObjectName('questionBlock')
            block_layout = QVBoxLayout(self.question_block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(6)
            self.meaning_heading = _plain_label('【解释】', 'meaningHeading')
            block_layout.addWidget(self.meaning_heading)
            self.question_label = _meaning_label(content, 'meaning')
            block_layout.addWidget(self.question_label)
            if mode == 'listening':
                self.meaning_heading.hide()
                self.question_label.hide()
                listen_row = QHBoxLayout()
                # The replay control is the same round speaker button as everywhere
                # else; a wide text button made this card look like another window.
                self.listen_button = self.speaker_button([question['word']], '重新播放单词发音',
                                                         on_click=self.play_listening_prompt)
                listen_row.addWidget(self.listen_button)
                listen_row.addWidget(_plain_label('重听发音', 'status'))
                listen_row.addStretch()
                block_layout.insertLayout(0, listen_row)
                # The sentence that used to live here explained that the word was hidden and
                # pointed at a button by name. The row now says that itself, so what occupies
                # the slot is the transcription -- hidden until 音标 is asked for, which keeps
                # the card the same height whether or not the sound can be heard.
                self.front_phonetic = _plain_label(question.get('phonetic', ''), 'status')
                self.front_phonetic.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                self.front_phonetic.hide()
                block_layout.insertWidget(1, self.front_phonetic)
            layout.addWidget(self.question_block)
        else:
            self.question_label = _plain_label(content, 'question')
            # The prompt is the word itself here, so it sits on the card's centre line
            # like the answer face does; a left-aligned word reads like a heading.
            self.question_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.front_speaker = None
            if mode in FRONT_AUDIO_MODES:
                # The word is already printed, so hearing it is the ear's turn rather than
                # a hint — and it must not be priced as one. 中文选英文 deliberately has no
                # speaker: there the English word IS the answer.
                word_row = QHBoxLayout()
                word_row.setSpacing(0)
                word_row.addStretch()
                word_row.addSpacing(WORD_SPEAKER + 6)
                word_row.addWidget(self.question_label)
                word_row.addSpacing(6)
                self.front_speaker = self.speaker_button([question['word']], '朗读单词（回车同样）',
                                                         size=WORD_SPEAKER,
                                                         on_click=self.play_word_prompt)
                word_row.addWidget(self.front_speaker)
                word_row.addStretch()
                layout.addLayout(word_row)
            else:
                layout.addWidget(self.question_label)
        if mode == 'judgment':
            self.judgment_label = _meaning_label(mask(question['judgment_statement']), 'meaning')
            layout.addWidget(self.judgment_label)
        if mode == 'cloze':
            source_title, source = next(((title, text) for title, text in
                                          (('例句', question.get('example', '')), ('权威例句', question.get('literature', '')))
                                          if cloze_sentence(text, question['word'])), ('例句', ''))
            groups = example_groups(source) or [question.get('cloze', '')]
            examples_widget = QWidget()
            examples_widget.setObjectName('questionBlock')
            examples_layout = QVBoxLayout(examples_widget)
            examples_layout.setContentsMargins(0, 0, 0, 0)
            examples_layout.setSpacing(8)
            examples_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.question_example_cards = []
            for index, group in enumerate(groups, 1):
                is_literature = bool(literature_example_html(group) or re.match(r'^\s*文献例句\s*[:：]', group))
                title = '文献例句' if is_literature else source_title
                heading = '%s %d' % (title, index) if len(groups) > 1 else title
                masked = mask(group)
                card, _label = self.make_detail(heading, masked, spoken_examples(group, '', 'example'), hint=True)
                examples_layout.addWidget(card)
                self.question_example_cards.append(card)
            self.question_examples = QScrollArea()
            self.question_examples.setWidgetResizable(True)
            self.question_examples.setWidget(examples_widget)
            block_layout.addWidget(self.question_examples)
        if mode == 'choice' and question.get('phonetic'):
            self.phonetic_label = _plain_label(question['phonetic'], 'status')
            self.phonetic_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(self.phonetic_label)

        self.input = None
        self.letter_boxes = []
        self.letter_positions = [(i, c) for i, c in enumerate(self.answer_form) if c.isalpha()]
        self.choice_buttons = []
        self.spoken_answer_button = None
        self.spoken_unknown_button = None
        self.hint_label = None
        self.hint_button = None
        self.letter_label = None
        self.check_button = None
        self.answer_button = None
        self.phonetic_hint_button = None
        if mode in ('choice', 'reverse', 'judgment'):
            correct = (question['meaning'] if mode == 'choice' else question['word'] if mode == 'reverse'
                       else ('正确' if question['judgment_correct'] else '错误'))
            for index, option in enumerate(question['options']):
                display_option = mask(option) if mode == 'choice' else option
                row = _ChoiceRow(chr(65 + index), display_option)
                row.setToolTip(display_option)
                row.clicked.connect(lambda _checked=False, value=option: self.reveal(value == correct))
                self.choice_buttons.append(row)
                row.installEventFilter(self)
                # No stretch: an option is exactly as tall as its own text. With `1` here the
                # rows divided the window's leftover height between themselves, which measured
                # 190 px per row for a two-option 判断题 in a 710 px window whose natural row
                # height is 37 px — the screenshot the user sent on 2026-11-04.
                layout.addWidget(row)
            self.installEventFilter(self)
        elif mode == 'speaking':
            self.spoken_answer_button = QPushButton('我已说出，查看答案')
            self.spoken_answer_button.setObjectName('primary')
            self.spoken_answer_button.clicked.connect(lambda: self.reveal(None))
            layout.addWidget(self.spoken_answer_button)
            self.spoken_unknown_button = QPushButton('想不起来，显示答案')
            self.spoken_unknown_button.clicked.connect(lambda: self.reveal(False))
            layout.addWidget(self.spoken_unknown_button)
        else:
            row = QWidget()
            row.setObjectName('letterRow')
            rows = QVBoxLayout(row)
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setSpacing(4)
            chunks = [self.answer_form[i:i + 10] for i in range(0, len(self.answer_form), 10)] or ['']
            for chunk in chunks:
                row_layout = QHBoxLayout()
                row_layout.setSpacing(4)
                row_layout.addStretch()
                for char in chunk:
                    if char.isalpha():
                        box = LetterBox(self, len(self.letter_boxes))
                        self.letter_boxes.append(box)
                        row_layout.addWidget(box)
                    else:
                        row_layout.addWidget(_plain_label(char))
                row_layout.addStretch()
                rows.addLayout(row_layout)
            self.letter_scroll = QScrollArea()
            self.letter_scroll.setWidget(row)
            self.letter_scroll.setWidgetResizable(True)
            self.letter_scroll.setStyleSheet('QScrollArea, QScrollArea > QWidget { background: %s; border: none; }' % ('#171c2b' if self.cfg.get('review_theme') == 'dark' else '#f4f6fb'))
            self.letter_scroll.setFixedHeight(min(190, max(65, 12 + len(chunks) * 44)))
            layout.addWidget(self.letter_scroll)
            # Two lines, split by what they are for (user 2026-11-06: 提示排的排版需要重新设计).
            # The aids sit under the boxes they change, in the quiet text style the card already
            # uses for 稍后再说; the one thing done on every card -- submit -- is the only filled
            # button and gets its own centred line, on the same axis as the word and the boxes.
            # 显示答案 is not an aid, it is giving up, so it is not here at all: it joins
            # 稍后再说 in the foot, as far from 检查拼写 as the card allows.
            aids = QHBoxLayout()
            aids.setSpacing(2)
            self.check_button = QPushButton('检查拼写')
            self.check_button.setObjectName('primary')
            self.check_button.setMinimumWidth(168)
            self.check_button.clicked.connect(self.check_input)
            self.hint_button = QPushButton(letter_hint_label(0, len(self.letter_positions)))
            self.hint_button.setToolTip('输入字母时按空格可显示下一个提示字母')
            self.hint_button.clicked.connect(self.add_hint)
            if mode == 'listening':
                self.meaning_hint_button = QPushButton('释义')
                self.meaning_hint_button.setToolTip('显示中文释义；看过即计入提示')
                self.meaning_hint_button.clicked.connect(self.show_meaning_hint)
                aids.addWidget(self.meaning_hint_button)
            if mode == 'typing':
                self.example_hint_button = QPushButton('例句')
                self.example_hint_button.setToolTip('显示藏起目标词的例句；看过即计入提示')
                self.example_hint_button.clicked.connect(self.request_example_hint)
                aids.addWidget(self.example_hint_button)
            if mode == 'listening' and phonetic_available(question):
                # The learner asked for the transcription so the card works with the sound off
                # (2026-11-06); it is priced as a hint because a phonetic nearly spells the
                # word, and it is absent entirely when the note has no 音标 field.
                self.phonetic_hint_button = QPushButton('音标')
                self.phonetic_hint_button.setToolTip('听不到发音时看音标拼，Shift+空格同样；看过即计入提示')
                self.phonetic_hint_button.clicked.connect(self.show_phonetic_hint)
                aids.addWidget(self.phonetic_hint_button)
            aids.addWidget(self.hint_button)
            aids.addStretch()
            for button in (getattr(self, 'meaning_hint_button', None),
                           getattr(self, 'example_hint_button', None),
                           self.phonetic_hint_button, self.hint_button):
                if button is not None:
                    button.setObjectName('aid')
            actions = QHBoxLayout()
            actions.addStretch()
            actions.addWidget(self.check_button)
            actions.addStretch()
            row_box = QVBoxLayout()
            row_box.setSpacing(4)
            row_box.addLayout(aids)
            row_box.addLayout(actions)
            layout.addLayout(row_box)
            self.answer_button = QPushButton('显示答案')
            self.answer_button.setObjectName('secondary')
            self.answer_button.clicked.connect(lambda: self.reveal(False))

        self.result_label = _plain_label('', 'result')
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.hide()
        self.answer_word = _plain_label('', 'question')
        self.answer_word.setAlignment(Qt.AlignmentFlag.AlignCenter)
        answer_content = QWidget()
        answer_content.setObjectName('answerContent')
        self.answer_layout = QVBoxLayout(answer_content)
        self.answer_layout.setContentsMargins(0, 0, 0, 0)
        self.answer_layout.setSpacing(8)
        self.answer_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        word_row = QHBoxLayout()
        # The word is the thing that should sit on the centre line, so the speaker's own
        # width is balanced by an empty spacer on the other side: with equal weight on both
        # sides of the label, the word itself is centred and the speaker just hugs it.
        word_row.setSpacing(0)
        word_row.addStretch()
        word_row.addSpacing(WORD_SPEAKER + 6)
        word_row.addWidget(self.answer_word)
        word_row.addSpacing(6)
        self.answer_speaker = self.speaker_button([question['word']], '朗读单词', size=WORD_SPEAKER)
        word_row.addWidget(self.answer_speaker)
        word_row.addStretch()
        self.answer_layout.addLayout(word_row)
        self.answer_phonetic = _plain_label(question.get('phonetic', ''), 'status')
        self.answer_phonetic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.answer_layout.addWidget(self.answer_phonetic)
        self.answer_labels = []
        self.answer_scroll = QScrollArea()
        self.answer_scroll.setWidgetResizable(True)
        self.answer_scroll.setMinimumHeight(240)
        # The explanations are the reason the card exists, so they get the floor and every
        # pixel the user wins by enlarging the window (the layout gives them the only
        # stretch factor). The ratings and the word-list pills stay compact below it.
        self.answer_scroll.setWidget(answer_content)
        self.answer_scroll.hide()
        layout.addWidget(self.answer_scroll)
        layout.setStretchFactor(self.answer_scroll, 1)
        layout.addWidget(self.result_label)
        self.status = _plain_label('先尝试回答；需要时可以使用提示。', 'status')
        if mode in FRONT_AUDIO_MODES:
            self.status.setText('先尝试回答；回车或点喇叭可听发音。')
        if self.letter_boxes:
            self.status.setText('空格给字母提示 · 回车检查拼写')
            if mode == 'listening':
                self.status.setText('回车重听 · 空格给字母提示' if self.phonetic_hint_button is None
                                    else '回车重听 · 空格给字母 · Shift+空格给音标')
        elif self.spoken_answer_button is not None:
            self.status.setText('回车：我已说出，查看答案。空格：想不起来，显示答案。')
        layout.addWidget(self.status)
        self.grade_widget = QWidget()
        grade_layout = QHBoxLayout(self.grade_widget)
        grade_layout.setContentsMargins(0, 0, 0, 0)
        # Centred, so the empty gap to the left of A. Again equals the one to the right of
        # D. Easy rather than all of it piling up on one side.
        grade_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.grade_buttons = []
        for letter, (caption, ease) in enumerate((('Again', 1), ('Hard', 2), ('Good', 3), ('Easy', 4))):
            button = QPushButton()
            button.setProperty('gradeCaption', caption)
            button.setProperty('gradeEase', ease)
            size_rating_button(button)
            button.clicked.connect(lambda _checked=False, value=ease: self.start_grade(value))
            self.grade_buttons.append(button)
            grade_layout.addWidget(button)
        self.label_grade_buttons()
        self.grade_widget.hide()
        layout.addWidget(self.grade_widget)
        self.later = QPushButton('稍后再说')
        self.later.setObjectName('secondary')
        self.later.clicked.connect(self.reject)
        # The foot holds the two ways of not answering this card: give up and look at the
        # answer, or leave it for later. They belong together, and away from 检查拼写 -- the
        # old row put 显示答案 right beside the submit button, one mis-click from an Again.
        footer = QHBoxLayout()
        footer.addStretch()
        if self.answer_button is not None:
            footer.addWidget(self.answer_button)
            footer.addSpacing(20)
        footer.addWidget(self.later)
        footer.addStretch()
        layout.addLayout(footer)
        # 回看上一张的页脚。一张已经评过分、不会再排程的卡能给的只有两件事：再看一张，
        # 或者回去 —— 评分行在这种卡上必须消失。
        self.review_bar = QWidget()
        self.review_bar.setObjectName('reviewBar')
        review_layout = QHBoxLayout(self.review_bar)
        review_layout.setContentsMargins(0, 0, 0, 0)
        review_layout.setSpacing(8)
        self.review_back_button = QPushButton('← 上一张')
        self.review_back_button.setObjectName('reviewBack')
        self.review_back_button.clicked.connect(lambda _checked=False: self.review_back_requested.emit(self))
        self.review_exit_button = QPushButton('退出回看')
        self.review_exit_button.setObjectName('reviewExit')
        self.review_exit_button.clicked.connect(self.reject)
        review_layout.addWidget(self.review_back_button)
        review_layout.addWidget(self.review_exit_button)
        self.review_bar.hide()
        layout.addWidget(self.review_bar)
        # Which exam lists the word belongs to belongs at the foot of the card as one small
        # pill per list, and the provenance rides on the pill it explains. A single label
        # joined with "·" used to lose its last name and leave a dangling dot behind, which
        # read as a typo rather than as truncated text.
        self.book_chip = QWidget()
        self.book_chip.setObjectName('bookChipRow')
        chip_row = QHBoxLayout(self.book_chip)
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(CHIP_GAP)
        # Aligning the layout, not the layout item: the pills then keep their own size hint
        # instead of being stretched into three wide bars.
        chip_row.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        # Decided here rather than at reveal because the card is sized to fit them once, at
        # birth: a word in three lists needs more room than the rating row.
        self.book_chips = []
        for label in exam_word_labels(question['word']):
            # Not _plain_label: that turns word wrap on, and a wrapped QLabel's size hint is
            # a guess at a paragraph rather than the width of four characters — which is how
            # these boxes ended up roomier than their text.
            pill = QLabel(label)
            pill.setTextFormat(Qt.TextFormat.PlainText)
            pill.setObjectName('bookChip')
            # A QLabel that draws a stylesheet frame indents its text by two characters'
            # width unless told otherwise, which made each pill 12px wider than its text.
            pill.setIndent(0)
            pill.setMargin(0)
            source = BOOK_LABEL_SOURCES.get(label)
            if source:
                pill.setToolTip('来源：%s' % source)
            chip_row.addWidget(pill)
            self.book_chips.append(pill)
        self.book_chip.hide()
        # Stretch 0: the pills belong under the rating row, not in whatever band is left
        # over. With a stretch factor they drifted to the foot of a half-empty card and the
        # gap above them read as a broken layout.
        layout.addWidget(self.book_chip)
        self.fit_card_width()

    def fit_card_width(self):
        """Widen the card once, at birth, so nothing on it has to be clipped.

        Two rows decide the width: the four ratings, which share one line, and the
        word-list pills, which are never allowed to be squeezed. Measuring with the dialog's
        font was not enough — the stylesheet paints the buttons with its own family, and the
        row came out narrower than its own text on the real machine while every offscreen
        check stayed green. Everything here is measured with the widget's own polished font,
        and `ensure_row_fits()` re-checks the row once it is actually on screen.
        """
        row = self.grade_widget.layout()
        buttons = [button for button in self.grade_buttons if button.text()]
        for button in buttons:
            button.ensurePolished()
            button.setMinimumWidth(QFontMetrics(button.font()).horizontalAdvance(button.text()) + 26)
        needed = self.row_demand()
        needed = max(needed, sum(button.sizeHint().width() for button in buttons)
                     + row.spacing() * max(0, len(buttons) - 1))
        margins = self.layout().contentsMargins()
        room = margins.left() + margins.right() + 8
        chip_width = 0
        for pill in self.book_chips:
            pill.ensurePolished()
            # Each pill is its text plus the stylesheet's own horizontal padding, and +2 for
            # the border the label paints.
            chip_width += QFontMetrics(pill.font()).horizontalAdvance(pill.text()) \
                + 2 * CHIP_PADDING_X + 2
        chip_width += CHIP_GAP * max(0, len(self.book_chips) - 1)
        room = margins.left() + margins.right() + 8
        # Qt's own arithmetic over the children's minimums, as a check on the estimates: the
        # row is measured with the font the card paints with, and an estimate that comes in
        # short shows up here as a wider demand.
        demanded = self.layout().totalMinimumSize().width()
        width = max(510, needed + room, chip_width + room, demanded + 8)
        try:
            from . import log_runtime
            log_runtime('card sized for %s: width=%d row=%d chips=%d layout-min=%d' % (
                self.question['word'], width, needed + room, chip_width + room, demanded))
        except Exception:
            pass
        self.setMinimumWidth(width)
        if needed:
            self.grade_widget.setMinimumWidth(needed + 2)
        self.resize(width, self.height())

    def card_window(self):
        """The window this card is actually drawn in.

        An in-place swap embeds the new card inside the old card's window, so resizing
        `self` there would make the widget larger than the window that shows it: the front
        face came back as a pile of overlapping pixels. The host window is the thing with
        the title bar, and its resizeEvent already keeps the embedded card filling it.
        """
        return self.window() if getattr(self, '_embedded', False) else self

    def fit_card_height(self):
        """Make the window exactly as tall as the content needs — and never wider.

        The card used to only ever get *shorter*: `min(window.height(), hint)` meant a
        question whose 释义 runs to six lines was quietly cut off at the bottom of a window
        sized by some earlier, smaller card. That is what the learner reported on
        2026-11-05 as 「字母提示按钮…看不全」, and the live captures proved the mechanism:
        every card in a session arrived in the same 526x609 window, because the handover
        leaves the new card inside the previous card's window and nothing resized it.

        It now fits the content in BOTH directions. Shrinking matters as much as growing:
        the surplus left by a tall card in a short one is the dead band the learner pointed
        at next (「空隙太大了…应该让他们锚定下边缘」), and anchoring the rows would only have
        moved that band somewhere else. The learner approved two-way fitting on
        2026-11-05, which replaces the earlier "换卡不许跳窗口" decision **for height only** —
        width is still never recomputed here, because a width change mid-flip is the jump
        that was rejected and the rating row is sized for it at birth.

        §9.32's real constraint survives: an embedded card must fill the window it is drawn
        in. That is held by the host's own `resizeEvent`, which re-fills the child with the
        new rect — resizing the host keeps card and window in lockstep, which is what the
        overlap bug needed fixed, not the resize forbidden.
        """
        # Recompute before reading. A flip runs with updates disabled, and a nested layout
        # (the hint row is two of them since 2026-11-06) otherwise answers from the height the
        # *other* face needed -- the fit then happily preserved a 37 px dead band.
        layout = self.layout()
        layout.invalidate()
        layout.activate()
        hint = layout.sizeHint().height()
        if hint <= 0:
            return
        window = self.card_window()
        screen = QApplication.primaryScreen()
        ceiling = hint if screen is None else min(hint, screen.availableGeometry().height() - 120)
        # No magic floor: `sizeHint` is already at least the layout's minimum, and a fixed
        # 360 used to hold the window taller than a short face needed — that surplus is
        # precisely the dead band the learner asked to remove. The host's own minimum is not
        # a usable floor either, because an embedded card is positioned by geometry and is
        # not part of the host's layout.
        needed = ceiling
        if abs(window.height() - needed) < 24:
            return                      # a tolerance, so repeated flips do not jitter
        window.resize(window.width(), needed)
        window.update()
        if window is not self and hasattr(window, 'position_window'):
            # The host owns the on-screen rectangle, so it re-anchors after either change:
            # growing downward can push the foot off the screen, shrinking can float it.
            window.position_window()

    def ensure_row_fits(self):
        """Make the window as wide as its own content asks for, once it is on screen.

        The width is settled at birth so a normal flip never jumps — but every estimate made
        before the card is visible has come out short on the real machine (the log said
        `row=486 layout-min=466` while the pixels needed ~476), because a hidden widget's size
        hint is computed before the stylesheet's font has fully reached it. Once the row is
        laid out, Qt's own `totalSizeHint()` is no longer a guess, so the card grows to it.
        The three numbers are logged either way, so the next card tells us if anything is
        still being under-read.
        """
        margins = self.layout().contentsMargins()
        # Re-measure with the fonts the buttons actually have now that they are on screen:
        # a hidden widget's size hint is computed before the stylesheet's face has fully
        # reached it, and every width settled at birth has come out short because of that.
        for button in self.visible_grade_buttons():
            if button.text() and not button.isHidden():
                self.size_grade_button(button)
        laid = self.layout().totalSizeHint().width()
        minimum = self.layout().totalMinimumSize().width()
        demand = max(self.row_demand() + margins.left() + margins.right(), laid, minimum)
        # The window that shows this card, not the card itself: an embedded card resized on
        # its own would grow past the frame that paints it and leave stale pixels behind.
        window = self.card_window()
        if demand + 4 > window.width():
            try:
                from . import log_runtime
                log_runtime('card widened at reveal for %s: %d -> %d (row=%d sizeHint=%d minimum=%d)' % (
                    self.question['word'], window.width(), demand + 8,
                    self.row_demand() + margins.left() + margins.right(), laid, minimum))
            except Exception:
                pass
            window.resize(demand + 8, window.height())
            window.update()
        else:
            try:
                from . import log_runtime
                log_runtime('row fit for %s: card=%d row=%d sizeHint=%d minimum=%d' % (
                    self.question['word'], window.width(), self.row_demand()
                    + margins.left() + margins.right(), laid, minimum))
            except Exception:
                pass
        return demand

    def showEvent(self, event):
        super().showEvent(event)
        # English for the whole life of the card, in every question type: A–D on a choice
        # card and A–D / F / P on the answer face are letter keys, and a Chinese input method
        # in the way of those is the same failure the spelling boxes had, in a different
        # costume. Handed back in `hideEvent`, which the handover also triggers.
        self.keyboard.enable()
        # The reaction window is measured from the moment this card appeared, not from the
        # moment the answer was checked.
        self.shown_at = time.monotonic()
        # Whatever the previous card was still reading belongs to that card.
        stop_speech()
        ReviewDialog.speech_generation += 1
        # Every pop-up starts on top, so the band is re-asserted here as well as in the
        # flags: Windows remembers the band, not the flag.
        if int(self.window().windowFlags()) & int(Qt.WindowType.WindowStaysOnTopHint):
            set_topmost_band(self.window(), True)
        if hasattr(self, 'question_examples'):
            QTimer.singleShot(0, self.resize_question_examples)
        # Once the window is laid out, Qt's own size hints are final — so settle the width
        # here, before the answer can appear, instead of jumping when it does.
        QTimer.singleShot(0, self.ensure_row_fits)
        previous = getattr(self, '_handoff_geometry', None)
        if getattr(self, '_embedded', False):
            pass
        elif previous is None:
            self.position_window()
        elif self.position == 'center':
            self.move(self._handoff_position.x() + (previous.width() - self.width()) // 2,
                      self._handoff_position.y() + (previous.height() - self.height()) // 2)
        else:
            self.move(self._handoff_position.x() + previous.width() - self.width(),
                      self._handoff_position.y() + previous.height() - self.height())
        if self.letter_boxes:
            QTimer.singleShot(0, self.focus_spelling)
            if self.question['mode'] == 'listening' and not getattr(self, '_listening_played', False):
                self._listening_played = True
                QTimer.singleShot(0, self.play_listening_prompt)
        elif self.choice_buttons:
            QTimer.singleShot(0, self.focus_choices)
        elif self.spoken_answer_button is not None:
            QTimer.singleShot(0, self.focus_spoken)

    def focus_spoken(self):
        # Without this, a speaking card leaves focus on the '...' menu button and
        # Enter opens the card menu instead of answering.
        if self.isVisible() and not self.answer_shown:
            self.activateWindow()
            self.spoken_answer_button.setFocus()

    def focus_choices(self):
        if self.isVisible() and not self.answer_shown:
            self.activateWindow()
            self.choice_buttons[0].setFocus()

    def focus_spelling(self):
        if self.isVisible() and not self.answer_shown:
            self.activateWindow()
            self.letter_boxes[0].setFocus()

    def resize_question_examples(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if not screen or not self.question_examples.isVisible():
            return
        width = max(100, self.question_examples.viewport().width() - 8)
        content = self.question_examples.widget()
        height = max(content.layout().heightForWidth(width), content.sizeHint().height()) + 4
        self.question_examples.setFixedHeight(min(height, max(120, screen.availableGeometry().height() - 430)))
        if getattr(self, '_handoff_geometry', None) is None:
            self.adjustSize()
            self.position_window()

    def _set_pin_icon(self):
        """The pushpin carries the state: upright and filled, or tipped over as a line."""
        pinned = self.pin_button.isChecked()
        theme = 'dark' if self.cfg.get('review_theme') == 'dark' else 'light'
        self.pin_button.setIcon(pin_icon(pinned, PIN_COLORS[theme]))
        self.pin_button.setToolTip('卡片置顶中，点击取消置顶' if pinned else '卡片未置顶，点击让它总在最前面')
        self.pin_button.setAccessibleName('已置顶' if pinned else '未置顶')

    def apply_pin(self, pinned):
        """Re-apply the flags on the top-level window without losing where it sits.

        After a flip the card is a child embedded in the host window, and window flags on
        a child do nothing at all — so the host is what has to change. Qt also hides a
        widget whose flags change, which is why this shows it again at the same place.
        """
        window = self.window()
        flags = window.windowFlags()
        if pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        visible = window.isVisible()
        geometry = window.geometry()
        window.setWindowFlags(flags)
        if visible:
            window.show()
            window.setGeometry(geometry)
        set_topmost_band(window, pinned)
        if pinned:
            window.raise_()
        self._set_pin_icon()
        self.pin_changed.emit(bool(pinned))

    def hide_main_window(self):
        try:
            mw.hide()
        except Exception as error:
            self.status.setText('主窗口没能隐藏：%s' % type(error).__name__)

    def quit_anki(self):
        """Quit for real: the close filter only hides the window while a card is up."""
        try:
            mw.zvr_force_quit = True
            # The user also runs a tray add-on, which rewrites mw.closeEvent so that closing
            # a window only hides it, and performs a real shutdown only under its own flag.
            # Without that flag 「退出 Anki」 would send the windows to the tray and leave
            # Anki running — so set it when that add-on is the one holding closeEvent.
            if hasattr(mw, 'closeEventFromAction'):
                mw.closeEventFromAction = True
            mw.close()
        except Exception as error:
            self.status.setText('Anki 没能退出：%s' % type(error).__name__)

    def position_window(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            if self.position == 'center':
                self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
            else:
                self.move(area.right() - self.width() - 20, area.bottom() - self.height() - 20)

    def themed_speaker_icon(self, size=32):
        glyph, disc, ring = SPEAKER_COLORS['dark' if self.cfg.get('review_theme') == 'dark' else 'light']
        return speaker_icon(glyph, disc, ring, size)

    def speaker_button(self, texts, tooltip, hint=False, size=32, on_click=None):
        """A round speaker the disc actually fills the button.

        The icon was drawn at 32px but never given an icon size, and a push button's
        default is 16 — so the disc arrived on screen at half the size it was drawn.
        """
        from PyQt6.QtCore import QSize
        button = QPushButton()
        button.setObjectName('speaker')
        button.setFixedSize(size, size)
        button.setIcon(self.themed_speaker_icon(size))
        button.setIconSize(QSize(size, size))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setEnabled(bool(texts))
        if on_click is not None:
            button.clicked.connect(on_click)
        else:
            button.clicked.connect(lambda: self.hear_hint(texts) if hint else self.speak_many(texts))
        return button

    def add_detail(self, heading, text, audio=False):
        card, label = self.make_detail(heading, text, spoken_examples(text, '', 'example') if audio else None)
        self.answer_labels.append(label)
        self.answer_layout.addWidget(card)

    def make_detail(self, heading, text, audio_texts=None, hint=False):
        card = QWidget()
        card.setObjectName('detailCard')
        column = QVBoxLayout(card)
        column.setContentsMargins(14, 10, 14, 12)
        column.setSpacing(4)
        column.setAlignment(Qt.AlignmentFlag.AlignTop)
        header = QHBoxLayout()
        heading_label = _plain_label('【%s】' % heading, 'cardHeading')
        heading_label.setWordWrap(False)
        header.addWidget(heading_label)
        header.addStretch()
        if audio_texts is not None:
            header.addWidget(self.speaker_button(audio_texts, '朗读%s' % heading, hint=hint,
                                                 size=HEADING_SPEAKER))
        column.addLayout(header)
        label = _meaning_label(text, 'cardText') if heading == '解释' else _plain_label(text, 'cardText')
        if heading != '解释':
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            label.setOpenExternalLinks(False)
            label.linkActivated.connect(self.word_link_activated)
            self.example_labels.append((label, text, heading))
            self._render_example(label, text, heading)
        column.addWidget(label)
        return card, label

    def _render_example(self, label, text, heading):
        formatted = (root_detail_html(text) if heading == '词根与词源' else
                     literature_example_html(text) if heading.startswith('文献例句') else None)
        if not formatted:
            formatted = '<p style="margin:0; line-height:125%;">' + html.escape(text, quote=False).replace('\n', '<br>') + '</p>'
        label.setText(link_example_html(formatted, self.question['word'], self.known_words,
                                        self.cfg.get('review_known_style', 'underline'),
                                        '#e2e9f6' if self.cfg.get('review_theme') == 'dark' else '#27344d'))

    def update_known_words(self, words):
        self.known_words = set(words)
        for label, text, heading in self.example_labels:
            self._render_example(label, text, heading)

    def word_link_activated(self, link):
        if link.startswith('zvr:') and self.open_word:
            self.open_word(link[4:], self)

    def add_hint(self):
        index = next_hint_index([c for _, c in self.letter_positions],
                                [box.text() for box in self.letter_boxes],
                                {i for i, box in enumerate(self.letter_boxes) if box.placeholderText()})
        if index is None:
            self.status.setText('当前没有可增加的字母提示。')
            return
        self.letter_boxes[index].setPlaceholderText(self.letter_positions[index][1])
        self.hints += 1
        self.hint_uses += 1
        self._note_revealed(index)
        # The button carries its own tally now, so the count that decides the recommendation
        # is visible before it is spent rather than only in the evidence line afterwards.
        self.hint_button.setText(letter_hint_label(len(self.revealed_indices),
                                                   len(self.letter_positions)))
        self.status.setText('已显示部分字母，可继续尝试；按空格可再提示一个字母。')
        if self.cfg.get('review_hint_audio', False):
            self.speak_many([self.letter_positions[index][1]])

    def _note_revealed(self, index):
        """Record which letter position a Space hint gave away, by index not by count."""
        if not isinstance(self.revealed_indices, set):
            self.revealed_indices = set(self.revealed_indices)
        self.revealed_indices.add(index)

    def pulse_timer(self):
        """One timer for the whole card: only one box can be focused, so one is enough."""
        timer = getattr(self, '_pulse_timer', None)
        if timer is None:
            timer = QTimer(self)
            timer.setInterval(LETTER_PULSE_MS)
            timer.timeout.connect(self._pulse_tick)
            self._pulse_timer = timer
        return timer

    def start_box_pulse(self):
        # Only starts the timer. Asking the dialog who has focus, or repainting a box, from
        # inside a focus event crashed the offscreen checks (0xC0000409, silently): Qt is
        # still moving the focus at that moment, so the repaint is left to the tick.
        timer = self.pulse_timer()
        if not timer.isActive():
            timer.start()

    def stop_box_pulse(self):
        timer = getattr(self, '_pulse_timer', None)
        if timer is not None and timer.isActive():
            timer.stop()

    def _pulse_tick(self):
        self._pulse_step = getattr(self, '_pulse_step', 0) + 1
        boxes = [box for box in (self.letter_boxes or []) if box.isVisible()]
        if not boxes:
            # The answer face, a look-back that folded them away, or a hidden card: nothing
            # to breathe, so the timer stops itself rather than outliving the face.
            self.stop_box_pulse()
            return
        for box in boxes:
            box.update()

    def focus_ring(self, box):
        """(draw, bright) -- whether this box wears the breathing frame, and which half.

        Never fully off while focused: the frame dims and brightens, so there is no
        half-period in which the card looks like nothing has focus.
        """
        if box not in (self.letter_boxes or []) or not box.isVisible():
            return (False, False)
        return (self.focusWidget() is box, pulse_bright(getattr(self, '_pulse_step', 0)))

    def hint_components(self):
        """The hint record the recommendation is computed from.

        `letters` is the number of boxes the word is actually spelled into, so the share is
        measured against this word, not against a fixed guess.
        """
        return {'audio_hints': int(self.audio_hint_uses or 0),
                'other_hints': int(self.other_hint_uses or 0),
                'revealed': set(self.revealed_indices or ()),
                'letters': len(self.letter_positions or ())}

    def request_example_hint(self):
        groups = example_groups(self.question.get('example', '')) + example_groups(self.question.get('literature', ''))
        group = next((item for item in groups if masked_example(item, self.question['word'])), None)
        if group:
            self.show_example_hint(group)
        elif self.lookup_example:
            self.example_hint_button.setEnabled(False)
            self.status.setText('正在查找例句…')
            self.lookup_example(self)
        else:
            self.status.setText('没有可用的例句提示。')

    def show_example_hint(self, group):
        masked = masked_example(group, self.question['word'])
        if not masked:
            self.example_hint_button.setEnabled(True)
            self.status.setText('没有找到包含该词的例句。')
            return
        masked = mask_answer_clues(masked, self.question['word'], self.question.get('source_form', ''))
        card, _label = self.make_detail('例句提示', masked, spoken_examples(group, '', 'example'), hint=True)
        self.question_block.layout().addWidget(card)
        self.example_hint_button.setEnabled(False)
        self.hint_uses += 1
        self.other_hint_uses += 1
        self.status.setText('例句中已隐藏目标词；使用提示会计入评分建议。')
        if not getattr(self, '_embedded', False):
            self.adjustSize()
            self.position_window()

    def hint_summary(self):
        """Say what the hints cost, in the units the recommendation is priced in.

        '提示 2 次' told the learner nothing about why the suggestion moved; the spelling
        card now names the listen count and the position-weighted share of the word.
        """
        record = self.hint_record or {}
        parts = []
        if self.audio_hint_uses:
            parts.append('发音提示 %d 次' % self.audio_hint_uses)
        revealed = record.get('revealed') or ()
        letters = record.get('letters') or 0
        if revealed and letters:
            parts.append('字母提示 %d/%d（按位置已给出 %d%%）' % (
                len(revealed), letters, round(hint_share(revealed, letters) * 100)))
        if record.get('other_hints'):
            parts.append('释义/例句提示 %d 次' % record['other_hints'])
        if parts:
            return '，'.join(parts)
        return '无提示' if self.question['mode'] == 'typing' else (
            '提示 %d 次' % self.hint_uses if self.hint_uses else '无提示')

    def input_complete_and_correct(self):
        return bool(self.letter_boxes) and all(
            box.text() and box.text().casefold() == expected.casefold()
            for box, (_, expected) in zip(self.letter_boxes, self.letter_positions))

    def check_input(self):
        if not self.letter_boxes or not all(box.text() for box in self.letter_boxes):
            self.status.setText('请填写所有字母，空格和标点已为你保留。')
            return
        chars = iter(box.text() for box in self.letter_boxes)
        value = ''.join(next(chars) if c.isalpha() else c for c in self.answer_form)
        if answer_matches(self.answer_form, value):
            self.reveal(True)
        else:
            self.failed_attempts += 1
            self.status.setText('拼写尚未完全正确：绿色位置正确，红色位置有误；可以继续尝试。')

    def play_listening_prompt(self):
        if self.isVisible() and not self.answer_shown:
            self.speak_many([self.question['word']])

    def play_word_prompt(self):
        """Read the word the question is already showing, on the learner's request.

        Deliberately `speak_many`, not `hear_hint`: hint counts feed the suggested rating,
        and hearing a word that is printed on the screen has not told the learner anything
        the screen had not already told them.
        """
        if (self.isVisible() and not self.answer_shown and not self.showing_front
                and self.question['mode'] in FRONT_AUDIO_MODES):
            self.speak_many([self.question['word']])
            return True
        return False

    def request_phonetic_hint(self):
        """The keyboard route to the transcription (learner 2026-11-06: 想看音标但不想用鼠标).

        It drives the same button the click does, so there is one accounting path, one
        disabled state and one status line -- and a card with no 音标 field ignores the key.
        """
        if self.phonetic_hint_button is None:
            return False
        if self.phonetic_hint_button.isEnabled():
            self.phonetic_hint_button.click()
        else:
            self.status.setText('本张卡的音标已经看过了；音标算一次提示。')
        return True

    def show_phonetic_hint(self):
        """Reveal the transcription, for the learner who cannot play the audio.

        Priced as a hint on purpose (user 2026-11-06 chose this over showing it always): a
        phonetic nearly spells the word, so once it is on screen this is no longer a listening
        card and the recommendation has to say so. One tap per card, like the other hints.
        """
        self.front_phonetic.show()
        self.phonetic_hint_button.setEnabled(False)
        self.hint_uses += 1
        self.other_hint_uses += 1
        self.status.setText('已显示音标；使用提示会计入评分建议。')
        self.fit_card_height()

    def show_meaning_hint(self):
        self.meaning_heading.show()
        self.question_label.show()
        self.meaning_hint_button.setEnabled(False)
        self.hint_uses += 1
        self.other_hint_uses += 1
        self.status.setText('已显示释义提示；使用提示会计入评分建议。')
        if not getattr(self, '_embedded', False):
            self.adjustSize()
            self.position_window()

    def hear_hint(self, texts):
        if self.speak_many(texts) is not False:
            self.hint_uses += 1
            self.audio_hint_uses += 1

    def speak_many(self, texts):
        try:
            from aqt.sound import av_player
            stop_speech()
            ReviewDialog.speech_generation += 1
            token = ReviewDialog.speech_generation
            return speech.speak(av_player, mw.taskman, texts, self.cfg.get('review_volume', 100),
                                self.tts_tag, on_error=self.speech_failed,
                                is_stale=lambda: token != ReviewDialog.speech_generation)
        except Exception:
            self.status.setText(self.status.text() + ' 系统语音不可用，请检查 Anki 的英文语音设置。')
            return False

    def speech_failed(self, error):
        # Loudness is not worth silence: the render failed, so say so instead of nothing.
        self.status.setText(self.status.text() + ' 加大音量时朗读失败，可把朗读音量调回 100%。')

    def tts_tag(self, text):
        from anki.sound import TTSTag
        return TTSTag(field_text=str(text)[:500], lang='en_US', voices=[], speed=1.0, other_args=[])

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.input_mode.restore()
        super().changeEvent(event)

    def eventFilter(self, watched, event):
        if isinstance(watched, QWidget) and watched is not self and not self.isAncestorOf(watched):
            return super().eventFilter(watched, event)
        if self.review_note is not None:
            # A look-back answers nothing: P/Esc go home, B walks one further back, and
            # every other key is left to Qt.
            if event.type() == QEvent.Type.KeyPress and event.modifiers() == Qt.KeyboardModifier.NoModifier:
                if event.key() in (Qt.Key.Key_P, Qt.Key.Key_Escape):
                    self.reject()
                    event.accept()
                    return True
                if event.key() == Qt.Key.Key_B:
                    self.review_back_requested.emit(self)
                    event.accept()
                    return True
            return super().eventFilter(watched, event)
        if (not self.answer_shown and self.question['mode'] in FRONT_AUDIO_MODES
                and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            # Enter is unclaimed on these faces — the option rows are plain widgets, so it
            # does not answer for the learner — and it is now theirs: press it, hear the word.
            self.play_word_prompt()
            event.accept()
            return True
        if (not self.answer_shown and self.choice_buttons and event.type() == QEvent.Type.KeyPress
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            index = event.key() - Qt.Key.Key_A
            if 0 <= index < len(self.choice_buttons):
                self.choice_buttons[index].click()
                event.accept()
                return True
        if (self.answer_shown and event.type() == QEvent.Type.KeyPress
                and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
                and event.key() == Qt.Key.Key_F):
            # 看回题目 lives on Shift+F since 2026-11-06: on the flipped-back front face the
            # bare letter was eaten here, so an f could never be typed into a spelling box.
            # The answer stays revealed as far as Anki is concerned; this only turns the card
            # over again.
            self.toggle_front()
            event.accept()
            return True
        if self.answer_shown and event.type() == QEvent.Type.KeyPress and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            if event.key() == Qt.Key.Key_P:
                self.review_requested.emit(self)
                event.accept()
                return True
            if self.showing_front:
                # Reading the prompt back is not a moment to rate it, so A–D and Enter stay
                # inert while the front is up.
                return super().eventFilter(watched, event)
            index = event.key() - Qt.Key.Key_A
            if 0 <= index < 4 and self.grade_with_letter(index):
                event.accept()
                return True
        if (self.answer_shown and event.type() == QEvent.Type.KeyPress
                and event.modifiers() == Qt.KeyboardModifier.NoModifier
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)):
            # Space is the same key as Enter here, and deliberately so: it used to fall
            # through to Qt and activate whatever button happened to hold focus, which on
            # one question type meant the speaker (measured 2026-11-05).
            # Reading the prompt back is not a moment to answer, so the look-back keeps both
            # keys inert and leaves Space to the letter boxes, where a 词组 may need one.
            if self.showing_front:
                return super().eventFilter(watched, event)
            if self.grading:
                event.accept()
                return True
            if self.enter_ease is not None:
                self.start_grade(self.enter_ease)
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        # The speaking card has no letter boxes and no choice buttons, so the dialog
        # itself receives keys: Enter means "I said it, show me", Space means "I could
        # not recall it". The event filter is only installed for choice modes, so this
        # cannot live there.
        if (self.question['mode'] == 'speaking' and not self.answer_shown
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.spoken_answer_button.click()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Space:
                self.spoken_unknown_button.click()
                event.accept()
                return
        super().keyPressEvent(event)

    def hide_front(self):
        """Fold the question face away, and remember exactly which widgets that was.

        Only widgets that were actually visible are recorded, so 看回题目 cannot resurrect a
        hint button that this question type never showed.
        """
        candidates = list(self.choice_buttons) + [
            getattr(self, 'prompt_label', None), getattr(self, 'question_label', None),
            getattr(self, 'question_block', None),
            getattr(self, 'meaning_heading', None), getattr(self, 'phonetic_label', None),
            getattr(self, 'judgment_label', None), getattr(self, 'spoken_answer_button', None),
            getattr(self, 'spoken_unknown_button', None), getattr(self, 'letter_scroll', None),
            getattr(self, 'example_hint_button', None),
            getattr(self, 'phonetic_hint_button', None), getattr(self, 'front_phonetic', None),
            getattr(self, 'meaning_hint_button', None), getattr(self, 'check_button', None),
            getattr(self, 'hint_button', None), getattr(self, 'answer_button', None)]
        self.front_widgets = [widget for widget in candidates if widget is not None and widget.isVisible()]
        for widget in self.front_widgets:
            widget.hide()

    def answer_widgets(self):
        """The answer face as a set, so it can be folded away in one move."""
        word_row = self.answer_word.parentWidget()
        return [widget for widget in (word_row, self.answer_scroll, self.result_label, self.status,
                                      self.grade_widget, self.book_chip) if widget is not None]

    def show_front_face(self, visible):
        """Look at the question again without un-revealing the answer.

        The answer stays revealed as far as Anki is concerned — this is a look, not a redo —
        so the rating row is hidden while the front is up: pressing A–D should not fire while
        the user is only reading the prompt back. Width never changes here; only the height
        follows the content, and the top edge stays where it was.
        """
        self.showing_front = visible
        for widget in self.front_widgets:
            widget.setVisible(visible)
        for widget in self.answer_widgets():
            widget.setVisible(not visible)
        if visible and self.answer_shown and self.answer_button is not None:
            # Look-back re-shows the question row, but 显示答案 answers a card that is already
            # answered -- it must not come back with the rest of the foot.
            self.answer_button.hide()
        self.fit_card_height()
        # Ask the window to paint the whole area again: the two faces do not cover the same
        # pixels, and whatever the other face drew has to be erased, not left as a ghost.
        self.card_window().update()

    def toggle_front(self):
        if not self.answer_shown or self.grading:
            return False
        self.show_front_face(not self.showing_front)
        return True

    def enter_review(self):
        """Show this card the way it was left: answer up, ratings gone.

        The look-back is a look. The counters are restored so the answer face reads the same
        as it did at the time, the word is not spoken again, and the rating row is replaced
        by the footer — pressing A–D on a card that is already scheduled would either be
        refused by Anki or, worse, silently re-answer it.
        """
        note = self.review_note or {}
        self.hint_uses = int(note.get('hint_uses') or 0)
        self.incorrect_letters = int(note.get('incorrect_letters') or 0)
        self.failed_attempts = int(note.get('failed_attempts') or 0)
        # The hint breakdown travels with the card, so a look-back reads the same
        # recommendation line it showed at the time.
        record = note.get('hint_record') or {}
        self.audio_hint_uses = int(record.get('audio_hints') or 0)
        self.other_hint_uses = int(record.get('other_hints') or 0)
        self.revealed_indices = set(record.get('revealed') or ())
        self.suppress_speech = True
        try:
            self.reveal(note.get('correct', True))
        finally:
            self.suppress_speech = False
        self.grade_widget.hide()
        self.later.hide()
        timing = '（用时 %.1f 秒）' % note['seconds'] if note.get('seconds') else ''
        self.status.setText('回看 · 这张已评分为「%s」%s，不会再排程；按 P 或 Esc 退出回看，按 B 看更早的一张。' %
                            (note.get('rating') or '已评分', timing))
        self.status.show()
        self.review_bar.show()
        self.fit_card_height()
        return True

    def letter_motion_allowed(self):
        """The per-keystroke hop is feedback while answering, so it stops once the answer is up."""
        return card_motion.hop_allowed(self.cfg) and not self.answer_shown

    def play_celebration(self, correct):
        """The badge for a spelling that earned one — never on a look-back or a wrong answer.

        Tier comes from `card_motion.tier_for`, which only ever answers for the typing card:
        a choice card answered in half a second is recognition, not spelling, and it must not
        be rewarded with confetti.
        """
        if self.review_note is not None or self.suppress_speech or not correct:
            return
        tier = tier_for(self.question['mode'], correct, self.incorrect_letters,
                        self.hint_uses, self.failed_attempts, self.answer_seconds)
        if not tier or not card_motion.celebration_allowed(self.cfg):
            return
        if self.celebration is None:
            self.celebration = motion_view.Celebration(self, self.cfg.get('review_theme', 'light'))
        word_row, rows = self.celebration_rows()
        self.celebration.play(tier, self.cfg, word_row=word_row, protected=rows)
        try:
            from . import log_runtime
            log_runtime('card motion: tier=%d word=%s' % (tier, self.question.get('word', '')))
        except Exception:
            pass

    def celebration_rows(self):
        """Where the word and the rating row really are, in the overlay's coordinates.

        Read from the widgets rather than remembered from any earlier layout pass: the whole
        point of the clearance rule is that these rows move with the content (a six-line
        释义 pushes the word down), so a number kept from last week's screenshot is exactly
        what got this wrong before.
        """
        def rect(widget):
            top_left = widget.mapTo(self, QPoint(0, 0))
            return QRect(top_left.x(), top_left.y(), widget.width(), widget.height())

        rows = []
        boxes = [box for box in getattr(self, 'letter_boxes', []) if box.isVisible()]
        if boxes:
            union = rect(boxes[0])
            for box in boxes[1:]:
                union = union.united(rect(box))
            rows.append(union)
        for widget in (getattr(self, 'answer_word', None), getattr(self, 'question_label', None)):
            if widget is not None and widget.isVisible():
                rows.append(rect(widget))
        grade = getattr(self, 'grade_widget', None)
        if grade is not None and grade.isVisible():
            rows.append(rect(grade))
        # The verdict line and the evidence line belong with the rating row: the celebration
        # is what happens *to* that answer, so it may not sit on the words that report it.
        # `windows-card-motion.py` 3c asserts exactly these three rows pixel by pixel.
        for widget in (getattr(self, 'result_label', None), getattr(self, 'status', None)):
            if widget is not None and widget.isVisible():
                rows.append(rect(widget))
        return (rows[0] if rows else None), rows

    def hideEvent(self, event):
        self.keyboard.restore()
        self.stop_box_pulse()
        # A celebration must not outlive the card it belongs to: the handover hides the old
        # card under the new one, and an overlay left visible is exactly the ghosting shape
        # AUDIT §9.32 recorded.
        if self.celebration is not None:
            self.celebration.stop()
        super().hideEvent(event)

    def reveal(self, correct):
        if self.answer_shown:
            return
        self.setUpdatesEnabled(False)
        self._flipping = True
        try:
            self.answer_shown = True
            self.last_correct = correct
            # Only the spelling card reports its hints by kind: 听一遍 is nearly free there,
            # a revealed letter is priced by position, and the other question types keep the
            # old blanket "a hint was used" rule until the user says otherwise.
            self.hint_record = (self.hint_components()
                                if self.question['mode'] == 'typing' else {})
            self.enter_ease = None if correct is None else suggested_ease(
                correct, self.hint_uses, self.incorrect_letters, self.failed_attempts,
                self.question['mode'], **self.hint_record)
            # The clock is evidence for the tooltip on the non-spelling modes; since E was
            # retired it no longer decides anything by itself.
            self.answer_seconds = None if self.shown_at is None else time.monotonic() - self.shown_at
            self.hide_front()
            shown = syllable_display(self.question['word'])
            self.answer_word.setText(shown)
            self.answer_word.setToolTip(
                self.question['word'] if shown == self.question['word']
                else '%s\n音节分段来源：Moby 音节词表；不代表词根词缀。' % self.question['word'])
            if self.book_chips:
                # Built at birth, so the card already knows how wide it has to be.
                self.book_chip.show()
            # The cloze asks for the headword, so the inflected form the sentence used has to
            # be shown here or the learner never sees why the blank was shorter.
            shown = self.question.get('cloze_shown') or ''
            if shown and shown.casefold() != self.question['word'].casefold():
                self.add_detail('例句中的形式', shown)
            if self.question.get('source_form', self.question['word']).casefold() != self.question['word'].casefold():
                self.add_detail('收录时的词形', self.question['source_form'])
            self.add_detail('解释', self.question['meaning'])
            for title, key in [('词根与词源', 'roots'), ('识记方法', 'mnemonic'), ('词语辨析', 'distinctions')]:
                if self.question.get(key):
                    self.add_detail(title, self.question[key])
            breakdown = morphology.breakdown(self.question['word'])
            if breakdown:
                self.add_detail('拆分记忆', breakdown)
            chunks = morphology.spelling_chunks(self.question['word'])
            # The syllable form is on the word now, so repeating it below is noise;
            # only the mechanical letter grouping still earns its own card.
            if chunks and chunks[0] != '音节分段':
                self.add_detail(chunks[0], ' · '.join(chunks[1]) + '\n按字母机械分组，不代表音节或词根词缀。')
            contrast = morphology.confusion(self.question['word'])
            if contrast:
                self.add_detail('易混辨析', contrast)
            self.show_relations()
            # 例句 is the tallest part of the answer, and the setting page can now switch it
            # off; 例句填空 keeps its sentence whatever the switch says.
            if show_examples(self.cfg, self.question['mode']):
                for title, source in [('例句', self.question.get('example', '')), ('权威例句', self.question.get('literature', ''))]:
                    groups = example_groups(source)
                    for index, text in enumerate(groups, 1):
                        is_literature = bool(literature_example_html(text) or re.match(r'^\s*文献例句\s*[:：]', text))
                        current_title = '文献例句' if is_literature else title
                        self.add_detail('%s %d' % (current_title, index) if len(groups) > 1 else current_title, text, audio=True)
                examples = spoken_examples(self.question.get('example', ''), self.question.get('literature', ''), 'all')
                if len(examples) > 1:
                    all_button = QPushButton('朗读全部例句')
                    all_button.setObjectName('secondary')
                    all_button.clicked.connect(lambda: self.speak_many(examples))
                    self.answer_layout.addWidget(all_button)
            self.result_label.setText('请根据回忆与发音自主评分' if correct is None else ('回答正确' if correct else '回答错误，已显示答案'))
            result_color = ('#aab9ff' if self.cfg.get('review_theme') == 'dark' else '#5668ca') if correct is None else (('#71e0b5' if correct else '#ff99a9') if self.cfg.get('review_theme') == 'dark' else ('#198765' if correct else '#bd4358'))
            self.result_label.setStyleSheet('color: %s;' % result_color)
            self.result_label.show()
            self.answer_scroll.show()
            self.force_again = correct is False
            for index, button in enumerate(self.grade_buttons, 1):
                button.setObjectName('suggest' if index == self.enter_ease else '')
                button.style().unpolish(button)
                button.style().polish(button)
            rating_name = {1: 'Again', 2: 'Hard', 3: 'Good', 4: 'Easy'}.get(self.enter_ease)
            if correct is None:
                self.status.setText('请听发音并选择评分；此题不会自动识别或上传语音。')
            elif not correct:
                self.status.setText('回答错误或已查看答案：按 A 记录并继续（回车同样）。')
            else:
                # One line for the decision, the whole accounting in its tooltip: the row
                # used to wrap to two lines and eat the card's height for counts like
                # 「检查失败 0 次」 that say nothing about this card.
                line, detail = answer_report(
                    self.hint_summary(), incorrect_letters=self.incorrect_letters,
                    failed_checks=self.failed_attempts, rating=rating_name,
                    seconds=self.answer_seconds,
                    show_seconds=self.question['mode'] != 'typing')
                self.status.setText(line)
                self.status.setToolTip(detail)
            self.grade_widget.show()
            if self.force_again:
                # A wrong answer may only record Again, then offers 继续学习; the other
                # three eases would invite a rating Anki is not allowed to take.
                self.grade_buttons[0].setProperty('gradeCaption', 'Again 并继续')
                self.grade_buttons[2].setProperty('gradeCaption', '继续学习')
                self.grade_buttons[1].hide()
                self.grade_buttons[3].hide()
            self.label_grade_buttons()
            # 「不评分，结束」 used to take a row of its own under the ratings; Escape and the
            # card menu still do it, and the space belongs to the explanations.
            self.later.hide()
            self.stop_box_pulse()
            # Still inside the disabled-updates block: the answer's own height is trimmed in
            # the same repaint, so the card never shows a tall window with an empty foot.
            self.fit_card_height()
            # ... and the row's own minimum is checked once it is on screen, so a short
            # estimate cuts a button rather than leaving it unread.
            self.ensure_row_fits()
            for widget in [self] + self.findChildren(QWidget):
                widget.installEventFilter(self)
        finally:
            self.setUpdatesEnabled(True)
        self.flip_finished()
        self.play_celebration(correct)
        speech = []
        if self.cfg.get('review_auto_word', True):
            speech.append(self.question['word'])
        mode = self.cfg.get('review_auto_example_mode', 'example' if self.cfg.get('review_auto_example', False) else 'first')
        speech.extend(spoken_examples(self.question.get('example', ''), self.question.get('literature', ''), mode))
        if any(speech) and not self.suppress_speech:
            self.speak_many(speech)

    def visible_grade_buttons(self):
        """The grade row as it actually stands. A wrong answer collapses it to two
        buttons, and then A and B have to mean those two rather than leave D dead."""
        return [button for button in self.grade_buttons if not button.isHidden()]

    def size_grade_button(self, button):
        """Give each rating button its own floor, so the row cannot cut the longest label.

        `size_rating_button` lets each button keep its own width, and equal shares were
        wrong when one caption is longer than the rest: "E. Mastered" reached the user as
        ". Mastere" while "A. Again" still had room to spare. The floor is the stylesheet's
        own box — 12px padding plus a 1px border on each side — around the text measured
        with **the button's own font**: the dialog's font is not the one the stylesheet
        paints with, and that difference is what made every estimate come up short on the
        real machine while the offscreen checks stayed green.
        """
        button.ensurePolished()
        button.setMinimumWidth(QFontMetrics(button.font()).horizontalAdvance(button.text()) + 26)

    def row_demand(self):
        """The width the rating row truly needs, measured with the fonts that paint it.

        Each button is as wide as the larger of its own text box and its size hint — the
        hint carries the style's minimum button width, which is what the row really asks for
        and what an `Ignored` policy hid from the layout's arithmetic.
        """
        buttons = [button for button in self.visible_grade_buttons()
                   if button.text() and not button.isHidden()]
        if not buttons:
            return 0
        row = self.grade_widget.layout()
        width = sum(max(button.sizeHint().width(),
                        QFontMetrics(button.font()).horizontalAdvance(button.text()) + 26)
                    for button in buttons) + row.spacing() * max(0, len(buttons) - 1)
        margins = row.contentsMargins()
        return width + margins.left() + margins.right()

    def label_grade_buttons(self):
        # The key sits in front of the word, the way Anki's own review buttons read,
        # because the row is the only place the user learns which key does what. The
        # letters name the *visible* buttons: a wrong answer collapses the row to two.
        for letter, button in zip('ABCD', self.visible_grade_buttons()):
            caption = str(button.property('gradeCaption'))
            button.setText('%s. %s' % (letter, caption))
            button.setToolTip('按 %s 选择「%s」' % (letter, caption))
            self.size_grade_button(button)

    def grade_with_letter(self, index):
        buttons = self.visible_grade_buttons()
        if index < len(buttons):
            buttons[index].click()
            return True
        return False

    def start_grade(self, ease):
        if self.grading:
            return
        # Fill in the button the user actually picked before anything else changes, so a
        # keyboard rating is visibly theirs rather than the card's pre-selection. Match
        # on the requested ease, not the recorded one: a wrong answer forces Again no
        # matter which of the two collapsed buttons was pressed.
        chosen = next((button for button in self.grade_buttons
                       if button.property('gradeEase') == ease and not button.isHidden()), None)
        for button in self.grade_buttons:
            button.setObjectName('chosen' if button is chosen else '')
            button.style().unpolish(button)
            button.style().polish(button)
        self.grading = True
        if self.force_again:
            ease = 1
        for button in self.grade_buttons:
            button.setEnabled(False)
        self.later.setEnabled(False)
        self.grade(self, ease)

    def flip_finished(self):
        self._flipping = False
        if self._relations_dirty and self.answer_shown:
            self._relations_dirty = False
            self.show_relations()

    def update_relations(self, relations):
        self.relations.update(relations)
        if self._flipping:
            self._relations_dirty = True
            return
        if self.answer_shown:
            self.show_relations()

    def show_relations(self):
        for key, title in (('similar', '形近词（拼写相似）'), ('antonyms', '反义词（注意义项）'), ('synonyms', '近义词（注意义项）')):
            value = self.relations.get(key, '')
            if not value:
                continue
            if key not in self.relation_labels:
                card, label = self.make_detail(title, value)
                self.answer_labels.append(label)
                self.answer_layout.addWidget(card)
                self.relation_labels[key] = label
                self.relations_shown.add(key)
            else:
                label = self.relation_labels[key]
                self.example_labels = [(widget, value if widget is label else text, heading)
                                       for widget, text, heading in self.example_labels]
                self._render_example(label, value, title)

    def grade_result(self, error):
        self.later.setEnabled(True)
        if error:
            self.status.setText('未能确认评分已保存：%s。请在 Anki 中检查后再复习。' % error)
            # The row was folded away when the answer appeared; an unconfirmed rating needs a
            # visible way out, so this one case brings it back with a different meaning.
            self.later.show()
            self.later.setText('跳过并继续（本次不重试评分）')
            self.later.clicked.disconnect()
            self.later.clicked.connect(self.skip_after_error)
            return
        self.completed = True
        self.status.setText('本组结束。')
        self.accept()

    def skip_after_error(self):
        self.skipped = True
        self.accept()


GROUP_BREAK_SECONDS = 3


class GroupBreakDialog(QWidget):
    """The pause between groups, shown inside the card window rather than beside it.

    A finished group used to roll straight into the next one, so "练完一组" quietly became an
    open-ended session; the countdown puts the decision in front of the user and does nothing
    if they walk away. It used to be a second window at the card's geometry, which read as two
    unrelated popups — now it is a panel that covers the card the next group is about to
    replace, so the switch is one window the whole time.
    """

    finished = pyqtSignal(int)

    def __init__(self, summary, cfg, geometry=None, parent=None):
        super().__init__(parent)
        self.remaining = GROUP_BREAK_SECONDS
        self.cfg = cfg or {}
        self.setObjectName('breakCard')
        # A plain QWidget ignores the stylesheet's background without this, and the panel has
        # to be opaque: the card it covers is still there underneath.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if parent is None:
            # Standalone (the way the tests and any older caller build it) keeps a window.
            self.setWindowTitle('单词随身复习')
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(popup_style(self.cfg))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if geometry is not None:
            self.setGeometry(geometry)
        else:
            self.resize(510, 320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(10)
        layout.addWidget(_plain_label('VOCABULARY  ·  本组结束', 'eyebrow'), 0, Qt.AlignmentFlag.AlignHCenter)
        summary_label = _plain_label(summary, 'status')
        summary_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(summary_label, 0, Qt.AlignmentFlag.AlignHCenter)
        self.count_label = _plain_label(str(self.remaining), 'question')
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.count_label, 1)
        self.hint = _plain_label('按 Enter 进入下一组学习', 'breakHint')
        self.hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.hint, 0, Qt.AlignmentFlag.AlignHCenter)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.setFocus()
        self.timer.start()

    def accept(self):
        self.finished.emit(int(QDialog.DialogCode.Accepted))

    def reject(self):
        self.finished.emit(int(QDialog.DialogCode.Rejected))

    def _tick(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self.timer.stop()
            self.reject()
            return
        self.count_label.setText(str(self.remaining))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.timer.stop()
            self.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.timer.stop()
            self.reject()
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.timer.stop()
            self.accept()
            return
        super().mouseReleaseEvent(event)


class WordLookupDialog(QDialog):
    loaded = pyqtSignal(object, object)

    def __init__(self, word, parent, cfg, api, dictionary, add_word):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.WindowStaysOnTopHint)
        enable_click_away(self)
        self.word, self.cfg, self.api, self.dictionary, self.add_word = word, cfg, api, dictionary, add_word
        self.info, self.note_id = {}, None
        self.setWindowTitle('单词释义')
        self.setStyleSheet(popup_style(self.cfg))
        self.resize(420, 320)
        layout = QVBoxLayout(self)
        layout.addWidget(_plain_label(word, 'question'))
        self.detail = _plain_label('正在查询…', 'cardText')
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(self.detail)
        layout.addWidget(area)
        buttons = QHBoxLayout()
        self.add_button = QPushButton('添加到单词本')
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self.add_to_collection)
        buttons.addWidget(self.add_button)
        self.browse_button = QPushButton('查看详细单词卡片')
        self.browse_button.setEnabled(False)
        self.browse_button.clicked.connect(self.browse)
        buttons.addWidget(self.browse_button)
        layout.addLayout(buttons)
        self.loaded.connect(self.on_loaded)
        threading.Thread(target=self.lookup, daemon=True).start()

    def lookup(self):
        try:
            escaped = self.word.replace('\\', '\\\\').replace('"', '\\"')
            ids = self.api('findNotes', {'query': '"%s"' % escaped}) or []
            notes = self.api('notesInfo', {'notes': ids}) if ids else []
            note = next((n for n in notes if clean_text(n.get('fields', {}).get(self.cfg['front_field'], {}).get('value', '')).casefold() == self.word.casefold()), None)
            if note:
                fields = note.get('fields', {})
                info = {'meaning': clean_detail(fields.get(self.cfg['back_field'], {}).get('value', ''), '解释'),
                        'phonetic': clean_detail(fields.get('音标', {}).get('value', '')),
                        'examples': clean_detail(fields.get('例句', {}).get('value', ''), '例句'),
                        'authority': clean_detail(fields.get('权威例句', {}).get('value', ''), '权威例句'),
                        'synonyms': clean_detail(fields.get('近义词', {}).get('value', '')),
                        'roots': clean_detail(fields.get('词根', {}).get('value', '')),
                        'note_id': note.get('noteId')}
            else:
                info = self.dictionary(self.word) if self.dictionary else {}
            self.loaded.emit(info, None)
        except Exception as error:
            self.loaded.emit({}, str(error))

    def on_loaded(self, info, error):
        self.info = info or {}
        self.note_id = self.info.get('note_id')
        pieces = []
        for title, key in [('音标', 'phonetic'), ('解释', 'meaning'), ('例句', 'examples'), ('近义词', 'synonyms'), ('词根', 'roots')]:
            if self.info.get(key):
                pieces.append('【%s】\n%s' % (title, self.info[key]))
        self.detail.setText('\n\n'.join(pieces) if pieces else ('查询失败：%s' % error if error else '没有找到释义。'))
        self.add_button.setEnabled(self.add_word is not None)
        self.browse_button.setEnabled(bool(self.note_id))

    def add_to_collection(self):
        if self.add_word:
            self.add_word(self.word, self.info)
            self.add_button.setEnabled(False)
            self.add_button.setText('正在添加…')

    def browse(self):
        if self.note_id:
            threading.Thread(target=lambda: self.api('guiBrowse', {'query': 'nid:%s' % self.note_id}), daemon=True).start()


class _Signals(QObject):
    prepared = pyqtSignal(object, object, int, bool)
    saved = pyqtSignal(object, int, object)
    graded = pyqtSignal(object, object, int, object)
    known = pyqtSignal(object, object, int)
    relations = pyqtSignal(object, object, int)
    example = pyqtSignal(object, object, object, int)


class DesktopReviewController:
    def __init__(self, settings, api, feedback, log):
        self.settings, self.api, self.feedback, self.log = settings, api, feedback, log
        self.signals = _Signals()
        self.signals.prepared.connect(self._prepared)
        self.signals.saved.connect(self._saved)
        self.signals.graded.connect(self._graded)
        self.signals.known.connect(self._known_ready)
        self.signals.relations.connect(self._relations_ready)
        self.signals.example.connect(self._example_ready)
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._tick)
        self.dialog = None
        self.review_host = None
        self.busy = False
        self.generation = 0
        self.regular_deadline = None
        self.session_seen = set()
        self.session_words = set()
        self.recent_words = {}
        self.capture_lookup_cache = {}
        self.session_target = 1
        self.prepared_next = None
        self.prefetched = None
        self.prefetch_ready = None
        self.break_dialog = None
        self.pending_group = None
        # 回看上一张: the last few cards the user actually answered, the card we stepped
        # away from, and how far back the look-back has walked.
        self.history = []
        self.paused = None
        self.review_index = None
        self.HISTORY_LIMIT = 10
        self.open_settings = None
        self.dictionary = None
        self.add_word = None
        self.lookup_dialogs = []

    def start(self, *_args):
        if mw.col is not None:
            self.log('Anki scheduler: %s' % ('FSRS' if mw.col.get_config('fsrs', False) else 'SM-2'))
        self.schedule(reset=True)

    def schedule(self, reset=False):
        self.timer.stop()
        cfg = self.settings()
        if cfg.get('review_enabled', True):
            minutes = max(5, min(240, int(cfg.get('review_interval_minutes', 30))))
            now = time.monotonic()
            if reset or self.regular_deadline is None:
                self.regular_deadline = now + minutes * 60
            delay = next_check_delay(now, self.regular_deadline, cfg.get('review_smart', True))
            if cfg.get('review_windows_enabled'):
                wait = window_wait(datetime.datetime.now(), cfg.get('review_windows', []))
                if wait is None:
                    self.log('review time windows invalid')
                    return
                delay = max(delay, wait)
            self.timer.start(max(1000, int(delay * 1000)))
            self.log('review check scheduled: %d seconds' % delay)

    def _tick(self):
        cfg = self.settings()
        if cfg.get('review_windows_enabled') and window_wait(datetime.datetime.now(), cfg.get('review_windows', [])) != 0:
            self.schedule()
            return
        due_only = bool(cfg.get('review_smart', True) and
                        self.regular_deadline and time.monotonic() < self.regular_deadline)
        self.show_next(False, due_only)

    def _current_reviewer_card(self):
        if mw.state != 'review':
            return None
        try:
            card = mw.reviewer.card
            return card.id if card else None
        except Exception:
            return None

    def _reviewer_is_foreground(self):
        return mw.state == 'review' and mw.isActiveWindow() and not mw.isMinimized()

    def _next_result(self, cfg, completed, current_target):
        """Plan, target and the next card for one step of the session.

        The plan is read before the current rating lands, which is why the remaining
        count subtracts the card in flight and why prepare_question is told to treat
        one deck slot as already spent.
        """
        current_plan = None
        target = current_target
        if cfg.get('review_plan_mode') == 'daily':
            try:
                current_plan = collection_plan(self.api, cfg)
                target = updated_session_target(completed, current_plan)
            except Exception as error:
                self.log('review plan refresh failed: %s' % type(error).__name__)
        elif cfg.get('review_deadline') or cfg.get('review_daily_goal'):
            try:
                current_plan = collection_plan(self.api, cfg)
            except Exception as error:
                self.log('review plan refresh failed: %s' % type(error).__name__)
        new_group = completed >= target
        if new_group:
            target = session_batch_size(cfg, current_plan, manual=True)
        limits_new = plan_limits_new(cfg)
        try:
            next_question = prepare_question(self.api, cfg, cfg.get('review_mode', 'mixed'),
                                             due_only=bool(limits_new and current_plan is not None and
                                                           current_plan['new_remaining'] <= 0))
            if next_question:
                remaining = today_remaining(current_plan) if current_plan else None
                next_question['_today_remaining'] = max(0, remaining - 1) if remaining is not None else None
                # Cards inside a session arrive through here, not through show_next, so
                # the eyebrow's 已学/总数 has to be stamped on this path too.
                try:
                    next_question['_book_progress'] = book_progress(self.api, cfg)
                except Exception as error:
                    self.log('book progress unavailable: %s' % type(error).__name__)
            reason = None
            if not next_question:
                reason = end_of_session_reason(
                    current_plan, limits_new, book_label=selection_summary(cfg),
                    elsewhere_due=due_outside_book(self.api, cfg),
                    mode_labels=selected_mode_labels(cfg),
                    suspended=book_suspended(self.api, cfg))
                self.log('end of session: %s' % reason)
            return (next_question, None, target, new_group, reason)
        except Exception as error:
            self.log('review preparation failed: %s' % type(error).__name__)
            return (None, str(error), target, False, None)

    def _start_prefetch(self, dialog):
        """Choose the next card while the user is still reading this one.

        Picking a card costs several AnkiConnect round trips. Doing that now instead of
        after the rating is what makes the flip instant. The card on screen is excluded
        and its deck slot is already counted as spent, so the prefetched card is the one
        the rating path would have chosen anyway.
        """
        question = dialog.question
        cfg = dict(self.settings())
        cfg['_review_exclude_card'] = self._current_reviewer_card()
        cfg['_review_exclude_cards'] = self.session_seen | {question['card_id']}
        cfg['_review_exclude_words'] = self.session_words | {str(question.get('word', '')).casefold()}
        cfg['_review_recent_words'] = set(self.recent_words)
        cfg['_review_group'] = (len(cfg['_review_exclude_cards']), self.session_target)
        kind_new = question.get('kind') == 'new'
        cfg['_review_inflight_new'] = 1 if kind_new else 0
        cfg['_review_inflight_due'] = 0 if kind_new else 1
        cfg['_review_prefetch'] = True
        completed = len(self.session_seen) + 1
        current_target = self.session_target
        generation = self.generation
        key = (generation, frozenset(cfg['_review_exclude_cards']), current_target)
        ready = threading.Event()
        self.prefetch_ready = ready

        def work():
            result = self._next_result(cfg, completed, current_target)
            if generation == self.generation and self.dialog is dialog and result[0]:
                self.prefetched = (key, result)
            ready.set()
        threading.Thread(target=work, daemon=True).start()

    def show_next(self, manual=True, due_only=False, continuation=False):
        if self.busy or self.dialog:
            if manual:
                self.feedback('复习卡正在准备或已经显示。')
            if not manual:
                self.schedule(reset=True)
            return
        if mw.col is None or self._reviewer_is_foreground():
            if manual:
                self.feedback('请先打开 Anki 账户，并结束当前 Anki 复习。')
            self.schedule(reset=True)
            return
        self.timer.stop()
        cfg = dict(self.settings())
        if not continuation:
            self.session_seen = set()
            self.session_words = set()
            self.capture_lookup_cache.clear()
            self.prefetched = None
            self.prefetch_ready = None
            self.session_target = session_batch_size(cfg)
        cfg['_review_exclude_card'] = self._current_reviewer_card()
        cfg['_capture_lookup_cache'] = self.capture_lookup_cache
        cfg['_review_exclude_cards'] = self.session_seen.copy()
        cfg['_review_exclude_words'] = self.session_words.copy()
        now = time.monotonic()
        self.recent_words = {word: timestamp for word, timestamp in self.recent_words.items() if now - timestamp < 1800}
        cfg['_review_recent_words'] = set(self.recent_words)
        cfg['_review_group'] = (len(cfg['_review_exclude_cards']), self.session_target)
        generation = self.generation
        self.busy = True

        def work():
            try:
                plan = None
                if not continuation and cfg.get('review_plan_mode') == 'daily':
                    plan = collection_plan(self.api, cfg)
                    self.session_target = session_batch_size(cfg, plan, manual)
                    if not self.session_target:
                        self.signals.prepared.emit(None, None, generation, manual)
                        return
                # Where this card sits in the group, so the mixed new/due order can be
                # applied per slot (learner 2026-11-06: 每组混排固定比例的旧词). Stamped here
                # rather than above because `session_target` can still change with the plan.
                cfg['_review_group'] = (len(cfg['_review_exclude_cards']), self.session_target)
                limit_to_due = due_only or (plan is not None and plan['new_remaining'] <= 0 and not manual)
                question = prepare_question(self.api, cfg, cfg.get('review_mode', 'mixed'), due_only=limit_to_due)
                reason = None
                if question:
                    # The eyebrow says how far this book has been studied. Counting in
                    # the worker keeps the two findCards queries off the UI thread.
                    try:
                        question['_book_progress'] = book_progress(self.api, cfg)
                    except Exception as error:
                        self.log('book progress unavailable: %s' % type(error).__name__)
                    if plan is None and (cfg.get('review_plan_mode') == 'daily' or cfg.get('review_deadline') or cfg.get('review_daily_goal')):
                        try:
                            plan = collection_plan(self.api, cfg)
                        except Exception as error:
                            self.log('review plan refresh failed: %s' % type(error).__name__)
                    question['_today_remaining'] = today_remaining(plan) if plan else None
                elif manual:
                    reason = self._no_card_reason(cfg, plan, due_only)
                self.signals.prepared.emit(question, reason, generation, manual)
            except Exception as error:
                self.log('review preparation failed: %s' % type(error).__name__)
                self.signals.prepared.emit(None, str(error), generation, manual)

        threading.Thread(target=work, daemon=True).start()

    def _no_card_reason(self, cfg, plan, due_only):
        """Name the real reason the manual button found nothing.

        The plan's batch is the deadline pace, not what Anki will release: a deck's
        daily new limit can be spent while thousands of new words remain in the book.
        Saying that plainly is more useful than a toast that fits every cause.
        """
        try:
            new_now, due_now = book_availability(self.api, cfg)
        except Exception as error:
            self.log('book availability check failed: %s' % type(error).__name__)
            return None
        name = book_label(cfg) or '这本词书'
        if due_only:
            if due_now:
                return ('「%s」还有 %d 张到期卡，但当前题型凑不出题目；到设置里多勾一种题型试试。' % (name, due_now))
            return '「%s」现在没有到期复习卡。' % name
        if not new_now and not due_now:
            remaining = int((plan or {}).get('remaining_new_total', 0))
            left = '（书里还剩 %d 张新词）' % remaining if remaining else ''
            return ('「%s」今天没有可学的卡：Anki 的每日新词额度已用完%s，也没有到期复习。'
                    '明天再来，或在 Anki 牌组选项里把新词上限调高。' % (name, left))
        return ('「%s」还有 %d 张新词、%d 张到期卡，但当前题型凑不出题目；到设置里多勾一种题型试试。'
                % (name, new_now, due_now))

    def _prepared(self, question, error, generation, manual, previous=None):
        if generation != self.generation:
            return
        self.busy = False
        if not manual and not self.settings().get('review_enabled', True):
            return
        if error or not question:
            if manual:
                message = str(error) if error else ''
                if message.startswith('「'):
                    self.feedback(message)
                else:
                    self.feedback('复习暂不可用：%s' % message if message else
                                  '没有符合已选题型的可复习词，或今天的学习额度已用完。')
            if previous is None:
                self.schedule(reset=bool(error) or not self.regular_deadline or time.monotonic() >= self.regular_deadline)
            return
        if mw.col is None or self._reviewer_is_foreground() or self._current_reviewer_card() == question['card_id']:
            if previous is None:
                self.schedule(reset=True)
            return
        new_dialog = None
        connected = False
        try:
            cfg = self.settings()
            cfg['_book_progress'] = question.get('_book_progress') or (0, 0)
            progress = '%d / %d' % (len(self.session_seen) + 1, self.session_target)
            self.dialog = ReviewDialog(question, cfg.get('review_position', 'corner'), self._grade, cfg, progress, self.open_settings, self.open_word_lookup, self._lookup_example)
            new_dialog = self.dialog
            if previous is not None:
                host = self.review_host or previous
                self.dialog._embedded = True
                self.dialog._handoff_geometry = host.geometry()
                self.dialog.setMinimumWidth(0)
                self.dialog.setParent(host, Qt.WindowType.Widget)
                self.dialog.setGeometry(host.rect())
                # Registered before any resize: the host re-fills its embedded card from
                # `resizeEvent`, and a resize that happens first leaves the card at the old
                # (taller) geometry inside a shorter window — a clipped foot, which is the
                # same class of bug §9.32 was about.
                host._embedded_dialog = self.dialog
            self.dialog.finished.connect(self._closed)
            self.dialog.review_requested.connect(lambda _dialog=None: self.review_previous())
            self.dialog.review_back_requested.connect(lambda _dialog=None: self.review_back())
            connected = True
            self.dialog.show()
            self.dialog.raise_()
            # Height follows the content on EVERY card, not only on a handover. This used to
            # be `if previous is not None`, which left the session opener in the fixed
            # 510x570 birth size: a live capture on 2026-11-06 showed a 526x609 window whose
            # own content needed 474 -- about 96 px of dead band that no later card of the
            # session had. It is done here rather than in the dialog's showEvent on purpose:
            # fitting at show time also resized the standalone dialogs the geometry checks
            # build themselves, and one of them died in native code.
            self.dialog.fit_card_height()
            if previous is None:
                # The opener is its own window, so the shrink has to be re-anchored; a card
                # handed over to a host is repositioned by the host's own resize path.
                self.dialog.position_window()
                self.review_host = self.dialog
            # Which queue this card came from and where it sat in the group — without this,
            # "did the mixed order actually fire?" is only answerable by watching the card.
            self.log('review popup displayed: queue=%s slot=%d/%d' % (
                question['kind'], len(self.session_seen), self.session_target))
            self._start_prefetch(self.dialog)
            self._lookup_known_words(self.dialog, cfg)
            self._lookup_relations(self.dialog, dict(cfg))
            if previous is not None:
                # The new card only paints over the host; the outgoing card's widgets
                # stayed live underneath, so overlapping pixels hit-tested to them and
                # the window looked frozen. Hide everything that is not the new card.
                for widget in host.findChildren(QWidget):
                    if widget is not self.dialog and not self.dialog.isAncestorOf(widget):
                        widget.hide()
            return True
        except Exception as error:
            self.dialog = previous
            if new_dialog is not None:
                if connected:
                    new_dialog.finished.disconnect(self._closed)
                new_dialog.close()
            self.log('review display failed: %s' % type(error).__name__)
            self.feedback('复习窗口显示失败，请检查插件日志。')
            if previous is None:
                self.schedule(reset=True)

    def open_word_lookup(self, word, parent):
        dialog = WordLookupDialog(word, parent, dict(self.settings()), self.api, self.dictionary, self.add_word)
        self.lookup_dialogs.append(dialog)
        dialog.finished.connect(lambda _result: self.lookup_dialogs.remove(dialog) if dialog in self.lookup_dialogs else None)
        dialog.show()
        dialog.raise_()

    def _lookup_known_words(self, dialog, cfg):
        if cfg.get('review_known_style', 'underline') == 'none':
            return
        raw = dialog.question.get('example', '') + '\n' + dialog.question.get('literature', '')
        words = list(dict.fromkeys(word.casefold() for word in re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", raw)))
        if not words:
            return
        generation = self.generation
        def work():
            try:
                field = cfg['front_field'].replace('\\', '\\\\').replace('"', '\\"')
                known = set()
                for start in range(0, len(words), 100):
                    if generation != self.generation or self.dialog is not dialog:
                        return
                    actions = [{'action': 'findNotes', 'params': {'query': '"%s:re:^%s$"' % (field, re.escape(word))}} for word in words[start:start + 100]]
                    results = self.api('multi', {'actions': actions}) or []
                    ids = list(dict.fromkeys(note for group in results if isinstance(group, list) for note in group))
                    notes = self.api('notesInfo', {'notes': ids}) if ids else []
                    known.update(clean_text(n.get('fields', {}).get(cfg['front_field'], {}).get('value', '')).casefold() for n in notes)
                    self.signals.known.emit(dialog, set(known), generation)
            except Exception as error:
                self.log('example word marking unavailable: %s' % type(error).__name__)
        threading.Thread(target=work, daemon=True).start()

    def _known_ready(self, dialog, words, generation):
        if generation == self.generation and self.dialog is dialog:
            dialog.update_known_words(words)

    def _lookup_relations(self, dialog, cfg):
        generation, word = self.generation, dialog.question['word']
        def work():
            groups = {key: word_relations.candidate_words(dialog.question.get(field, ''), word)
                      for key, field in (('similar', 'similar_words'), ('antonyms', 'antonyms'), ('synonyms', 'synonyms'))}
            try:
                if not groups['similar']:
                    groups['similar'] = word_relations.similar_words(word, limit=30)
                if not groups['antonyms'] or not groups['synonyms']:
                    data = word_relations.fetch_relations(word)
                    for key in ('synonyms', 'antonyms'):
                        if not groups[key]:
                            groups[key] = list(dict.fromkeys(item for _pos, item in data.get(key, [])))
            except Exception as error:
                self.log('word relation lookup unavailable: %s' % type(error).__name__)
            words = list(dict.fromkeys(item for group in groups.values() for item in group))
            meanings, preferred = {}, set()
            try:
                decks = self.api('deckNames', {}) or []
                exam_decks = [name for name in decks if re.search(r'四六级|四级|六级|\bCET(?:4|6)?\b', name, re.I)]
                field = cfg['front_field'].replace('\\', '\\\\').replace('"', '\\"')
                def query(item):
                    return '"%s:re:^%s$"' % (field, re.escape(item))
                actions = [{'action': 'findNotes', 'params': {'query': query(item)}} for item in words]
                results = self.api('multi', {'actions': actions}) or []
                ids = list(dict.fromkeys(note for found in results if isinstance(found, list) for note in found))
                notes = self.api('notesInfo', {'notes': ids}) if ids else []
                for note in notes:
                    fields = note.get('fields', {})
                    front = clean_text(fields.get(cfg['front_field'], {}).get('value', '')).casefold()
                    back = clean_detail(fields.get(cfg['back_field'], {}).get('value', ''), '解释')
                    if front and back:
                        meanings.setdefault(front, word_relations.brief_meaning(back))
                for deck in exam_decks:
                    escaped = deck.replace('\\', '\\\\').replace('"', '\\"')
                    actions = [{'action': 'findNotes', 'params': {'query': 'deck:"%s" %s' % (escaped, query(item))}} for item in words]
                    matches = self.api('multi', {'actions': actions}) or []
                    preferred.update(item.casefold() for item, found in zip(words, matches) if isinstance(found, list) and found)
            except Exception as error:
                self.log('related word local lookup unavailable: %s' % type(error).__name__)
            selected = {key: word_relations.select_candidates(items, preferred) for key, items in groups.items()}
            def publish():
                values = {key: '\n'.join(item + (' — ' + meanings[item.casefold()] if meanings.get(item.casefold()) else '')
                                          for item in items) for key, items in selected.items()}
                self.signals.relations.emit(dialog, values, generation)
            publish()
            missing = list(dict.fromkeys(item for items in selected.values() for item in items if not meanings.get(item.casefold())))
            if self.dictionary and missing:
                with ThreadPoolExecutor(max_workers=5) as pool:
                    pending = {pool.submit(self.dictionary, item): item for item in missing}
                    for future in as_completed(pending):
                        if generation != self.generation or self.dialog is not dialog:
                            break
                        try:
                            meaning = word_relations.brief_meaning(future.result().get('meaning', ''))
                            if meaning:
                                meanings[pending[future].casefold()] = meaning
                                publish()
                        except Exception:
                            pass
        threading.Thread(target=work, daemon=True).start()

    def _relations_ready(self, dialog, values, generation):
        if generation == self.generation and self.dialog is dialog:
            dialog.update_relations(values)

    def _lookup_example(self, dialog):
        generation, word = self.generation, dialog.question['word']
        def work():
            try:
                info = self.dictionary(word) if self.dictionary else {}
                groups = example_groups(info.get('examples', '')) + example_groups(info.get('authority', ''))
                group = next((item for item in groups if masked_example(item, word)), None)
                self.signals.example.emit(dialog, group, None, generation)
            except Exception as error:
                self.signals.example.emit(dialog, None, str(error), generation)
        threading.Thread(target=work, daemon=True).start()

    def _example_ready(self, dialog, group, error, generation):
        if generation != self.generation or self.dialog is not dialog or dialog.answer_shown:
            return
        if group:
            dialog.show_example_hint(group)
        else:
            dialog.example_hint_button.setEnabled(True)
            dialog.status.setText('例句查询失败，请稍后重试。' if error else '没有找到包含该词的例句。')

    def _closed(self, _result):
        stop_speech()
        dialog = self.dialog
        self.dialog = None
        host, self.review_host = self.review_host, None
        if host is not None and host is not dialog:
            host.finished.disconnect(self._host_closed)
            host.reject()
        if dialog and (dialog.completed or dialog.skipped):
            self._record_review(dialog)
            if len(self.session_seen) < self.session_target:
                if self.prepared_next is not None:
                    question, error = self.prepared_next
                    self.prepared_next = None
                    self._prepared(question, error, self.generation, False)
                    return
                self.show_next(False, continuation=True)
                return
        if self.session_seen and getattr(mw, 'state', None) == 'deckBrowser':
            try:
                mw.deckBrowser.refresh()
            except Exception as error:
                self.log('study dashboard refresh failed: %s' % type(error).__name__)
        self.schedule(reset=True)

    def card_on_screen(self):
        """Whether a study window is really up, rather than merely still referenced.

        The close filter hides Anki's main window while a card is on screen, so a stale
        reference must not answer for one: it was seen leaving an Anki with no window at
        all, which nothing on screen can close any more.
        """
        for widget in (self.dialog, self.review_host, self.break_dialog):
            if widget is None:
                continue
            try:
                if widget.isVisible():
                    return True
            except RuntimeError:
                continue        # the Qt object is already gone; only the reference remains
        return False

    def _host_closed(self, _result):
        dialog = self.dialog
        self.review_host = None
        if dialog is not None:
            dialog.finished.disconnect(self._closed)
            dialog.reject()
            self._closed(_result)

    def _record_review(self, dialog):
        self.session_seen.add(dialog.question['card_id'])
        word = dialog.question['word'].casefold()
        self.session_words.add(word)
        if dialog.completed:
            self.recent_words[word] = time.monotonic()

    def remember(self, dialog, ease, rating=None):
        """Keep an answered card so 回看上一张 can show it again.

        Only what the card asked and what the user made of it — nothing here lets a
        look-back reach the scheduler, and the list is capped so a long session cannot grow.
        """
        self.history.append({'question': dict(dialog.question), 'ease': int(ease),
                             'rating': rating or EASE_NAMES.get(int(ease), str(ease)),
                             'correct': getattr(dialog, 'last_correct', True),
                             'hint_uses': getattr(dialog, 'hint_uses', 0),
                             'incorrect_letters': getattr(dialog, 'incorrect_letters', 0),
                             'failed_attempts': getattr(dialog, 'failed_attempts', 0),
                             'hint_record': dict(getattr(dialog, 'hint_record', None) or {}),
                             'seconds': getattr(dialog, 'answer_seconds', None)})
        del self.history[:-self.HISTORY_LIMIT]

    def review_previous(self):
        """Step back over the cards already answered, without losing this one."""
        if self.busy or not self.history:
            return False
        if self.review_index is None:
            if self.dialog is None:
                return False
            self.paused = self.dialog
            self.review_index = len(self.history) + 1
        return self.show_review(min(self.review_index - 1, len(self.history)))

    def review_back(self):
        if self.review_index is None or self.review_index <= 1:
            return False
        return self.show_review(self.review_index - 1)

    def show_review(self, index):
        if index < 1 or index > len(self.history):
            return False
        entry = self.history[index - 1]
        self.review_index = index
        outgoing = self.dialog
        cfg = dict(self.settings())
        dialog = ReviewDialog(entry['question'], cfg.get('review_position', 'corner'),
                              lambda *_a: None, cfg, '回看 %d / %d' % (index, len(self.history)),
                              self.open_settings, self.open_word_lookup, self._lookup_example)
        dialog.review_note = entry
        dialog.review_requested.connect(lambda _d=None: self.exit_review())
        dialog.review_back_requested.connect(lambda _d=None: self.review_back())
        dialog.finished.connect(self._review_closed)
        if outgoing is not None:
            dialog.setGeometry(outgoing.geometry())
            outgoing.hide()
            if getattr(outgoing, 'review_note', None) is not None:
                # Walking further back closes the look-back we came from; the disconnect
                # first, or its `finished` would end the whole review.
                try:
                    outgoing.finished.disconnect(self._review_closed)
                except Exception:
                    pass
                outgoing.close()
        self.dialog = dialog
        dialog.show()
        dialog.enter_review()
        dialog.raise_()
        self.log('review look-back opened: card %s (%d/%d)' % (
            entry['question']['card_id'], index, len(self.history)))
        return True

    def exit_review(self):
        if self.review_index is None:
            return False
        looking = self.dialog
        self.review_index = None
        self.dialog = self.paused
        self.paused = None
        if looking is not None:
            try:
                looking.finished.disconnect(self._review_closed)
            except Exception:
                pass
            looking.close()
        if self.dialog is not None:
            self.dialog.show()
            self.dialog.raise_()
        self.log('review look-back closed')
        return True

    def _review_closed(self, _result):
        self.exit_review()

    def _grade(self, dialog, ease):
        if mw.col is None or mw.state == 'review':
            dialog.grade_result('Anki 正在复习或账户已关闭')
            return
        # Kept for 回看上一张 the moment the decision is made; a save that later fails drops
        # the entry again in `_saved`, so a look-back never shows a card Anki never saw.
        dialog.recorded_ease = ease
        self.remember(dialog, ease)
        collection = mw.col
        cfg = dict(self.settings())
        cfg['_capture_lookup_cache'] = self.capture_lookup_cache
        cfg['_review_exclude_card'] = self._current_reviewer_card()
        cfg['_review_exclude_cards'] = self.session_seen | {dialog.question['card_id']}
        cfg['_review_exclude_words'] = self.session_words | {dialog.question['word'].casefold()}
        cfg['_review_recent_words'] = set(self.recent_words)
        cfg['_review_group'] = (len(cfg['_review_exclude_cards']), self.session_target)
        # The next card is chosen while this rating is still being written, so the
        # deck must be treated as one slot poorer in the queue this card came from.
        inflight_new = dialog.question.get('kind') == 'new'
        cfg['_review_inflight_new'] = 1 if inflight_new else 0
        cfg['_review_inflight_due'] = 0 if inflight_new else 1
        completed = len(self.session_seen) + 1
        current_target = self.session_target
        generation = self.generation

        def save():
            """Write the rating on its own thread; the answer is already given."""
            error = None
            try:
                submit_review(self.api, cfg, dialog.question, ease,
                              lambda question, rating: self._answer_on_main(collection, generation, question, rating))
                # The recommendation and the press are logged together: the weights behind
                # 建议评分 were picked, not fitted, and the override rate is the only honest
                # reading of whether they are too harsh.
                self.log(grading_log_line(getattr(dialog, 'enter_ease', None), ease,
                                          dialog.question.get('mode', ''), dialog.hint_components(),
                                          bool(getattr(dialog, 'force_again', False))))
                self.log('review rating saved')
            except Exception as raised:
                error = str(raised) or type(raised).__name__
                self.log('review save failed: %s' % type(raised).__name__)
            self.signals.saved.emit(dialog, generation, error)

        threading.Thread(target=save, daemon=True).start()
        threading.Thread(target=self._flip(dialog, cfg, completed, current_target, generation),
                         daemon=True).start()

    def _flip(self, dialog, cfg, completed, current_target, generation):
        """The thread body that moves on to the next card, prefetched if one is ready.

        Ratings and 已掌握 share this, so both hand the next card over inside the same
        window instead of closing it and opening another one a second later.
        """
        def run():
            key = (generation, frozenset(cfg['_review_exclude_cards']), current_target)
            ready = self.prefetch_ready
            if self.prefetched is None and ready is not None:
                # A prefetch that is still running is far cheaper than starting a
                # second round trip, so give it a moment before falling back.
                ready.wait(0.4)
            prefetched, self.prefetched = self.prefetched, None
            self.prefetch_ready = None
            result = (prefetched[1] if prefetched is not None and prefetched[0] == key
                      else self._next_result(cfg, completed, current_target))
            self.signals.graded.emit(dialog, None, generation, result)
        return run

    def _advance(self, dialog, inflight):
        """Move on to the next card without writing a rating (used by 已掌握)."""
        cfg = dict(self.settings())
        cfg['_capture_lookup_cache'] = self.capture_lookup_cache
        cfg['_review_exclude_card'] = self._current_reviewer_card()
        cfg['_review_exclude_cards'] = self.session_seen | {dialog.question['card_id']}
        cfg['_review_exclude_words'] = self.session_words | {str(dialog.question.get('word', '')).casefold()}
        cfg['_review_recent_words'] = set(self.recent_words)
        cfg['_review_group'] = (len(cfg['_review_exclude_cards']), self.session_target)
        cfg['_review_inflight_new'] = 1 if inflight and dialog.question.get('kind') == 'new' else 0
        cfg['_review_inflight_due'] = 1 if inflight and dialog.question.get('kind') != 'new' else 0
        threading.Thread(target=self._flip(dialog, cfg, len(self.session_seen) + 1,
                                          self.session_target, self.generation), daemon=True).start()

    def _answer_on_main(self, collection, generation, question, ease):
        done = threading.Event()
        cancelled = threading.Event()
        result = {}
        def answer():
            try:
                # The card may already have been replaced on screen: the rating was
                # given, so it still has to be written. What must not happen is
                # answering into a different account or a card that moved, which the
                # generation, collection and snapshot checks below cover.
                if cancelled.is_set() or generation != self.generation or mw.col is not collection or mw.state == 'review':
                    raise ValueError('Anki 账户或复习状态已改变')
                card = collection.get_card(question['card_id'])
                if any(getattr(card, key) != value for key, value in question['snapshot'].items()):
                    raise ValueError('卡片已发生变化')
                from anki.scheduler.v3 import CardAnswer
                rating = {1: CardAnswer.AGAIN, 2: CardAnswer.HARD, 3: CardAnswer.GOOD, 4: CardAnswer.EASY}[ease]
                from anki.errors import InvalidInput
                def grade():
                    current = collection.get_card(card.id)
                    if any(getattr(current, key) != value for key, value in question['snapshot'].items()):
                        raise ValueError('卡片已发生变化')
                    states = collection._backend.get_scheduling_states(current.id)
                    current.start_timer()
                    native_answer = collection.sched.build_answer(card=current, states=states, rating=rating)
                    collection.sched.answer_card(native_answer)
                try:
                    grade()
                except InvalidInput as error:
                    if 'not at top of queue' not in str(error):
                        raise
                    grade()
                result['value'] = [True]
            except Exception as error:
                result['error'] = error
            finally:
                done.set()
        mw.taskman.run_on_main(answer)
        if not done.wait(20):
            cancelled.set()
            raise RuntimeError('Anki 主线程未及时响应；请检查评分记录')
        if 'error' in result:
            raise result['error']
        return result['value']

    def _saved(self, dialog, generation, error):
        """Silence on success; only a lost rating is news, because the card moved on."""
        if generation != self.generation or not error:
            return
        # A rating that never reached Anki must not be offered as a look-back either.
        self.history = [entry for entry in self.history
                        if entry['question']['card_id'] != dialog.question['card_id']]
        self.feedback('「%s」的评分没有保存：%s。卡片已经翻过去了，Anki 里还没有这条记录。' %
                      (dialog.question.get('word', ''), error))

    def _graded(self, dialog, error, generation, next_result):
        if generation == self.generation and self.dialog is dialog:
            if not error:
                end_reason = None
                if next_result and len(next_result) > 2:
                    self.session_target = next_result[2] if next_result[0] else len(self.session_seen) + 1
                    new_group = len(next_result) > 3 and next_result[3]
                    end_reason = next_result[4] if len(next_result) > 4 else None
                    next_result = next_result[:2] if next_result[0] or next_result[1] else None
                else:
                    new_group = False
                if next_result and next_result[0] and not next_result[1]:
                    dialog.completed = True
                    self._record_review(dialog)
                    if new_group:
                        self.pending_group = (dialog, next_result[0], generation)
                        self._show_group_break(dialog)
                        return
                    if self._handover(dialog, next_result[0], generation):
                        return
                self.prepared_next = next_result
                if next_result and next_result[1]:
                    self.feedback('下一张没能准备好：%s。这张的评分不受影响。' % next_result[1])
                elif not next_result and end_reason:
                    self.feedback(end_reason)
            dialog.grade_result(error)

    def _handover(self, dialog, question, generation):
        """Paint the next card over the window the last one is still using."""
        if not self._prepared(question, None, generation, False, previous=dialog):
            return False
        dialog.finished.disconnect(self._closed)
        dialog.input_mode.restore()
        if dialog is self.review_host:
            dialog.finished.connect(self._host_closed)
        else:
            dialog.accept()
        return True

    def _show_group_break(self, dialog):
        summary = '本组 %d 张已完成 · 下一组约 %d 张' % (len(self.session_seen), self.session_target)
        # The countdown covers the card the next group is about to replace, in the same
        # window: one popup for the whole session instead of a second one next to it.
        host = dialog.window()
        # The panel covers the card, but the letter boxes underneath are still live, and a
        # QLineEdit eats Enter — which made "按 Enter 进入下一组" a promise the window did
        # not keep when the learner's cursor was still in the last box they typed into.
        for box in list(getattr(dialog, 'letter_boxes', None) or ()):
            box.setEnabled(False)
        focused = host.focusWidget()
        if focused is not None:
            focused.clearFocus()
        break_dialog = GroupBreakDialog(summary, self.settings(), parent=host)
        self.break_dialog = break_dialog
        break_dialog.finished.connect(self._break_finished)
        break_dialog.setGeometry(host.rect())
        break_dialog.show()
        break_dialog.raise_()
        self.log('group break offered: %s' % summary)

    def _break_finished(self, result):
        pending, self.pending_group = self.pending_group, None
        panel, self.break_dialog = self.break_dialog, None
        if panel is not None:
            panel.timer.stop()
            panel.hide()
        if pending is None:
            return
        dialog, question, generation = pending
        if result != int(QDialog.DialogCode.Accepted):
            self.end_session(dialog)
            return
        self.session_seen.clear()
        self.session_words.clear()
        if not self._handover(dialog, question, generation):
            self.prepared_next = (question, None)

    def end_session(self, dialog=None):
        """Stop here: the group is finished and the user did not ask for another."""
        self.session_target = len(self.session_seen)
        self.prepared_next = None
        self.prefetched = None
        self.prefetch_ready = None
        current = dialog if dialog is not None else self.dialog
        if current is not None:
            current.reject()

    def style_card(self, text, card, kind):
        try:
            cfg = self.settings()
            deck = mw.col.decks.name(getattr(card, 'odid', 0) or card.did)
            if should_style_card(deck, card.note_type().get('name'), kind, cfg):
                return text + CARD_STYLE
        except Exception as error:
            self.log('card styling skipped: %s' % type(error).__name__)
        return text

    def stop(self, *_args):
        self.generation += 1
        self.timer.stop()
        self.regular_deadline = None
        self.prepared_next = None
        self.prefetched = None
        self.prefetch_ready = None
        self.busy = False
        self.session_seen.clear()
        self.session_words.clear()
        self.recent_words.clear()
        dialog = None
        if self.break_dialog is not None:
            break_dialog, self.break_dialog = self.break_dialog, None
            break_dialog.finished.disconnect(self._break_finished)
            break_dialog.reject()
        self.pending_group = None
        if self.dialog:
            dialog, self.dialog = self.dialog, None
            dialog.finished.disconnect(self._closed)
            dialog.reject()
        if self.review_host is not None:
            host, self.review_host = self.review_host, None
            if host is not dialog:
                host.finished.disconnect(self._host_closed)
                host.reject()
