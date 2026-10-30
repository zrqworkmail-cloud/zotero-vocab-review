"""CET-6 listening practice, independent of Anki scheduling."""
import hashlib
import datetime
import json
from pathlib import Path

from aqt.qt import QComboBox, QDesktopServices, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QUrl, QVBoxLayout, Qt

PASSAGES = [
    {'kind': '长对话', 'audio': "Woman: I heard the library plans to close at six next month. Isn't that a problem for students who work during the day? Man: Yes. The director says energy costs have risen, but the student council has suggested keeping one study room open until ten. Woman: Has the director agreed? Man: Not yet. She wants to see how many students would actually use it before making a decision.",
     'questions': [
        {'question': 'Why does the library plan to close earlier?', 'options': ['A. Its energy costs have increased.', 'B. It is moving to a new building.', 'C. Students prefer to study at home.', 'D. The staff need more training.'], 'answer': 0},
        {'question': 'What will the director consider before deciding?', 'options': ['A. The number of new employees.', 'B. How many students would use the room.', 'C. The price of new furniture.', 'D. The results of a national survey.'], 'answer': 1}]},
    {'kind': '听力篇章', 'audio': "A small town introduced a bicycle-sharing program to reduce short car trips. At first, many residents complained that the bicycles were difficult to find. The organizers then added stations near the railway station and the hospital. Six months later, usage had doubled, although the town has not yet measured whether air pollution has fallen. The organizers say the next step is to improve access in neighborhoods farther from the center.",
     'questions': [
        {'question': 'What was the original problem with the program?', 'options': ['A. The bicycles were too expensive.', 'B. Residents could not easily find bicycles.', 'C. The railway station was closed.', 'D. Most bicycles were damaged.'], 'answer': 1},
        {'question': 'What do the organizers plan to do next?', 'options': ['A. Remove the hospital station.', 'B. Replace bicycles with buses.', 'C. Expand access beyond the town center.', 'D. End the program after six months.'], 'answer': 2}]},
    {'kind': '讲座', 'audio': "Researchers studying memory have found that testing yourself can reveal what you do not yet know. In one experiment, two groups spent equal time learning new words. One group repeatedly reread the list, while the other tried to recall the words before checking the answers. The recall group performed better on a test a week later. The researchers cautioned that the result does not mean rereading is useless; it suggests that practice should include opportunities to retrieve information.",
     'questions': [
        {'question': 'How did the two groups differ?', 'options': ['A. They studied different languages.', 'B. They spent different amounts of time.', 'C. One group practiced recalling words.', 'D. One group took no final test.'], 'answer': 2},
        {'question': 'What do the researchers suggest?', 'options': ['A. Never reread any material.', 'B. Include recall in learning practice.', 'C. Avoid tests after one week.', 'D. Memorize only familiar words.'], 'answer': 1}]},
]


def local_exam(directory, filename='cet6-202512-1.json'):
    directory = Path(directory)
    path = directory / filename
    try:
        exam = json.loads(path.read_text(encoding='utf-8'))
        audio_name = exam.get('audio_file', '')
        if not isinstance(audio_name, str) or Path(audio_name).name != audio_name:
            return None
        audio = directory / audio_name
        if not audio.is_file():
            return None
        digest = hashlib.sha256()
        with audio.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != exam.get('audio_sha256'):
            return None
        questions = exam.get('questions', [])
        if len(questions) != 25 or any(len(q.get('options', [])) != 4 or q.get('answer') not in range(4) for q in questions):
            return None
        transcript_path = directory / (path.stem + '-transcript.md')
        transcript = transcript_path.read_text(encoding='utf-8') if transcript_path.is_file() else ''
        return {'kind': exam['kind'], 'title': exam['title'], 'paper_id': path.stem, 'audio_path': str(audio), 'questions': questions,
                'transcript': transcript}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


