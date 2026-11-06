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

def card(mode, word='hazardous'):
    question={'kind':'due','card_id':1,'mode':mode,'word':word,'meaning':MEANING,
              'example':'','literature':'','options':OPTIONS,'phonetic':'hɑːzədəs'}
    if mode=='judgment':
        # A judgment card is the word paired with a claim about it; the claim is what the
        # learner reads, so the builder needs it.
        question.update(options=['正确','错误'], judgment_statement=MEANING, judgment_correct=True)
    dialog=ReviewDialog(question,'center',lambda *_a:None,dict(CFG))
    dialog.show();QTest.qWait(60);app.processEvents()
    return dialog

def press_enter(dialog):
    target=dialog.focusWidget() or dialog
    QApplication.sendEvent(target,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Return,
                                           Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(target,QKeyEvent(QEvent.Type.KeyRelease,Qt.Key.Key_Return,
                                           Qt.KeyboardModifier.NoModifier))
    app.processEvents();QTest.qWait(40);app.processEvents()

# 1. 英文选中文: Enter speaks the word, and the card is still unanswered.
dialog=card('choice')
del SPOKEN[:]
press_enter(dialog)
assert SPOKEN==[('hazardous',)],('回车必须朗读单词',SPOKEN)
assert not dialog.answer_shown,'回车不许替用户作答'
assert dialog.hint_uses==0,('听自己屏幕上已经印出来的词不算提示',dialog.hint_uses)

# 2. A clickable speaker sits on the question face, same round control as everywhere else.
speakers=[widget for widget in dialog.findChildren(QPushButton)
          if widget.objectName()=='speaker' and widget.isVisible()]
assert speakers,('题目面必须有可点的喇叭', [w.objectName() for w in dialog.findChildren(QPushButton)])
del SPOKEN[:]
speakers[0].click();app.processEvents()
assert SPOKEN==[('hazardous',)],SPOKEN
assert dialog.hint_uses==0,dialog.hint_uses
assert '回车' in dialog.status.text() and '发音' in dialog.status.text(), dialog.status.text()

# 3. A–D still answer (the letter branch lives in the event filter, so the key has to be
#    delivered the way Qt delivers it), and the card must not have been answered by Enter.
assert not dialog.answer_shown, '回车不许提前翻面'
QTest.keyClick(dialog, Qt.Key.Key_B)
app.processEvents();QTest.qWait(40)
assert dialog.answer_shown and dialog.last_correct is True,(dialog.answer_shown,getattr(dialog,'last_correct',None))
dialog.deleteLater();QTest.qWait(40)

# 4. 单词释义判断 gets the same treatment.
dialog=card('judgment')
del SPOKEN[:]
press_enter(dialog)
assert SPOKEN==[('hazardous',)],SPOKEN
assert not dialog.answer_shown
dialog.deleteLater();QTest.qWait(40)

# 5. 中文选英文 must stay silent: there the English word IS the answer.
dialog=card('reverse')
del SPOKEN[:]
press_enter(dialog)
assert SPOKEN==[],('反向题念出来就是给答案',SPOKEN)
assert not dialog.answer_shown
assert not [widget for widget in dialog.findChildren(QPushButton)
            if widget.objectName()=='speaker' and widget.isVisible()],\
    '反向题题目面不许有喇叭'
dialog.deleteLater();QTest.qWait(40)

# 6. The answer face keeps speaking on its own schedule: the new front-face speaker must not
#    double-up when the auto-read is on.
cfg=dict(CFG); cfg['review_auto_word']=True
dialog=ReviewDialog({'kind':'due','card_id':2,'mode':'choice','word':'hazardous',
                     'meaning':MEANING,'example':'','literature':'','options':OPTIONS,
                     'phonetic':'hɑːzədəs'},'center',lambda *_a:None,cfg)
dialog.show();QTest.qWait(60);app.processEvents()
del SPOKEN[:]
dialog.reveal(True);app.processEvents()
assert SPOKEN==[('hazardous',)],SPOKEN
print('Qt: 选中文/判断题题目面可回车朗读且不计提示，反向题保持安静，答案面照旧')
