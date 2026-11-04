import os,sys,types
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


from PyQt6.QtTest import QTest
app=QApplication([])
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

cfg={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
     'review_theme':'light','review_position':'center','review_plan_mode':'fixed','review_batch_size':2,
     'model':'四六级单词模板','deck':'Literature'}

def session(card_id):
    """A controller mid-session, with one card on screen and a group boundary reached."""
    ctl=DesktopReviewController(lambda:cfg, lambda *a:None, lambda *a:None, lambda *a:None)
    ctl._lookup_known_words=lambda *a:None;ctl._lookup_relations=lambda *a:None;ctl.schedule=lambda **kw:None
    ctl.session_target=2;ctl.session_seen={card_id};ctl.session_words={'first'}
    card={'kind':'due','card_id':card_id,'mode':'typing','word':'first','meaning':'一','example':'','literature':'','options':[],'snapshot':{}}
    dialog=ReviewDialog(card,'center',ctl._grade,cfg)
    ctl.dialog=dialog;ctl.review_host=dialog;dialog.finished.connect(ctl._closed)
    dialog.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
    return ctl, dialog

NEXT={'kind':'due','card_id':12,'mode':'typing','word':'second','meaning':'二','example':'','literature':'','options':[],'snapshot':{}}

# 1. The group boundary is now a choice: a countdown appears, and nothing else moves.
ctl, dialog = session(11)
ctl._graded(dialog, None, ctl.generation, (dict(NEXT), None, 3, True, None))
QTest.qWait(60);app.processEvents();QTest.qWait(60)
break_dialog=ctl.break_dialog
assert break_dialog is not None and break_dialog.isVisible(),'the end of a group must be announced'
# The countdown is a panel inside the card window, not a second popup beside it: the user
# asked for the switch to feel like one window the whole time.
assert break_dialog.parent() is dialog.window(),break_dialog.parent()
assert not break_dialog.isWindow(),'the break must not be its own top-level window'
assert break_dialog.geometry()==dialog.window().rect(),(break_dialog.geometry(), dialog.window().rect())
assert break_dialog.count_label.text()=='3',break_dialog.count_label.text()
assert '下一组' in break_dialog.hint.text(),break_dialog.hint.text()
assert ctl.dialog is dialog,'the next group must not start before the user agrees'

# Enter continues into the next group.
QTest.keyClick(break_dialog, Qt.Key.Key_Return);QTest.qWait(60);app.processEvents();QTest.qWait(60)
assert ctl.break_dialog is None
assert ctl.dialog is not dialog and ctl.dialog.question['card_id']==12,(ctl.dialog is dialog, getattr(ctl.dialog,'question',None))
assert ctl.session_target==3 and ctl.session_seen==set(),(ctl.session_target,ctl.session_seen)

# 2. Doing nothing is answering: the countdown expires and the session ends.
ctl2, dialog2 = session(21)
ctl2._graded(dialog2, None, ctl2.generation, (dict(NEXT, card_id=22), None, 3, True, None))
QTest.qWait(60);app.processEvents()
for _ in range(900):
    app.processEvents();QTest.qWait(5)
    if ctl2.break_dialog is None:break
else:
    raise AssertionError('the countdown never expired')
assert ctl2.dialog is None,'a finished session must close the card'
assert ctl2.session_seen=={21},ctl2.session_seen
assert not ctl2.prepared_next,ctl2.prepared_next

# 3. The prompt has to be readable at a glance (user 2026-11-04: 把字弄的大一点醒目一点).
#    It is the one line that decides whether the session continues, so it cannot share the
#    12px grey used for ordinary status text.
ctl3, dialog3 = session(31)
ctl3._graded(dialog3, None, ctl3.generation, (dict(NEXT, card_id=32), None, 3, True, None))
QTest.qWait(60);app.processEvents();QTest.qWait(60)
panel=ctl3.break_dialog
assert 'Enter' in panel.hint.text() and '下一组' in panel.hint.text(),panel.hint.text()
# font() carries the stylesheet-resolved font here; fontInfo() reports a meaningless
# -0.75pt under the offscreen platform, which would make the assertion pass on nothing.
hint_px=QFontMetrics(panel.hint.font()).horizontalAdvance('按')
assert hint_px>=18,('the Enter prompt must be big enough to read at a glance',hint_px,panel.hint.styleSheet())
assert panel.hint.font().weight()>=QFont.Weight.Bold.value,('bold',panel.hint.font().weight())
QTest.keyClick(panel, Qt.Key.Key_Return);QTest.qWait(60);app.processEvents();QTest.qWait(60)
assert ctl3.break_dialog is None and ctl3.dialog.question['card_id']==32

# 4. Enter must work no matter where the keyboard focus sat before the break. The panel
#    covers the card, but the letter boxes underneath are still live widgets: a QLineEdit
#    keeps the focus chain and swallows Enter, which makes the prompt a lie. So the panel
#    has to own the focus, and the boxes behind it must not be able to take it back.
ctl4, dialog4 = session(41)
dialog4.letter_boxes[0].setFocus(Qt.FocusReason.OtherFocusReason);QTest.qWait(40);app.processEvents()
assert dialog4.window().focusWidget() is dialog4.letter_boxes[0]
ctl4._graded(dialog4, None, ctl4.generation, (dict(NEXT, card_id=42), None, 3, True, None))
QTest.qWait(60);app.processEvents();QTest.qWait(60)
assert ctl4.break_dialog is not None
assert dialog4.window().focusWidget() is ctl4.break_dialog,('the panel must hold the keyboard',
    type(dialog4.window().focusWidget()).__name__)
assert not any(box.isEnabled() for box in dialog4.letter_boxes),\
    'the boxes behind the panel must not be able to steal Enter back'
QTest.keyClick(ctl4.break_dialog, Qt.Key.Key_Return);QTest.qWait(60);app.processEvents();QTest.qWait(60)
assert ctl4.break_dialog is None,('Enter on the focused panel must continue the group',
                                  ctl4.break_dialog)
assert ctl4.dialog is not dialog4 and ctl4.dialog.question['card_id']==42
print('Qt: the break prompt is bold and legible, and it holds the keyboard')

