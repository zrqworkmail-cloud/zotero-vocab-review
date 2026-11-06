import os,sys,types
base=r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
dll_dirs=[os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin')),os.add_dll_directory(os.path.dirname(base))]
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
from PyQt6.QtCore import QObject,QTimer,Qt,pyqtSignal,QEvent,QRectF,QVariantAnimation,QUrl,QPoint,QEasingCurve
from PyQt6.QtGui import QCursor,QFont,QFontDatabase,QFontMetrics,QColor,QPainter,QDesktopServices
from PyQt6.QtWidgets import QApplication,QComboBox,QDialog,QHBoxLayout,QLabel,QLineEdit,QMenu,QMessageBox,QPushButton,QScrollArea,QStyle,QVBoxLayout,QWidget
aqt=types.ModuleType('aqt');aqt.mw=types.SimpleNamespace()
qt=types.ModuleType('aqt.qt')
for n in ('QObject','QTimer','Qt','pyqtSignal','QEasingCurve','QEvent','QRectF','QVariantAnimation','QUrl','QColor','QPainter','QDesktopServices','QMenu','QMessageBox','QCursor','QFontMetrics','QApplication','QComboBox','QDialog','QHBoxLayout','QLabel','QLineEdit','QPushButton','QScrollArea','QStyle','QVBoxLayout','QWidget'): setattr(qt,n,globals()[n])
sys.modules['aqt']=aqt;sys.modules['aqt.qt']=qt
package=types.ModuleType('zotero_global_capture');package.__path__=[os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'anki-global-addon', 'zotero_global_capture'))];sys.modules['zotero_global_capture']=package
from zotero_global_capture.review_popup import ReviewDialog
from PyQt6.QtTest import QTest
app=QApplication([])
for _f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(_f)
ReviewDialog.speak_many = lambda self, texts: True

cfg = {'review_auto_word': False, 'review_auto_example': False, 'review_auto_example_mode': 'off',
       'review_hint_audio': False, 'review_theme': 'dark', 'review_position': 'center'}


def card(word, meaning='v. 使…'):
    dialog = ReviewDialog({'kind': 'due', 'card_id': 7, 'mode': 'typing', 'word': word,
                           'meaning': meaning, 'example': '', 'literature': '', 'options': []},
                          'center', lambda *_a: None, cfg)
    dialog.show()
    QTest.qWait(60); app.processEvents()
    return dialog


def spell_right(dialog):
    """Type the word perfectly into the boxes and submit, the way the learner does."""
    for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText(expected)
    dialog.check_input()
    app.processEvents(); QTest.qWait(40)
    assert dialog.answer_shown, 'a correct spelling must reveal the answer'
    return dialog


def evidence(dialog):
    """Where the accounting lives now.

    On 2026-11-05 the learner asked for the status row to stop eating two lines, so the
    counts moved into its tooltip and the row keeps only the suggestion and the keys. These
    checks follow the evidence rather than asserting on a string nobody can see any more.
    """
    return dialog.status.toolTip()


# 1. Baseline of the user's rule: 一次性写对、没碰提示 → the card recommends Mastered.
dialog = spell_right(card('characteristic'))
assert dialog.enter_mastered is True and dialog.enter_ease == 4, (dialog.enter_mastered, dialog.enter_ease)
# 「无提示」 is evidence, not a zero count, so it still exists — but the row is short now
# and the evidence lives in its tooltip (learner's choice, 2026-11-05).
assert '无提示' in dialog.status.toolTip(), dialog.status.toolTip()
assert '建议 Mastered' in dialog.status.text(), dialog.status.text()

# 2. One listen is nearly free: 用户点名它应当仍然建议 Easy, and it is no longer Mastered.
dialog = card('characteristic')
dialog.hear_hint(['characteristic'])
spell_right(dialog)
assert dialog.enter_mastered is False, 'a hint, however light, is not a blind recall'
assert dialog.enter_ease == 4, ('one audio hint stays Easy', dialog.enter_ease)
assert '发音提示 1 次' in evidence(dialog), evidence(dialog)
assert '建议 Easy' in dialog.status.text(), dialog.status.text()

# 3. Two listens drop to Good, three to Hard.
for presses, expected in ((2, 3), (3, 2), (5, 2)):
    dialog = card('characteristic')
    for _ in range(presses):
        dialog.hear_hint(['characteristic'])
    spell_right(dialog)
    assert dialog.enter_ease == expected, (presses, dialog.enter_ease, expected)

# 4. A letter hint is priced by where it sits. The first letter of a 14-letter word is a
#    third of the word's information → Good; the same single hint on a 5-letter word is
#    nearly half → Hard. A plain count could never tell those apart.
dialog = card('characteristic')
dialog.add_hint()
spell_right(dialog)
assert dialog.enter_ease == 3, ('first letter of a long word', dialog.enter_ease)
assert '字母提示 1/14' in evidence(dialog) and '31%' in evidence(dialog), evidence(dialog)
assert '建议 Good' in dialog.status.text(), dialog.status.text()

dialog = card('drive')
dialog.add_hint()
spell_right(dialog)
assert dialog.enter_ease == 2, ('first letter of a short word', dialog.enter_ease)
assert '44%' in evidence(dialog), evidence(dialog)

# 5. More letters given away can only make it worse, never better.
shares = []
for step in range(1, 4):
    probe = card('characteristic')
    for _ in range(step):
        probe.add_hint()
    spell_right(probe)
    shares.append(probe.enter_ease)
assert shares == sorted(shares, reverse=True) and len(set(shares)) > 1, shares

# 6. 例句提示仍然按 Hard 地板算，而一次写错的字母会把"只用过发音"的好局拖下来一档。
dialog = card('characteristic')
dialog.show_example_hint('He had a characteristic smile.')
spell_right(dialog)
assert dialog.enter_ease == 2, ('example hint', dialog.enter_ease)
assert '释义/例句提示 1 次' in evidence(dialog), evidence(dialog)

dialog = card('characteristic')
dialog.hear_hint(['characteristic'])
dialog.letter_boxes[0].setText('x')          # 打错一个字母，随后自己改回来
dialog.letter_boxes[0].setText('c')
spell_right(dialog)
assert (dialog.incorrect_letters, dialog.failed_attempts) == (1, 0), evidence(dialog)
assert dialog.enter_ease == 3, ('a corrected slip costs Good, not Hard', dialog.enter_ease)

dialog = card('characteristic')
dialog.hear_hint(['characteristic'])
for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
    box.setText(expected)
dialog.letter_boxes[0].setText('x')
dialog.check_input()                          # 提交过一次，没全对
assert dialog.failed_attempts == 1, dialog.status.text()
dialog.letter_boxes[0].setText('c')
spell_right(dialog)
assert dialog.enter_ease == 2, ('a failed check is Hard whatever the hints were', dialog.enter_ease)

# 7. Non-spelling cards report a press count, so their ladder must not change today.
dialog = ReviewDialog({'kind': 'due', 'card_id': 8, 'mode': 'choice', 'word': 'develop',
                       'meaning': 'v. 发展', 'example': '', 'literature': '',
                       'options': ['develop', 'devote', 'involve', 'improve']},
                      'center', lambda *_a: None, cfg)
dialog.show(); QTest.qWait(60); app.processEvents()
dialog.hear_hint(['develop'])
dialog.reveal(True)
assert dialog.enter_ease == 2, ('choice card with a hint keeps Hard', dialog.enter_ease)
assert '提示 1 次' in evidence(dialog), evidence(dialog)

print('Qt: 一次发音=Easy、字母提示按位置加权、释义/例句仍是 Hard 地板，其他题型不变')
