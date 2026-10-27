"""A small, non-modal vocabulary review window for the configured Anki deck."""

import threading

from aqt import mw
from aqt.qt import (
    QApplication, QCursor, QDialog, QHBoxLayout, QLabel, QLineEdit, QObject,
    QPushButton, QScrollArea, QTimer, QVBoxLayout, QWidget, pyqtSignal, Qt,
)

from .review_logic import answer_matches, prepare_question, should_style_card, submit_review


POPUP_STYLE = """
QDialog { background: #f4f6fb; color: #1e293b; font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; }
QLabel { color: #334155; font-size: 13px; }
QLabel#eyebrow { color: #5968b3; font-size: 12px; font-weight: 700; letter-spacing: 1px; }
QLabel#question { color: #172554; font-size: 27px; font-weight: 700; padding: 8px 0; }
QLabel#answer { color: #27344d; background: #ffffff; border: 1px solid #e0e7f2;
                border-radius: 12px; padding: 12px; font-size: 14px; }
QLabel#status { color: #66758d; font-size: 12px; }
QPushButton { background: #ffffff; color: #27344d; border: 1px solid #dce4f1;
              border-radius: 10px; padding: 9px 12px; text-align: left; font-size: 13px; }
QPushButton:hover { background: #eef2ff; border-color: #8996e8; }
QPushButton:disabled { color: #8c98aa; background: #f0f2f6; }
QPushButton#primary { background: #5668ca; color: white; border: none; text-align: center; font-weight: 600; }
QPushButton#primary:hover { background: #4557b5; }
QPushButton#secondary { background: transparent; border: none; color: #728096; text-align: center; }
QLineEdit { background: white; color: #172554; border: 1px solid #dce4f1; border-radius: 10px;
            padding: 10px 12px; font-size: 16px; }
QLineEdit:focus { border: 1px solid #7080dd; }
QScrollArea { border: none; background: transparent; }
"""


CARD_STYLE = """
<style id="zvr-vocabulary-theme">
body.card { max-width: 780px !important; margin: 32px auto !important; padding: 0 20px 32px !important;
  background: #f3f6fb !important; color: #1e293b !important; font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif !important; }
.card .section { background: #fff !important; color: #334155 !important; border-radius: 18px !important;
  border: 1px solid #e3e9f3 !important; box-shadow: 0 12px 32px rgba(43,58,92,.08) !important;
  padding: 10px 18px !important; margin: 16px 0 !important; line-height: 1.65 !important; }
.card .items { padding: 12px 0 !important; overflow-wrap: anywhere; }
.card #front { color: #223271 !important; font-size: 2.1em !important; font-weight: 700 !important; letter-spacing: -.02em; }
.card #back { color: #243450 !important; font-size: 1.1em !important; }
.card #front-extra1 { color: #7988ad !important; }
.card hr { border: 0 !important; border-top: 1px solid #e8edf5 !important; }
.card a { color: #5668ca !important; }
.card img { max-width: 100%; height: auto; }
</style>
"""


def _plain_label(text, name=None):
    label = QLabel(str(text))
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    return label


