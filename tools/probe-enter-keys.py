"""What does 回车 actually do on each question type, measured instead of remembered?

The learner asked for this table (2026-11-05) before adding "回车朗读" to the card, because
the key is already spoken for in several places: the answer face grades, the spelling box
either speaks or submits, the speaking card reveals, and a focused option button answers the
question on its own.

Read-only: this drives an offscreen dialog and reports state changes. Nothing here talks to
Anki.

    python tools/probe-enter-keys.py
"""
import os
import sys
import types

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32'),
                               os.environ['SystemRoot']])
os.add_dll_directory(os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(BASE))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_PLUGIN_PATH'] = os.path.join(BASE, 'PyQt6', 'Qt6', 'plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))

from PyQt6.QtCore import QObject, QEvent, QPoint, QRectF, Qt, QTimer, QVariantAnimation, QUrl, \
    pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFontDatabase, QDesktopServices, QFontMetrics, \
    QPainter, QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStyle,
                             QVBoxLayout, QWidget)

aqt = types.ModuleType('aqt')
aqt.mw = types.SimpleNamespace()
qt = types.ModuleType('aqt.qt')
for name in ('QObject', 'QTimer', 'Qt', 'pyqtSignal', 'QEvent', 'QRectF', 'QVariantAnimation',
             'QUrl', 'QColor', 'QPainter', 'QDesktopServices', 'QMenu', 'QMessageBox', 'QCursor',
             'QFontMetrics', 'QApplication', 'QComboBox', 'QDialog', 'QHBoxLayout', 'QLabel',
             'QLineEdit', 'QPushButton', 'QScrollArea', 'QStyle', 'QVBoxLayout', 'QWidget'):
    setattr(qt, name, globals()[name])
sys.modules['aqt'] = aqt
sys.modules['aqt.qt'] = qt
package = types.ModuleType('zotero_global_capture')
package.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                                 'anki-global-addon', 'zotero_global_capture'))]
sys.modules['zotero_global_capture'] = package

from zotero_global_capture.review_popup import ReviewDialog

app = QApplication([])
for _font in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(_font)
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'
aqt.mw.isActiveWindow = lambda: False
aqt.mw.isMinimized = lambda: False

CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_hint_audio': False,
       'review_theme': 'dark', 'review_position': 'center', 'review_plan_mode': 'fixed',
       'review_batch_size': 10, 'model': '四六级单词模板', 'deck': 'Literature'}

MEANING = 'n.（小）虾，河虾，褐虾'
QUESTIONS = {
    'choice 英文选中文': {'mode': 'choice', 'word': 'shrimp', 'meaning': MEANING,
                          'options': ['n. 协同因素；系数，率', MEANING, 'n. 详细检查，仔细观察',
                                      'n. 唯心主义；理想主义'],
                          'phonetic': 'ʃrmp', 'example': '', 'literature': ''},
    'reverse 中文选英文': {'mode': 'reverse', 'word': 'shrimp', 'meaning': MEANING,
                          'options': ['coefficient', 'shrimp', 'examination', 'idealism'],
                          'phonetic': 'ʃrɪmp', 'example': '', 'literature': ''},
    'judgment 释义判断': {'mode': 'judgment', 'word': 'shrimp', 'meaning': MEANING,
                        'options': ['正确', '错误'], 'judgment_statement': 'n. 协同因素；系数，率',
                        'judgment_correct': False, 'phonetic': 'ʃrɪmp', 'example': '',
                        'literature': ''},
    'typing 释义拼写': {'mode': 'typing', 'word': 'shrimp', 'meaning': MEANING,
                       'phonetic': 'ʃrɪmp', 'example': '', 'literature': '', 'options': []},
    'cloze 例句填空': {'mode': 'cloze', 'word': 'shrimp', 'meaning': MEANING,
                      'cloze': 'The ___ was small.', 'answer_form': 'shrimp',
                      'example': 'The shrimp was small.', 'literature': '', 'options': [],
                      'phonetic': 'ʃrɪmp'},
    'listening 听音拼写': {'mode': 'listening', 'word': 'shrimp', 'meaning': MEANING,
                         'phonetic': 'ʃrɪmp', 'example': '', 'literature': '', 'options': []},
    'speaking 口语回忆': {'mode': 'speaking', 'word': 'shrimp', 'meaning': MEANING,
                         'phonetic': 'ʃrɪmp', 'example': '', 'literature': '', 'options': []},
}

SPOKEN = []
GRADED = []
MASTERED = []
ReviewDialog.speak_many = lambda self, texts: SPOKEN.append(tuple(texts)) or True
ReviewDialog.start_grade = lambda self, ease: GRADED.append(ease)


