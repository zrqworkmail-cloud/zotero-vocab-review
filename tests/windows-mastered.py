import os,sys,types,threading,time
base=r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
dll_dirs=[os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin')),os.add_dll_directory(os.path.dirname(base))]
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
from PyQt6.QtCore import QObject,QTimer,Qt,pyqtSignal,QEasingCurve,QEvent,QRectF,QVariantAnimation,QUrl,QPoint
from PyQt6.QtGui import QCursor,QFont,QFontDatabase,QFontMetrics,QColor,QPainter,QDesktopServices
from PyQt6.QtWidgets import QApplication,QComboBox,QDialog,QHBoxLayout,QLabel,QLineEdit,QMenu,QMessageBox,QPushButton,QScrollArea,QStyle,QVBoxLayout,QWidget
aqt=types.ModuleType('aqt');aqt.mw=types.SimpleNamespace()
qt=types.ModuleType('aqt.qt')
for n in ('QObject','QTimer','Qt','pyqtSignal','QEasingCurve','QEvent','QRectF','QVariantAnimation','QUrl','QColor','QPainter','QDesktopServices','QMenu','QMessageBox','QCursor','QFontMetrics','QApplication','QComboBox','QDialog','QHBoxLayout','QLabel','QLineEdit','QPushButton','QScrollArea','QStyle','QVBoxLayout','QWidget'): setattr(qt,n,globals()[n])
sys.modules['aqt']=aqt;sys.modules['aqt.qt']=qt
package=types.ModuleType('zotero_global_capture');package.__path__=[os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'anki-global-addon', 'zotero_global_capture'))];sys.modules['zotero_global_capture']=package
from zotero_global_capture.review_popup import ReviewDialog, DesktopReviewController
from zotero_global_capture import review_popup as rp


from PyQt6.QtTest import QTest
app=QApplication([])
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

cfg={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
     'review_theme':'light','review_position':'center','review_plan_mode':'fixed','review_batch_size':1,
     'model':'四六级单词模板','deck':'Literature'}

def card(cid, word, meaning):
    return {'kind':'new','card_id':cid,'mode':'typing','word':word,'meaning':meaning,
            'example':'','literature':'','options':[],'snapshot':{}}

# The next card is already prepared, so mastering rolls straight on to it.
real_prepare=rp.prepare_question
rp.prepare_question=lambda api, config, mode='mixed', rng=None, due_only=False: card(98,'later','稍后')
rp.collection_plan=lambda api, config, *a, **k: {'batch':1,'new_remaining':1,'goal':10,'done':1,'due':0}

def controller(notes, calls, gate=None):
    def api(action, params=None):
        calls.append((action, params or {}))
        if action == 'cardsInfo':
            return [{'cardId': params['cards'][0], 'note': 7}]
        if action == 'suspend' and gate is not None:
            gate.wait(5)
        return True
    ctl=DesktopReviewController(lambda:cfg, api, lambda message,*a: notes.append(str(message)), lambda *a:None)
    ctl._lookup_known_words=lambda *a:None;ctl._lookup_relations=lambda *a:None;ctl.schedule=lambda **kw:None
    # A group of three: mastering one card must not look like the end of the session.
    ctl.session_target=3
    return ctl

