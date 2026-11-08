"""E/已掌握 was retired on 2026-11-07: the rating row is A–D again.

The user stopped using Mastered — every old suspended card was migrated to Easy — so the
card no longer offers the button, the E key does nothing on either face, and a flawless
spelling recommends Easy like any other clean answer. The backend (mark_mastered, the
zvr_mastered tag, the setting) stays for history; this file only guards the card itself.
"""
import os,sys,types,time
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
from zotero_global_capture import review_logic as rl


from PyQt6.QtTest import QTest
app=QApplication([])
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

cfg={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
     'review_theme':'light','review_position':'center','review_plan_mode':'fixed','review_batch_size':1,
     'model':'四六级单词模板','deck':'Literature'}

def card(cid, word, meaning):
    return {'kind':'new','card_id':cid,'mode':'typing','word':word,'meaning':meaning,
            'example':'','literature':'','options':[],'snapshot':{}}

def controller(notes, calls):
    def api(action, params=None):
        calls.append((action, params or {}))
        if action == 'cardsInfo':
            return [{'cardId': params['cards'][0], 'note': 7}]
        return True
    ctl=DesktopReviewController(lambda:cfg, api, lambda message,*a: notes.append(str(message)), lambda *a:None)
    ctl._lookup_known_words=lambda *a:None;ctl._lookup_relations=lambda *a:None;ctl.schedule=lambda **kw:None
    ctl.session_target=3
    graded=[]
    # The real save path talks to Anki's scheduler; here the decision itself is the subject.
    ctl._grade=lambda dialog,ease: graded.append(ease)
    return ctl, graded

# 1. The row is four ratings, A–D, and nothing else. No button, no signal, no attribute.
notes=[];calls=[]
ctl,graded=controller(notes, calls)
ctl._prepared(card(99,'yield','出产'), None, ctl.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
dialog=ctl.dialog
dialog.reveal(True);app.processEvents();QTest.qWait(60)
row=dialog.grade_widget.layout()
texts=[row.itemAt(i).widget().text() for i in range(row.count()) if row.itemAt(i).widget()]
assert texts==['A. Again','B. Hard','C. Good','D. Easy'],texts
assert not hasattr(dialog,'mastered_button'),'the 已掌握 button is retired'
assert not hasattr(ReviewDialog,'mastered'),'no signal may reach a mastering path'
assert not hasattr(dialog,'enter_mastered'),'the suggestion is a rating again, not mastering'
assert 'A–D' in rl.ANSWER_KEY_HINT and 'A–E' not in rl.ANSWER_KEY_HINT,rl.ANSWER_KEY_HINT
ctl.stop();app.processEvents()

# 2. A flawless spelling recommends Easy, and Enter records that rating — no suspend,
#    no tag, nothing that takes the word out of the schedule.
notes=[];calls=[]
ctl,graded=controller(notes, calls)
ctl._prepared(card(90,'agile','敏捷的'), None, ctl.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
spelling=ctl.dialog
spelling.reveal(True);app.processEvents();QTest.qWait(60)
assert spelling.enter_ease==4,spelling.enter_ease
assert '建议 Easy' in spelling.status.text(),spelling.status.text()
assert 'Mastered' not in spelling.status.text(),spelling.status.text()
assert [b.objectName() for b in spelling.grade_buttons].count('suggest')==1
QTest.keyClick(spelling, Qt.Key.Key_Return);app.processEvents();QTest.qWait(150);app.processEvents()
assert graded==[4],graded
assert not [a for a,_ in calls if a in ('suspend','addTags','answerCards')],calls
ctl.stop();app.processEvents()

# 3. E is inert on the answer face: it neither rates nor suspends.
notes=[];calls=[]
ctl,graded=controller(notes, calls)
ctl._prepared(card(97,'difficult','困难的'), None, ctl.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
rated=ctl.dialog
rated.reveal(True);app.processEvents();QTest.qWait(60)
QTest.keyClick(rated, Qt.Key.Key_E)
QTest.qWait(150);app.processEvents();QTest.qWait(150)
assert graded==[],graded
assert not [a for a,_ in calls if a in ('suspend','addTags')],calls
assert rated.answer_shown and not rated.grading,'E must leave the card exactly as it was'
ctl.stop();app.processEvents()

# 4. E is inert on a choice question's front face too: it used to suspend before answering.
notes=[];calls=[]
ctl,graded=controller(notes, calls)
ctl._prepared(dict(card(91,'passive','被动的'), mode='choice', options=['被动的','积极的','中性的','混合的']),
              None, ctl.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
choice=ctl.dialog
assert not choice.answer_shown
QTest.keyClick(choice, Qt.Key.Key_E)
app.processEvents();QTest.qWait(60)
assert not choice.answer_shown and not choice.grading
assert not [a for a,_ in calls if a in ('suspend','addTags')],calls
ctl.stop();app.processEvents()

# 5. In the spelling card the letter E still belongs to the answer box.
notes=[];calls=[]
ctl,graded=controller(notes, calls)
ctl._prepared(card(96,'eager','渴望的'), None, ctl.generation, True)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
spelling=ctl.dialog
spelling.letter_boxes[0].setFocus()
QTest.keyClick(spelling.letter_boxes[0], Qt.Key.Key_E)
app.processEvents()
assert spelling.letter_boxes[0].text()=='e',spelling.letter_boxes[0].text()
assert graded==[] and not [a for a,_ in calls if a=='suspend']
ctl.stop();app.processEvents()

print('Qt: the rating row is A–D, E does nothing on either face, and a flawless spelling recommends Easy')