def press_key(widget, key, modifiers=Qt.KeyboardModifier.NoModifier):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))
    app.processEvents()


def press_key_full(widget, key, modifiers=Qt.KeyboardModifier.NoModifier):
    """Press AND release: a QPushButton activates on the release, so a press-only probe
    under-reports exactly the case that matters here."""
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyRelease, key, modifiers))
    app.processEvents()


def press(widget):
    """Send a real Enter key press to the widget that currently has focus."""
    press_key_full(widget, Qt.Key.Key_Return)


def press_space(widget):
    press_key_full(widget, Qt.Key.Key_Space)


def state_of(dialog):
    return {'答案面': dialog.answer_shown, '回看题目': dialog.showing_front,
            '已发音': bool(SPOKEN), '已评分': GRADED or None, '已挂起': bool(MASTERED),
            '提示次数': dialog.hint_uses, '字母格': ''.join(box.text() for box in
                                                        getattr(dialog, 'letter_boxes', []) or [])}


for label, question in QUESTIONS.items():
    del SPOKEN[:], GRADED[:], MASTERED[:]
    base = {'kind': 'new', 'card_id': 1, 'meaning': MEANING, 'options': [], 'example': '',
            'literature': '', 'phonetic': '', 'word': 'shrimp'}
    dialog = ReviewDialog(dict(base, **question), 'center', lambda *_a: None, dict(CFG))
    dialog.mastered.connect(lambda _d=dialog: MASTERED.append(_d.question['mode']))
    dialog.resize(510, 630)
    dialog.show()
    app.processEvents()
    print('== %s ==' % label)
    focused = dialog.focusWidget()
    press(focused or dialog)
    print('   题目面 Enter → %s（焦点 %s）'
          % (state_of(dialog), type(focused).__name__ if focused else None))
    del SPOKEN[:], GRADED[:], MASTERED[:]
    focused = dialog.focusWidget()
    press_space(focused or dialog)
    print('   题目面 Space → %s（焦点 %s）'
          % (state_of(dialog), type(focused).__name__ if focused else None))
    if not dialog.answer_shown:
        dialog.reveal(True)
        app.processEvents()
    del SPOKEN[:], GRADED[:], MASTERED[:]
    focused = dialog.focusWidget()
    press(focused or dialog)
    print('   答案面 Enter → %s（焦点 %s）'
          % (state_of(dialog), type(focused).__name__ if focused else None))
    del SPOKEN[:], GRADED[:], MASTERED[:]
    focused = dialog.focusWidget()
    press_space(focused or dialog)
    print('   答案面 Space → %s（焦点 %s）'
          % (state_of(dialog), type(focused).__name__ if focused else None))
    if dialog.answer_shown and question['mode'] not in ('speaking',):
        dialog.show_front_face(True)
        app.processEvents()
        del SPOKEN[:], GRADED[:], MASTERED[:]
        focused = dialog.focusWidget()
        press_space(focused or dialog)
        print('   答案面 F 回看题目 Space → %s（焦点 %s）'
              % (state_of(dialog), type(focused).__name__ if focused else None))
    dialog.deleteLater()
    app.processEvents()
    print()


for label, word in (('typing 释义拼写', 'shrimp'), ('cloze 例句填空', 'shrimp')):
    question = QUESTIONS[label]
    del SPOKEN[:], GRADED[:], MASTERED[:]
    base = {'kind': 'new', 'card_id': 1, 'meaning': MEANING, 'options': [], 'example': '',
            'literature': '', 'phonetic': '', 'word': 'shrimp'}
    dialog = ReviewDialog(dict(base, **question), 'center', lambda *_a: None, dict(CFG))
    dialog.resize(510, 630)
    dialog.show()
    app.processEvents()
    dialog.reveal(True)
    app.processEvents()
    dialog.show_front_face(True)
    app.processEvents()
    box = dialog.letter_boxes[0]
    box.setFocus()
    app.processEvents()
    before = (dialog.showing_front, box.text())
    press_key(box, Qt.Key.Key_F)
    print('== 回看题目时往字母格打 f（%s）==' % label)
    print('   前：回看=%s 格内容=%r  →  后：回看=%s 格内容=%r'
          % (before[0], before[1], dialog.showing_front, box.text()))
    press_key(box, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier)
    print('   再按 Shift+F：回看=%s 格内容=%r' % (dialog.showing_front, box.text()))
    dialog.deleteLater()
    app.processEvents()
    print()