class ReviewDialog(QDialog):
    def __init__(self, question, position, grade):
        super().__init__(None)
        self.question = question
        self.grade = grade
        self.answer_shown = False
        self.setWindowTitle('单词随身复习')
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(POPUP_STYLE)
        self.resize(470, 530)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(_plain_label('VOCABULARY  ·  %s' % ('新词' if question['kind'] == 'new' else '到期复习'), 'eyebrow'))
        self.prompt = _plain_label('选择正确的释义' if question['mode'] == 'choice' else '根据释义填写英文单词')
        layout.addWidget(self.prompt)
        self.question_label = _plain_label(question['word'] if question['mode'] == 'choice' else question['meaning'][:320], 'question')
        layout.addWidget(self.question_label)

        self.input = None
        self.choice_buttons = []
        if question['mode'] == 'choice':
            if question.get('phonetic'):
                layout.addWidget(_plain_label(question['phonetic']))
            for index, option in enumerate(question['options']):
                visible = option if len(option) <= 30 else option[:30] + '…'
                button = QPushButton('%s  %s' % (chr(65 + index), visible))
                button.setToolTip(option)
                button.clicked.connect(lambda _checked=False, value=option: self.reveal(value == question['meaning']))
                self.choice_buttons.append(button)
                layout.addWidget(button)
        else:
            self.input = QLineEdit()
            self.input.setPlaceholderText('输入英文单词或短语')
            self.input.setMaxLength(160)
            self.input.returnPressed.connect(self.check_input)
            layout.addWidget(self.input)
            self.check_button = QPushButton('核对答案')
            self.check_button.setObjectName('primary')
            self.check_button.clicked.connect(self.check_input)
            layout.addWidget(self.check_button)

        self.answer_label = _plain_label('', 'answer')
        self.answer_scroll = QScrollArea()
        self.answer_scroll.setWidgetResizable(True)
        self.answer_scroll.setMinimumHeight(120)
        self.answer_scroll.setMaximumHeight(200)
        self.answer_scroll.setWidget(self.answer_label)
        self.answer_scroll.hide()
        layout.addWidget(self.answer_scroll)
        self.status = _plain_label('查看答案后，自行选择复习结果。', 'status')
        layout.addWidget(self.status)

        self.grade_widget = QWidget()
        grade_layout = QHBoxLayout(self.grade_widget)
        grade_layout.setContentsMargins(0, 0, 0, 0)
        self.grade_buttons = []
        for caption, ease in [('再练一次', 1), ('记住了', 3), ('很容易', 4)]:
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
        self.position = position

    def showEvent(self, event):
        super().showEvent(event)
        self.position_window()

    def position_window(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            if self.position == 'center':
                self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
            else:
                self.move(area.right() - self.width() - 20, area.bottom() - self.height() - 20)

    def check_input(self):
        if self.input and self.input.text().strip():
            self.reveal(answer_matches(self.question['word'], self.input.text()))
        else:
            self.status.setText('先填写英文单词，或点“稍后再说”。')

    def reveal(self, correct):
        if self.answer_shown:
            return
        self.answer_shown = True
        for button in self.choice_buttons:
            button.hide()
        if self.input:
            self.input.setReadOnly(True)
            self.check_button.hide()
        pieces = [self.question['word'] + ('  ' + self.question['phonetic'] if self.question.get('phonetic') else ''),
                  self.question['meaning']]
        if self.question.get('example'):
            pieces.append('例句：' + self.question['example'][:350])
        if self.question.get('literature'):
            pieces.append('文献：' + self.question['literature'][:350])
        self.answer_label.setText('\n\n'.join(pieces))
        self.answer_scroll.show()
        self.status.setText(('回答正确。' if correct else '已显示正确答案。') + ' 请选择复习结果，写入 Anki。')
        self.grade_widget.show()
        self.later.setText('不评分，关闭')
        self.adjustSize()
        self.position_window()

    def start_grade(self, ease):
        for button in self.grade_buttons:
            button.setEnabled(False)
        self.later.setEnabled(False)
        self.status.setText('正在保存复习结果…')
        self.grade(self, ease)

    def grade_result(self, error):
        self.later.setEnabled(True)
        if error:
            self.status.setText('未能确认评分已保存：%s。请在 Anki 中检查后再复习。' % error)
            self.later.setText('关闭')
            return
        self.status.setText('复习结果已保存到 Anki。')
        self.later.setText('关闭')
        QTimer.singleShot(1200, self.accept)


class _Signals(QObject):
    prepared = pyqtSignal(object, object, int, bool)
    graded = pyqtSignal(object, object, int)


class DesktopReviewController:
    def __init__(self, settings, api, feedback, log):
        self.settings, self.api, self.feedback, self.log = settings, api, feedback, log
        self.signals = _Signals()
        self.signals.prepared.connect(self._prepared)
        self.signals.graded.connect(self._graded)
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._tick)
        self.dialog = None
        self.busy = False
        self.generation = 0

    def start(self, *_args):
        self.schedule()

    def schedule(self):
        self.timer.stop()
        cfg = self.settings()
        if cfg.get('review_enabled', True):
            minutes = max(5, min(240, int(cfg.get('review_interval_minutes', 30))))
            self.timer.start(minutes * 60000)
            self.log('review timer scheduled: %d minutes' % minutes)

    def _tick(self):
        self.show_next(False)

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

    def show_next(self, manual=True):
        if self.busy or self.dialog:
            if manual:
                self.feedback('复习卡正在准备或已经显示。')
            return
        if mw.col is None or self._reviewer_is_foreground():
            if manual:
                self.feedback('请先打开 Anki 账户，并结束当前 Anki 复习。')
            self.schedule()
            return
        self.timer.stop()
        cfg = dict(self.settings())
        cfg['_review_exclude_card'] = self._current_reviewer_card()
        generation = self.generation
        self.busy = True

        def work():
            try:
                question = prepare_question(self.api, cfg, cfg.get('review_mode', 'mixed'))
                self.signals.prepared.emit(question, None, generation, manual)
            except Exception as error:
                self.log('review preparation failed: %s' % type(error).__name__)
                self.signals.prepared.emit(None, str(error), generation, manual)

        threading.Thread(target=work, daemon=True).start()

    def _prepared(self, question, error, generation, manual):
        if generation != self.generation:
            return
        self.busy = False
        if not manual and not self.settings().get('review_enabled', True):
            return
        if error or not question:
            if manual:
                self.feedback('复习暂不可用：%s' % error if error else '当前没有可复习的词，或今天的学习额度已用完。')
            self.schedule()
            return
        if mw.col is None or self._reviewer_is_foreground() or self._current_reviewer_card() == question['card_id']:
            self.schedule()
            return
        self.dialog = ReviewDialog(question, self.settings().get('review_position', 'corner'), self._grade)
        self.dialog.finished.connect(self._closed)
        self.dialog.show()
        self.dialog.raise_()
        self.log('review popup displayed')

    def _closed(self, _result):
        self.dialog = None
        self.schedule()

    def _grade(self, dialog, ease):
        if mw.col is None or self._reviewer_is_foreground() or self._current_reviewer_card() == dialog.question['card_id']:
            dialog.grade_result('Anki 正在复习或账户已关闭')
            return
        cfg = self.settings()
        generation = self.generation

        def work():
            try:
                submit_review(self.api, cfg, dialog.question, ease)
                self.signals.graded.emit(dialog, None, generation)
            except Exception as error:
                self.log('review grading failed: %s' % type(error).__name__)
                self.signals.graded.emit(dialog, str(error), generation)

        threading.Thread(target=work, daemon=True).start()

    def _graded(self, dialog, error, generation):
        if generation == self.generation and self.dialog is dialog:
            if not error:
                self.log('review rating saved')
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
        self.busy = False
        if self.dialog:
            dialog, self.dialog = self.dialog, None
            dialog.finished.disconnect(self._closed)
            dialog.reject()
