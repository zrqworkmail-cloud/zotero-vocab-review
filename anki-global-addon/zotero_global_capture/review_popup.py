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

from .review_logic import (answer_matches, clean_detail, clean_text, cloze_sentence, collection_plan, end_of_session_reason, example_groups, exam_word_labels, format_meaning, link_example_html, literature_example_html, masked_example, mask_answer_clues, meaning_table, next_check_delay, plan_limits_new, root_detail_html,
                           next_hint_index, prepare_question, session_batch_size, should_style_card, spelling_hint, spoken_examples, submit_review, suggested_ease, today_remaining, updated_session_target, window_wait)
from . import morphology, word_relations
from .input_mode import ReviewInputMode


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
QLabel#cardHeading { color: #64749a; font-size: 12px; font-weight: 700; background: transparent; }
QLabel#meaningHeading { color: #64749a; font-size: 15px; font-weight: 700; background: transparent; }
QLabel#cardText { color: #27344d; font-size: 14px; font-weight: normal; background: transparent; }
QPushButton { background: #ffffff; color: #27344d; border: 1px solid #dce4f1;
              border-radius: 10px; padding: 9px 12px; text-align: center; font-size: 13px; }
QPushButton#choice { text-align: left; }
QPushButton:hover { background: #eef2ff; border-color: #8996e8; }
QPushButton:disabled { color: #8c98aa; background: #f0f2f6; }
QPushButton#primary { background: #5668ca; color: white; border: none; text-align: center; font-weight: 600; }
QPushButton#primary:hover { background: #4557b5; }
QPushButton#secondary { background: transparent; border: none; color: #728096; text-align: center; }
QLineEdit { background: white; color: #172554; border: 1px solid #dce4f1; border-radius: 10px;
            padding: 10px 12px; font-size: 16px; }
QLineEdit:focus { border: 1px solid #7080dd; }
QScrollArea { border: none; background: transparent; }
QWidget#answerContent { background: #f4f6fb; }
QWidget#letterRow { background: #f4f6fb; }
QWidget#questionBlock { background: #f4f6fb; }
QWidget#detailCard { background: white; border: 1px solid #e0e7f2; border-radius: 12px; }
QPushButton#speaker { background: #eef2ff; border: 1px solid transparent; border-radius: 16px; padding: 5px; }
QPushButton#speaker:hover, QPushButton#speaker:focus { border: 1px solid #8996e8; border-radius: 16px; }
QPushButton#cardMenu { background: transparent; border: none; color: #64749a; font-size: 22px; padding: 0; }
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
    '#f0f2f6': '#343d4c', '#5668ca': '#596dd1', '#4557b5': '#6e80df',
    '#728096': '#b5c0d1', '#7080dd': '#aab8ff', 'background: white': 'background: #252e40',
}

def popup_style(cfg):
    style = POPUP_STYLE
    if cfg.get('review_theme', 'light') == 'dark':
        for old, new in _DARK_COLORS.items():
            style = style.replace(old, new)
        # The platform volume icon is dark; keep its button light for contrast.
        style += '\nQPushButton#speaker { background: #d9e2ff; }'
    return style


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


def _meaning_label(text, name):
    label = _plain_label('', name)
    font = label.font()
    font.setPixelSize(15 if name == 'meaning' else 14)
    metrics = QFontMetrics(font)
    parts = re.findall(r'(?m)^([A-Za-z]+\.)', format_meaning(text))
    width = max((metrics.horizontalAdvance(part) for part in parts), default=0) + 8
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setText(meaning_table(text, width))
    return label


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
        self.setFixedSize(38, 40)
        self.changed('')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.textChanged.connect(self.changed)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.owner.input_mode.enable(int(self.owner.winId()))

    def changed(self, value):
        expected = self.owner.letter_positions[self.index][1]
        if value and value.casefold() != expected.casefold() and not self.owner.answer_shown:
            self.owner.incorrect_letters += 1
        dark = self.owner.cfg.get('review_theme') == 'dark'
        color = ('#71e0b5' if dark else '#198765') if value.casefold() == expected.casefold() else ('#ff99a9' if dark else '#d34d61')
        base = ('background: #252e40; color: #edf1fa; border: 1px solid #4a5971;' if dark else 'background: white; border: 1px solid #dce4f1;') + ' border-radius: 8px; padding: 2px; font-size: 18px;'
        self.setStyleSheet(base + (' color: %s; font-weight: 700;' % color if value else ''))
        if value and self.index + 1 < len(self.owner.letter_boxes):
            self.owner.letter_boxes[self.index + 1].setFocus()

    def paintEvent(self, event):
        super().paintEvent(event)
        # Qt hides centered placeholder text in a focused QLineEdit.
        if self.hasFocus() and not self.text() and self.placeholderText():
            painter = QPainter(self)
            painter.setFont(self.font())
            painter.setPen(QColor('#7b86a5'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.placeholderText())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.owner.add_hint()
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


class ReviewDialog(QDialog):
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
        self.input_mode = ReviewInputMode()
        self.finished.connect(lambda _result: self.input_mode.restore())
        self.enter_ease = None
        self.grading = False
        self.force_again = False
        self.completed = False
        self.skipped = False
        self.hints = 0
        self.hint_uses = 0
        self.incorrect_letters = 0
        self.failed_attempts = 0
        self.setWindowTitle('单词随身复习')
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setStyleSheet(popup_style(self.cfg))
        self.resize(510, 570)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(10)
        top = QHBoxLayout()
        eyebrow = _plain_label('VOCABULARY  ·  %s' % ('新词' if question['kind'] == 'new' else '到期复习'), 'eyebrow')
        eyebrow.setWordWrap(False)
        top.addWidget(eyebrow, 1)
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
            '答错或直接显示答案按“再练一次”。答对时会根据拼写错误和提示次数建议评分；你也可以自己调整。复习日期由 Anki 排程决定。'))
        zotero = menu.addAction('Zotero 配套插件介绍与下载')
        zotero.triggered.connect(lambda: QDesktopServices.openUrl(QUrl('https://github.com/zrqworkmail-cloud/zotero-vocab-review')))
        menu_button.setMenu(menu)
        top.addWidget(menu_button)
        layout.addLayout(top)
        remaining = question.get('_today_remaining')
        today_text = ('今日计划剩余：%d 张%s' % (remaining, '（含当前卡）' if remaining else '（目标已完成）')
                      if remaining is not None else '今日计划剩余：暂无计划数据')
        progress_text = '本组 %s  ·  %s' % (progress, today_text)
        progress_label = _plain_label(progress_text, 'status')
        progress_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        if question.get('_new_group'):
            progress_label.setText('已自动进入下一组  ·  ' + progress_text)
            timer = QTimer(progress_label)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: progress_label.setText(progress_text))
            timer.start(2500)
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
                self.listen_button = QPushButton('重新播放单词')
                self.listen_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume))
                self.listen_button.setAccessibleName('重新播放单词发音')
                self.listen_button.clicked.connect(self.play_listening_prompt)
                block_layout.insertWidget(0, self.listen_button)
                self.listening_explanation = _plain_label('单词和释义暂时隐藏；点击下方“释义提示”查看中文。', 'status')
                self.listening_explanation.setWordWrap(True)
                block_layout.insertWidget(1, self.listening_explanation)
            layout.addWidget(self.question_block)
        else:
            self.question_label = _plain_label(content, 'question')
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
        if mode in ('choice', 'reverse', 'judgment'):
            correct = (question['meaning'] if mode == 'choice' else question['word'] if mode == 'reverse'
                       else ('正确' if question['judgment_correct'] else '错误'))
            for index, option in enumerate(question['options']):
                display_option = mask(option) if mode == 'choice' else option
                visible = display_option if len(display_option) <= 45 else display_option[:45] + '…'
                button = QPushButton('%s   %s' % (chr(65 + index), visible))
                button.setObjectName('choice')
                button.setToolTip(display_option)
                button.clicked.connect(lambda _checked=False, value=option: self.reveal(value == correct))
                self.choice_buttons.append(button)
                button.installEventFilter(self)
                layout.addWidget(button)
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
            buttons = QHBoxLayout()
            self.check_button = QPushButton('检查拼写')
            self.check_button.setObjectName('primary')
            self.check_button.clicked.connect(self.check_input)
            self.hint_button = QPushButton('增加字母提示')
            self.hint_button.setToolTip('输入字母时按空格可显示下一个提示字母')
            self.hint_button.clicked.connect(self.add_hint)
            if mode == 'listening':
                self.meaning_hint_button = QPushButton('释义提示')
                self.meaning_hint_button.clicked.connect(self.show_meaning_hint)
                buttons.addWidget(self.meaning_hint_button)
            if mode == 'typing':
                self.example_hint_button = QPushButton('例句提示')
                self.example_hint_button.clicked.connect(self.request_example_hint)
                buttons.addWidget(self.example_hint_button)
            self.answer_button = QPushButton('显示答案')
            self.answer_button.clicked.connect(lambda: self.reveal(False))
            for button in (self.check_button, self.hint_button, self.answer_button):
                buttons.addWidget(button)
            layout.addLayout(buttons)

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
        word_row.addStretch()
        word_row.addWidget(self.answer_word)
        word_row.addWidget(self.speaker_button([question['word']], '朗读单词'))
        word_row.addStretch()
        self.answer_layout.addLayout(word_row)
        self.answer_phonetic = _plain_label(question.get('phonetic', ''), 'status')
        self.answer_phonetic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.answer_layout.addWidget(self.answer_phonetic)
        self.answer_labels = []
        self.answer_scroll = QScrollArea()
        self.answer_scroll.setWidgetResizable(True)
        self.answer_scroll.setMinimumHeight(120)
        self.answer_scroll.setWidget(answer_content)
        self.answer_scroll.hide()
        layout.addWidget(self.answer_scroll)
        layout.setStretchFactor(self.answer_scroll, 1)
        layout.addWidget(self.result_label)
        self.status = _plain_label('先尝试回答；需要时可以使用提示。', 'status')
        if self.letter_boxes:
            self.status.setText('空格：字母提示；回车：检查拼写或朗读单词。')
            if mode == 'listening':
                self.status.setText('点击播放或按回车重听；需要时可查看释义或字母提示。')
        elif self.spoken_answer_button is not None:
            self.status.setText('回车：我已说出，查看答案。空格：想不起来，显示答案。')
        layout.addWidget(self.status)
        self.grade_widget = QWidget()
        grade_layout = QHBoxLayout(self.grade_widget)
        grade_layout.setContentsMargins(0, 0, 0, 0)
        self.grade_buttons = []
        for caption, ease in [('再练一次', 1), ('困难', 2), ('记住了', 3), ('很容易', 4)]:
            button = QPushButton(caption)
            if ease == 3:
                button.setObjectName('primary')
            button.clicked.connect(lambda _checked=False, value=ease: self.start_grade(value))
            self.grade_buttons.append(button)
            grade_layout.addWidget(button)
        self.grade_widget.hide()
        layout.addWidget(self.grade_widget)
        self.later = QPushButton('稍后再说')
        self.later.setObjectName('secondary')
        self.later.clicked.connect(self.reject)
        layout.addWidget(self.later)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'question_examples'):
            QTimer.singleShot(0, self.resize_question_examples)
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

    def position_window(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            if self.position == 'center':
                self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
            else:
                self.move(area.right() - self.width() - 20, area.bottom() - self.height() - 20)

    def speaker_button(self, texts, tooltip, hint=False):
        button = QPushButton()
        button.setObjectName('speaker')
        button.setFixedSize(32, 32)
        button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setEnabled(bool(texts))
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
            header.addWidget(self.speaker_button(audio_texts, '朗读%s' % heading, hint=hint))
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
        self.status.setText('已显示部分字母，可继续尝试；按空格可再提示一个字母。')
        if self.cfg.get('review_hint_audio', False):
            self.speak_many([self.letter_positions[index][1]])

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
        self.status.setText('例句中已隐藏目标词；使用提示会计入评分建议。')
        if not getattr(self, '_embedded', False):
            self.adjustSize()
            self.position_window()

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

    def show_meaning_hint(self):
        self.listening_explanation.hide()
        self.meaning_heading.show()
        self.question_label.show()
        self.meaning_hint_button.setEnabled(False)
        self.hint_uses += 1
        self.status.setText('已显示释义提示；使用提示会计入评分建议。')
        if not getattr(self, '_embedded', False):
            self.adjustSize()
            self.position_window()

    def hear_hint(self, texts):
        if self.speak_many(texts) is not False:
            self.hint_uses += 1

    def speak_many(self, texts):
        try:
            from anki.sound import TTSTag
            from aqt.sound import av_player
            av_player.play_tags([TTSTag(field_text=text[:500], lang='en_US', voices=[], speed=1.0, other_args=[]) for text in texts if text])
            return True
        except Exception:
            self.status.setText(self.status.text() + ' 系统语音不可用，请检查 Anki 的英文语音设置。')
            return False

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.input_mode.restore()
        super().changeEvent(event)

    def eventFilter(self, watched, event):
        if isinstance(watched, QWidget) and watched is not self and not self.isAncestorOf(watched):
            return super().eventFilter(watched, event)
        if (not self.answer_shown and self.choice_buttons and event.type() == QEvent.Type.KeyPress
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            index = event.key() - Qt.Key.Key_A
            if 0 <= index < len(self.choice_buttons):
                self.choice_buttons[index].click()
                event.accept()
                return True
        if self.answer_shown and event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self.grading and self.enter_ease is not None:
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

    def reveal(self, correct):
        if self.answer_shown:
            return
        self.setUpdatesEnabled(False)
        self._flipping = True
        try:
            self.answer_shown = True
            self.enter_ease = None if correct is None else suggested_ease(correct, self.hint_uses, self.incorrect_letters, self.failed_attempts)
            for button in self.choice_buttons:
                button.hide()
            self.prompt_label.hide()
            self.question_label.hide()
            if hasattr(self, 'question_block'):
                self.question_block.hide()
            if hasattr(self, 'meaning_heading'):
                self.meaning_heading.hide()
            if hasattr(self, 'phonetic_label'):
                self.phonetic_label.hide()
            if hasattr(self, 'judgment_label'):
                self.judgment_label.hide()
            if self.spoken_answer_button is not None:
                self.spoken_answer_button.hide()
                self.spoken_unknown_button.hide()
            if self.letter_boxes:
                self.letter_scroll.hide()
                if hasattr(self, 'example_hint_button'):
                    self.example_hint_button.hide()
                if hasattr(self, 'meaning_hint_button'):
                    self.meaning_hint_button.hide()
                for button in (self.check_button, self.hint_button, self.answer_button):
                    button.hide()
            self.answer_word.setText(self.question['word'])
            labels = exam_word_labels(self.question['word'])
            if labels:
                sources = []
                if any(label in labels for label in ('四级词表', '六级词表')):
                    sources.append('ECDICT 四六级词表')
                if '六级社区核心词' in labels:
                    sources.append('CET-6 Top 500 社区整理')
                self.add_detail('词表归属', ' · '.join(labels) + '\n来源：' + '；'.join(sources))
            if self.answer_form.casefold() != self.question['word'].casefold():
                self.add_detail('例句中的形式', self.answer_form)
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
            if chunks:
                title, pieces = chunks
                note = '来源：Moby 音节词表；不代表词根词缀。' if title == '音节分段' else '按字母机械分组，不代表音节或词根词缀。'
                self.add_detail(title, ' · '.join(pieces) + '\n' + note)
            contrast = morphology.confusion(self.question['word'])
            if contrast:
                self.add_detail('易混辨析', contrast)
            self.show_relations()
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
                button.setObjectName('primary' if index == self.enter_ease else '')
                button.style().unpolish(button)
                button.style().polish(button)
            rating_name = {1: '再练一次', 2: '困难', 3: '记住了', 4: '很容易'}.get(self.enter_ease)
            if correct is None:
                self.status.setText('请听发音并选择评分；此题不会自动识别或上传语音。')
            elif not correct:
                self.status.setText('回答错误或已查看答案：按“再练一次”记录。回车继续。')
            else:
                self.status.setText('错误字母 %d 次，提示 %d 次，检查失败 %d 次；建议“%s”，回车继续，也可自行评分。' %
                                    (self.incorrect_letters, self.hint_uses, self.failed_attempts, rating_name))
            self.grade_widget.show()
            if self.force_again:
                self.grade_buttons[0].setText('再练一次并继续')
                self.grade_buttons[1].hide()
                self.grade_buttons[2].setText('继续学习')
                self.grade_buttons[3].hide()
            self.later.setText('不评分，结束')
            for widget in [self] + self.findChildren(QWidget):
                widget.installEventFilter(self)
        finally:
            self.setUpdatesEnabled(True)
        self.flip_finished()
        speech = []
        if self.cfg.get('review_auto_word', True):
            speech.append(self.question['word'])
        mode = self.cfg.get('review_auto_example_mode', 'example' if self.cfg.get('review_auto_example', False) else 'first')
        speech.extend(spoken_examples(self.question.get('example', ''), self.question.get('literature', ''), mode))
        if any(speech):
            self.speak_many(speech)

    def start_grade(self, ease):
        if self.grading:
            return
        if self.force_again:
            ease = 1
        self.grading = True
        for button in self.grade_buttons:
            button.setEnabled(False)
        self.later.setEnabled(False)
        self.status.setText('正在保存复习结果…')
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
            self.later.setText('跳过并继续（本次不重试评分）')
            self.later.clicked.disconnect()
            self.later.clicked.connect(self.skip_after_error)
            return
        self.completed = True
        self.status.setText('复习结果已保存到 Anki。')
        self.accept()

    def skip_after_error(self):
        self.skipped = True
        self.accept()


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
    saved = pyqtSignal(object, int)
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
            self.session_target = session_batch_size(cfg)
        cfg['_review_exclude_card'] = self._current_reviewer_card()
        cfg['_capture_lookup_cache'] = self.capture_lookup_cache
        cfg['_review_exclude_cards'] = self.session_seen.copy()
        cfg['_review_exclude_words'] = self.session_words.copy()
        now = time.monotonic()
        self.recent_words = {word: timestamp for word, timestamp in self.recent_words.items() if now - timestamp < 1800}
        cfg['_review_recent_words'] = set(self.recent_words)
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
                limit_to_due = due_only or (plan is not None and plan['new_remaining'] <= 0)
                question = prepare_question(self.api, cfg, cfg.get('review_mode', 'mixed'), due_only=limit_to_due)
                if question:
                    if plan is None and (cfg.get('review_plan_mode') == 'daily' or cfg.get('review_deadline') or cfg.get('review_daily_goal')):
                        try:
                            plan = collection_plan(self.api, cfg)
                        except Exception as error:
                            self.log('review plan refresh failed: %s' % type(error).__name__)
                    question['_today_remaining'] = today_remaining(plan) if plan else None
                self.signals.prepared.emit(question, None, generation, manual)
            except Exception as error:
                self.log('review preparation failed: %s' % type(error).__name__)
                self.signals.prepared.emit(None, str(error), generation, manual)

        threading.Thread(target=work, daemon=True).start()

    def _prepared(self, question, error, generation, manual, previous=None):
        if generation != self.generation:
            return
        self.busy = False
        if not manual and not self.settings().get('review_enabled', True):
            return
        if error or not question:
            if manual:
                self.feedback('复习暂不可用：%s' % error if error else '没有符合已选题型的可复习词，或今天的学习额度已用完。')
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
            self.dialog.finished.connect(self._closed)
            connected = True
            self.dialog.show()
            self.dialog.raise_()
            if previous is None:
                self.review_host = self.dialog
            self.log('review popup displayed')
            self._lookup_known_words(self.dialog, cfg)
            self._lookup_relations(self.dialog, dict(cfg))
            if previous is not None:
                host._embedded_dialog = self.dialog
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

    def _grade(self, dialog, ease):
        if mw.col is None or mw.state == 'review':
            dialog.grade_result('Anki 正在复习或账户已关闭')
            return
        collection = mw.col
        cfg = dict(self.settings())
        cfg['_capture_lookup_cache'] = self.capture_lookup_cache
        cfg['_review_exclude_card'] = self._current_reviewer_card()
        cfg['_review_exclude_cards'] = self.session_seen | {dialog.question['card_id']}
        cfg['_review_exclude_words'] = self.session_words | {dialog.question['word'].casefold()}
        cfg['_review_recent_words'] = set(self.recent_words)
        completed = len(self.session_seen) + 1
        current_target = self.session_target
        generation = self.generation

        def work():
            try:
                target = current_target
                current_plan = None
                submit_review(self.api, cfg, dialog.question, ease,
                              lambda question, rating: self._answer_on_main(dialog, collection, generation, question, rating))
                next_result = None
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
                self.signals.saved.emit(dialog, generation)
                limits_new = plan_limits_new(cfg)
                try:
                    next_question = prepare_question(self.api, cfg, cfg.get('review_mode', 'mixed'),
                                                     due_only=bool(limits_new and current_plan is not None and
                                                                   current_plan['new_remaining'] <= 0))
                    if next_question:
                        next_question['_today_remaining'] = today_remaining(current_plan) if current_plan else None
                        next_question['_new_group'] = new_group
                    next_result = (next_question, None, target, new_group,
                                   None if next_question else end_of_session_reason(current_plan, limits_new))
                except Exception as error:
                    self.log('review preparation failed: %s' % type(error).__name__)
                    next_result = (None, str(error), target, False, None)
                self.signals.graded.emit(dialog, None, generation, next_result)
            except Exception as error:
                self.log('review grading failed: %s' % type(error).__name__)
                self.signals.graded.emit(dialog, str(error), generation, None)

        threading.Thread(target=work, daemon=True).start()

    def _answer_on_main(self, dialog, collection, generation, question, ease):
        done = threading.Event()
        cancelled = threading.Event()
        result = {}
        def answer():
            try:
                if cancelled.is_set() or generation != self.generation or self.dialog is not dialog or mw.col is not collection or mw.state == 'review':
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

    def _saved(self, dialog, generation):
        if generation == self.generation and self.dialog is dialog:
            dialog.status.setText('复习结果已保存，正在准备下一张…')

    def _graded(self, dialog, error, generation, next_result):
        if generation == self.generation and self.dialog is dialog:
            if not error:
                self.log('review rating saved')
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
                        self.session_seen.clear()
                        self.session_words.clear()
                    if self._prepared(next_result[0], None, generation, False, previous=dialog):
                        dialog.finished.disconnect(self._closed)
                        dialog.input_mode.restore()
                        if dialog is self.review_host:
                            dialog.finished.connect(self._host_closed)
                        else:
                            dialog.accept()
                        return
                self.prepared_next = next_result
                if next_result and next_result[1]:
                    self.feedback('复习结果已保存，但下一张准备失败。')
                elif not next_result and end_reason:
                    self.feedback(end_reason)
            dialog.grade_result(error)

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
        self.busy = False
        self.session_seen.clear()
        self.session_words.clear()
        self.recent_words.clear()
        dialog = None
        if self.dialog:
            dialog, self.dialog = self.dialog, None
            dialog.finished.disconnect(self._closed)
            dialog.reject()
        if self.review_host is not None:
            host, self.review_host = self.review_host, None
            if host is not dialog:
                host.finished.disconnect(self._host_closed)
                host.reject()