# 1. The button is a short one, sitting right of 很容易 in the rating row.
notes=[];calls=[]
ctl=controller(notes, calls)
ctl._prepared(card(99,'yield','出产'), None, ctl.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
dialog=ctl.dialog
assert not dialog.mastered_button.isVisible(),'it belongs to the rating row, which is hidden until the answer'
dialog.reveal(True);app.processEvents();QTest.qWait(60)
assert dialog.mastered_button.isVisible(),'the card needs a 已掌握 action'
assert dialog.mastered_button.text()=='E. Mastered',dialog.mastered_button.text()
row=dialog.grade_widget.layout()
assert dialog.mastered_button.parent() is dialog.grade_widget,dialog.mastered_button.parent()
assert row.indexOf(dialog.mastered_button)==row.indexOf(dialog.grade_buttons[3])+1,row.indexOf(dialog.mastered_button)

# 1b. A flawless spelling is the one answer that means "already known": the card
#     recommends Mastered, and Enter does exactly that instead of grading.
clean_notes=[];clean_calls=[]
clean=controller(clean_notes, clean_calls)
clean._prepared(card(90,'agile','敏捷的'), None, clean.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
spelling=clean.dialog
spelling.reveal(True);app.processEvents();QTest.qWait(60)
assert spelling.enter_mastered,'a clean typing answer must recommend mastering'
assert '建议 Mastered' in spelling.status.text(),spelling.status.text()
assert spelling.mastered_button.objectName()=='suggestMastered',spelling.mastered_button.objectName()
assert not any(button.objectName()=='suggest' for button in spelling.grade_buttons),\
    'Easy must not look recommended while Mastered is'
QTest.keyClick(spelling, Qt.Key.Key_Return);app.processEvents();QTest.qWait(150);app.processEvents()
assert 'suspend' in [action for action,_ in clean_calls],'Enter must do what the line recommended'
assert 'guiAnswerCard' not in [action for action,_ in clean_calls],\
    'Enter on a flawless spelling recorded a rating instead of mastering: %s' % [a for a,_ in clean_calls]

# 1c. Recognition questions earn the same thing only when the answer was instant: inside
#     three seconds they recommend Mastered, after that just Easy. 判断题 never earns it,
#     however fast, because two options make a right answer a coin flip.
choice_notes=[]
ctl3=controller(choice_notes, [])
ctl3._prepared(dict(card(91,'passive','被动的'), mode='choice', options=['被动的','积极的','中性的','混合的']),
               None, ctl3.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
choice=ctl3.dialog
choice.reveal(True);app.processEvents();QTest.qWait(60)
assert choice.enter_mastered and choice.answer_seconds is not None and choice.answer_seconds <= 3.0, \
    (choice.enter_mastered, choice.answer_seconds)
assert '用时' in choice.status.toolTip(),choice.status.toolTip()
choice.close();app.processEvents()
ctl4=controller(choice_notes, [])
ctl4._prepared(dict(card(92,'active','积极的'), mode='choice', options=['被动的','积极的','中性的','混合的']),
               None, ctl4.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
slow=ctl4.dialog
slow.shown_at=time.monotonic()-5
slow.reveal(True);app.processEvents();QTest.qWait(60)
assert not slow.enter_mastered,'a 5 second pick is not proof the word is already known'
assert slow.enter_ease==4,slow.enter_ease
slow.close();app.processEvents()
ctl5=controller(choice_notes, [])
ctl5._prepared(dict(card(93,'obliged','有义务的'), mode='judgment', judgment_correct=True,
                    judgment_statement='有义务的；使感激', options=[]),
               None, ctl5.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
judge=ctl5.dialog
judge.reveal(True);app.processEvents();QTest.qWait(60)
assert not judge.enter_mastered,'a two-option question can never earn mastering'
judge.close();app.processEvents()

# 2. Clicking it must not do the Anki work on the UI thread, and must keep the session going.
gate=threading.Event()
ctl2=controller(notes, calls, gate)
ctl2._prepared(card(94,'nimble','敏捷的'), None, ctl2.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
blocked=ctl2.dialog
blocked.reveal(True);app.processEvents();QTest.qWait(60)
assert [a for a,_ in calls].count('suspend')==0,'nothing is suspended before the user says so'
blocked.mastered_button.click()
for _ in range(200):
    app.processEvents(); QTest.qWait(5)
    if ('suspend',{'cards':[94]}) in calls: break
assert ('suspend',{'cards':[94]}) in calls,'the request should be in flight: %s' % calls
assert ctl2.dialog is blocked,'the UI must not wait for Anki to answer before it returns'
for _ in range(20):
    app.processEvents(); QTest.qWait(5)
gate.set()
for _ in range(240):
    app.processEvents(); QTest.qWait(5)
    if ctl2.dialog is not blocked: break
assert ('addTags',{'notes':[7],'tags':'zvr_mastered'}) in calls,calls
assert 'answerCards' not in [a for a,_ in calls],'mastering must not write a rating'
assert any('已掌握' in n for n in notes),notes
assert any('zvr_mastered' in n for n in notes),'the message has to say how to undo it: %s' % notes
assert ctl2.dialog is not blocked and ctl2.dialog.question['card_id']==98,(ctl2.dialog is blocked, ctl2.dialog.question['card_id'])
# Mastering must read like a rating: the next card paints into the same window, it does
# not close this one and reopen a new window a second later.
assert getattr(ctl2.dialog, '_embedded', False), 'the next card must be handed over in place'
assert ctl2.dialog.window() is blocked, (ctl2.dialog.window(), blocked)
assert blocked.isVisible() and ctl2.dialog.isVisible()
ctl2.stop();app.processEvents()

# 3. E is the shortcut on the answer face.
notes=[];calls=[]
ctl=controller(notes, calls)
ctl._prepared(card(97,'difficult','困难的'), None, ctl.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
rated=ctl.dialog
rated.reveal(True);app.processEvents();QTest.qWait(60)
QTest.keyClick(rated, Qt.Key.Key_E)
QTest.qWait(150);app.processEvents();QTest.qWait(150)
assert ('suspend',{'cards':[97]}) in calls,calls
assert ctl.dialog is not rated
ctl.stop();app.processEvents()

# 4. In the spelling card the letter E still belongs to the answer box.
notes=[];calls=[]
ctl=controller(notes, calls)
ctl._prepared(card(96,'eager','渴望的'), None, ctl.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
spelling=ctl.dialog
spelling.letter_boxes[0].setFocus()
QTest.keyClick(spelling.letter_boxes[0], Qt.Key.Key_E)
app.processEvents()
assert spelling.letter_boxes[0].text()=='e',spelling.letter_boxes[0].text()
assert [a for a,_ in calls].count('suspend')==0,'typing an E must not master the word'
ctl.stop();app.processEvents()

# 5. A clean spelling is the strongest evidence the card can get, so it recommends
#    mastering; the underlying rating still reaches Easy for the weaker question types.
notes=[];calls=[]
ctl=controller(notes, calls)
ctl._prepared(card(95,'difficult','困难的'), None, ctl.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
second=ctl.dialog
for box,char in zip(second.letter_boxes,'difficult'): box.setText(char)
second.check_input();app.processEvents();QTest.qWait(60)
assert second.answer_shown and second.enter_ease==4,(second.answer_shown,second.enter_ease)
assert second.enter_mastered,'a flawless spelling must recommend mastering'
assert '建议 Mastered' in second.status.text(),second.status.text()
assert not [n for n in notes if '保存' in n or '没有' in n],notes
ctl.stop();app.processEvents()
rp.prepare_question=real_prepare

print('Qt: 已掌握 sits in the rating row on E, works off the UI thread, and rolls on to the next card')
