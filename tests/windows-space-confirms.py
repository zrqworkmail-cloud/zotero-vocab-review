"""Hearing the word on a 选择题/判断题 — without turning the key into an answer.

The learner asked for pronunciation on the choice card (2026-11-05). The word is already
printed there, so playing it tells him nothing he did not have; what it does help with is
the ear. That distinction is what these checks hold in place:

* 英文选中文 and 单词释义判断 get Enter + a clickable speaker, and neither counts as a hint
  (a hint would bend the suggested rating for hearing a word that is on the screen).
* 中文选英文 does NOT: there the English word *is* the answer, so speaking it is answering.
* A–D and clicking still answer the card, and Enter still does not select an option.
"""
import os,sys,types
base=r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin'))
os.add_dll_directory(os.path.dirname(base))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
from PyQt6.QtCore import QObject,QTimer,Qt,pyqtSignal,QEasingCurve,QEvent,QRectF,QVariantAnimation,QUrl,QPoint
from PyQt6.QtGui import QCursor,QFont,QFontDatabase,QFontMetrics,QColor,QPainter,QDesktopServices,QKeyEvent
from PyQt6.QtWidgets import QApplication,QComboBox,QDialog,QHBoxLayout,QLabel,QLineEdit,QMenu,QMessageBox,QPushButton,QScrollArea,QStyle,QVBoxLayout,QWidget
aqt=types.ModuleType('aqt');aqt.mw=types.SimpleNamespace()
qt=types.ModuleType('aqt.qt')
for n in ('QObject','QTimer','Qt','pyqtSignal','QEasingCurve','QEvent','QRectF','QVariantAnimation','QUrl','QColor','QPainter','QDesktopServices','QMenu','QMessageBox','QCursor','QFontMetrics','QApplication','QComboBox','QDialog','QHBoxLayout','QLabel','QLineEdit','QPushButton','QScrollArea','QStyle','QVBoxLayout','QWidget'): setattr(qt,n,globals()[n])
sys.modules['aqt']=aqt;sys.modules['aqt.qt']=qt
package=types.ModuleType('zotero_global_capture');package.__path__=[os.path.abspath(os.path.join(os.path.dirname(__file__),'..','anki-global-addon','zotero_global_capture'))];sys.modules['zotero_global_capture']=package
from zotero_global_capture.review_popup import ReviewDialog
from PyQt6.QtTest import QTest

app=QApplication([])
for f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(f)
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

CFG={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
     'review_theme':'dark','review_position':'center','review_plan_mode':'fixed',
     'review_batch_size':10,'model':'四六级单词模板','deck':'Literature'}
MEANING='adj. 危险的；冒险的'
OPTIONS=['adj. 量的；定量的','adj. 危险的；冒险的','adj. 外部的；对外的','adj. 口头的；口的']

SPOKEN=[]
ReviewDialog.speak_many=lambda self,texts: SPOKEN.append(tuple(texts)) or True


# ---------------------------------------------------------------------------
# Space on the answer face must mean "take the rating this card just
# recommended", the same thing Enter means, and must stop meaning "whatever
# button happens to hold focus" (measured 2026-11-05: it clicked Mastered on one
# question type and the speaker on another).  During a look-back (F) neither key
# may answer the card.
GRADED = []
MASTERED = []


def built(mode, word='hazardous'):
    question = {'kind': 'due', 'card_id': 1, 'mode': mode, 'word': word, 'meaning': MEANING,
                'example': '', 'literature': '', 'options': OPTIONS, 'phonetic': 'hae'}
    if mode == 'judgment':
        question.update(options=['A', 'B'], judgment_statement=MEANING, judgment_correct=True)
    dialog = ReviewDialog(question, 'center', lambda *a: GRADED.append(a), dict(CFG))
    dialog.mastered.connect(lambda _d: MASTERED.append(mode))
    dialog.show(); QTest.qWait(60); app.processEvents()
    return dialog


def to_answer(dialog, mode):
    if mode in ('typing', 'cloze', 'listening'):
        for box, pair in zip(dialog.letter_boxes, dialog.letter_positions):
            box.setText(pair[1])
        dialog.check_input()
    else:
        dialog.reveal(True)
    app.processEvents(); QTest.qWait(40); app.processEvents()
    assert dialog.answer_shown, ('answer face expected', mode)


def outcome(mode, key, look_back=False):
    """One card, one key: what the card did, plus what it said it would do."""
    dialog = built(mode)
    to_answer(dialog, mode)
    suggested = (dialog.enter_ease, dialog.enter_mastered)
    if look_back:
        QTest.keyClick(dialog, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier)
        app.processEvents(); QTest.qWait(40)
        assert dialog.showing_front, ('Shift+F must show the question again', mode)
    del GRADED[:]; del MASTERED[:]; del SPOKEN[:]
    QTest.keyClick(dialog.focusWidget() or dialog, key)
    app.processEvents(); QTest.qWait(40); app.processEvents()
    result = {'graded': [entry[-1] for entry in GRADED], 'mastered': bool(MASTERED),

              'spoken': bool(SPOKEN),
              'front': dialog.showing_front, 'suggested': suggested}
    dialog.deleteLater(); QTest.qWait(40)
    return result


for mode in ('choice', 'reverse', 'judgment', 'typing', 'cloze', 'listening'):
    enter = outcome(mode, Qt.Key.Key_Return)
    space = outcome(mode, Qt.Key.Key_Space)
    assert space['graded'] == enter['graded'] and space['mastered'] == enter['mastered'], \
        ('space must do exactly what enter does', mode, enter, space)
    ease, mastered = enter['suggested']
    if mastered:
        assert enter['mastered'] and not enter['graded'], ('Enter must suspend', mode, enter)
    elif ease is not None:
        assert enter['graded'] == [ease] and not enter['mastered'], \
            ('the suggestion and the key must agree', mode, ease, enter['graded'])
    assert len(enter['graded']) <= 1, ('one key must not grade twice (focus + rule)', mode, enter)
    assert not enter['spoken'], ('space must not fall through to the speaker', mode, enter)
    back = outcome(mode, Qt.Key.Key_Space, look_back=True)
    assert back['front'] and not back['graded'] and not back['mastered'], \
        ('a look-back answers nothing, with either key', mode, back)
    back_enter = outcome(mode, Qt.Key.Key_Return, look_back=True)
    assert back_enter['front'] and not back_enter['graded'] and not back_enter['mastered'], \
        ('enter must stay inert during a look-back too', mode, back_enter)

dialog = built('typing')
to_answer(dialog, 'typing')
assert '\u7a7a\u683c' in dialog.status.text(), \
    ('the status line has to say space confirms as well', dialog.status.text())
dialog.deleteLater(); QTest.qWait(40)

print('Qt: \u7b54\u6848\u9762\u7a7a\u683c\u4e0e\u56de\u8f66\u540c\u4e49\uff0c\u90fd\u628a\u5361\u7247\u81ea\u5df1\u7684\u5efa\u8bae\u843d\u5730\uff1b\u56de\u770b\u9898\u76ee\u65f6\u4e24\u4e2a\u952e\u90fd\u4e0d\u8bc4\u5206')