class ListeningPractice(QDialog):
    def __init__(self, style='', local_dir=None):
        super().__init__(None)
        self.setWindowTitle('六级听力练习')
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(style)
        self.resize(640, 580)
        self.passage_index = self.question_index = self.correct_count = 0
        self.local_dir = Path(local_dir or Path(__file__).parent / 'user_files' / 'cet6-listening')
        self.local_papers = [paper for path in sorted(self.local_dir.glob('cet6-*.json'))
                             if (paper := local_exam(self.local_dir, path.name))]
        self.local_paper = self.local_papers[0] if self.local_papers else None
        self.passages = [self.local_paper] if self.local_paper else PASSAGES
        self.answered = False
        layout = QVBoxLayout(self)
        self.source_choice = QComboBox()
        for index, paper in enumerate(self.local_papers):
            self.source_choice.addItem('本地真题：' + paper['title'], 'local' if index == 0 else 'local:' + str(index))
        self.source_choice.addItem('原创模拟练习', 'practice')
        self.source_choice.currentIndexChanged.connect(self.change_source)
        layout.addWidget(self.source_choice)
        self.heading = QLabel(); self.heading.setWordWrap(True); layout.addWidget(self.heading)
        self.real_exam_button = QPushButton('在线真题：南京大学历年六级自测')
        self.real_exam_button.setToolTip('在浏览器打开南京大学六级真题自测，包含听力音频、题目和计分。')
        self.real_exam_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://eol.nju.edu.cn/cet6/index.html')))
        layout.addWidget(self.real_exam_button)
        self.play = QPushButton(); self.play.clicked.connect(self.play_audio); layout.addWidget(self.play)
        self.stop_button = QPushButton('停止播放'); self.stop_button.clicked.connect(self.stop_audio); layout.addWidget(self.stop_button)
        self.finished.connect(lambda _result: self.stop_audio())
        self.question = QLabel(); self.question.setWordWrap(True); self.question.setTextFormat(Qt.TextFormat.PlainText); layout.addWidget(self.question)
        self.buttons = []
        for i in range(4):
            button = QPushButton(); button.setObjectName('choice'); button.clicked.connect(lambda _checked=False, n=i: self.answer(n))
            button.setMinimumHeight(42); layout.addWidget(button); self.buttons.append(button)
        self.feedback = QLabel(); self.feedback.setWordWrap(True); layout.addWidget(self.feedback)
        row = QHBoxLayout()
        self.transcript_button = QPushButton('查看原文'); self.transcript_button.clicked.connect(self.show_transcript); row.addWidget(self.transcript_button)
        self.next_button = QPushButton('下一题'); self.next_button.setObjectName('primary'); self.next_button.clicked.connect(self.next_question); row.addWidget(self.next_button)
        layout.addLayout(row)
        self.transcript = QLabel(); self.transcript.setTextFormat(Qt.TextFormat.PlainText); self.transcript.setWordWrap(True)
        self.transcript_area = QScrollArea(); self.transcript_area.setWidgetResizable(True); self.transcript_area.setWidget(self.transcript)
        self.transcript_area.setMinimumHeight(120); self.transcript_area.hide(); layout.addWidget(self.transcript_area)
        layout.addStretch()
        self.refresh()

    def change_source(self):
        self.stop_audio()
        source = self.source_choice.currentData()
        if source == 'local':
            self.passages = [self.local_papers[0]]
        elif isinstance(source, str) and source.startswith('local:'):
            self.passages = [self.local_papers[int(source.split(':')[1])]]
        else:
            self.passages = PASSAGES
        self.passage_index = self.question_index = self.correct_count = 0
        self.play.setEnabled(True)
        for button in self.buttons: button.show()
        self.refresh()

    def refresh(self):
        passage = self.passages[self.passage_index]; q = passage['questions'][self.question_index]
        if 'audio_path' in passage:
            self.heading.setText('%s · 第 %d/%d 题\n第三方整理的真题，录音整套播放；答完可看原文，记录保存在本机。' %
                                 (passage['title'], self.question_index + 1, len(passage['questions'])))
            self.play.setText('播放整套真题录音')
        else:
            self.heading.setText('六级听力模拟 · %s · 材料 %d/%d · 第 %d/%d 题\n原创模拟题，不是历年真题；不计入 Anki 排程。' %
                                 (passage['kind'], self.passage_index + 1, len(self.passages), self.question_index + 1, len(passage['questions'])))
            self.play.setText('播放听力材料（系统语音）')
        self.question.setText(q['question']); self.answered = False
        for i, button in enumerate(self.buttons):
            button.setText(q['options'][i]); button.setEnabled(True); button.setObjectName('choice'); button.style().unpolish(button); button.style().polish(button)
        self.feedback.setText('先播放材料，再选择答案。'); self.transcript.clear(); self.transcript_area.hide()
        self.transcript_button.setEnabled(False); self.next_button.setEnabled(False)

    def play_audio(self):
        try:
            from aqt.sound import av_player
            passage = self.passages[self.passage_index]
            if 'audio_path' in passage:
                av_player.play_file_with_caller(passage['audio_path'], self)
            else:
                from anki.sound import TTSTag
                av_player.play_tags([TTSTag(field_text=passage['audio'], lang='en_US', voices=[], speed=1.0, other_args=[])])
        except Exception:
            self.feedback.setText('音频播放失败，请检查 Anki 的音频设置。')

    def stop_audio(self):
        try:
            from aqt.sound import av_player
            av_player.stop_and_clear_queue_if_caller(self)
        except Exception:
            pass

    def answer(self, index):
        if self.answered:
            return
        q = self.passages[self.passage_index]['questions'][self.question_index]; self.answered = True
        correct = index == q['answer']; self.correct_count += int(correct)
        self.feedback.setText(('回答正确。' if correct else '回答错误。') + ' 正确答案：' + q['options'][q['answer']])
        if 'audio_path' in self.passages[self.passage_index]:
            try:
                entry = {'time': datetime.datetime.now().isoformat(timespec='seconds'), 'paper': self.passages[self.passage_index]['paper_id'],
                         'question': q.get('number', self.question_index + 1), 'selected': index, 'correct': correct}
                with (self.local_dir / 'progress.jsonl').open('a', encoding='utf-8') as output:
                    output.write(json.dumps(entry, ensure_ascii=False) + '\n')
            except OSError:
                self.feedback.setText(self.feedback.text() + ' 本次记录未保存。')
        for i, button in enumerate(self.buttons):
            button.setEnabled(False)
            if i == q['answer']:
                button.setText('✓ ' + q['options'][i])
                button.setObjectName('primary'); button.style().unpolish(button); button.style().polish(button)
            elif i == index:
                button.setText('✗ ' + q['options'][i])
        self.transcript_button.setEnabled('audio' in self.passages[self.passage_index]); self.next_button.setEnabled(True)

    def show_transcript(self):
        passage = self.passages[min(self.passage_index, len(self.passages) - 1)]
        self.transcript.setText('【听力原文】\n' + (passage.get('audio') or passage.get('transcript', '')))
        self.transcript_area.show()

    def next_question(self):
        if not self.answered:
            return
        self.question_index += 1
        if self.question_index >= len(self.passages[self.passage_index]['questions']):
            self.question_index = 0; self.passage_index += 1
        if self.passage_index >= len(self.passages):
            self.heading.setText('练习完成 · 答对 %d / %d 题' % (self.correct_count, sum(len(p['questions']) for p in self.passages)))
            self.question.setText('练习结果没有修改 Anki 卡片评分。')
            self.play.setEnabled(False); self.transcript_button.setEnabled(bool(self.passages[-1].get('transcript'))); self.next_button.setEnabled(False)
            for button in self.buttons: button.hide()
            self.feedback.clear(); self.transcript.clear(); self.transcript_area.hide()
            return
        self.refresh()
