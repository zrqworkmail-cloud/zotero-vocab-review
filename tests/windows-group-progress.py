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

from zotero_global_capture import review_popup as rp
q={'kind':'due','mode':'typing','word':'test','meaning':'测试','example':'','literature':'','options':[],'_today_remaining':12}
d=ReviewDialog(q,'center',lambda *_:None,{'review_auto_word':False},'2 / 5');d.show();app.processEvents()
assert any('本组 2 / 5' in x.text() and '今日计划剩余：12' in x.text() for x in d.findChildren(QLabel))
d.close();app.processEvents()
# The card header has to name the slice it was drawn from.
named=ReviewDialog(dict(q),'center',lambda *_:None,{'review_auto_word':False,'review_scope_name':'四级核心'},'1 / 3')
named.show();app.processEvents()
header=next(x for x in named.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert '四级核心' in header.text() and '到期复习' in header.text(),header.text()
plain=ReviewDialog(dict(q),'center',lambda *_:None,{'review_auto_word':False,'review_scope_decks':['六级词书'],'review_scope_tags':['zvr_cet4_core']},'1 / 3')
plain.show();app.processEvents()
header=next(x for x in plain.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert '六级词书' in header.text() and 'cet4_core' in header.text() and 'zvr_' not in header.text(),header.text()
unnamed=ReviewDialog(dict(q),'center',lambda *_:None,{'review_auto_word':False},'1 / 3')
unnamed.show();app.processEvents()
header=next(x for x in unnamed.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert header.text()=='VOCABULARY  ·  到期复习',header.text()
named.close();plain.close();unnamed.close();app.processEvents()
q['_new_group']=True
d=ReviewDialog(q,'center',lambda *_:None,{'review_auto_word':False},'1 / 3');d.show();app.processEvents()
assert any('已自动进入下一组' in label.text() for label in d.findChildren(QLabel))
for theme in ('light','dark'):
 assert 'QPushButton#speaker:hover, QPushButton#speaker:focus' in rp.popup_style({'review_theme':theme})
QTest.keyClick(d,Qt.Key.Key_Escape);app.processEvents();assert not d.isVisible()

aqt.mw.col=object();aqt.mw.state='deckBrowser'
ctl=DesktopReviewController(lambda:{'review_plan_mode':'fixed','review_batch_size':2},lambda *_:None,lambda *_:None,lambda *_:None)
ctl.session_target=1;dlg=types.SimpleNamespace(question={'card_id':42,'word':'test'});ctl.dialog=dlg;got=[]
ctl.signals.saved.disconnect(ctl._saved);ctl.signals.graded.disconnect(ctl._graded);ctl.signals.graded.connect(lambda d,e,g,n:got.append((e,n)))
rp.submit_review=lambda *a,**k:None
rp.prepare_question=lambda *a,**k:{'card_id':43}
ctl._grade(dlg,3)
for _ in range(100):
 app.processEvents();QTest.qWait(5)
 if got:break
assert got and got[0][0] is None and got[0][1][0]['_new_group'] and got[0][1][2:4]==(2,True),got
# a card was produced, so the "why did the session end" slot must stay empty
assert len(got[0][1])==5 and got[0][1][4] is None,got
finished=DesktopReviewController(lambda:{},lambda *_:None,lambda *_:None,lambda *_:None)
finished.session_target=1;events=[];finished.schedule=lambda **kw:events.append('schedule')
finished.show_next=lambda *a,**kw:events.append('next')
finished.dialog=types.SimpleNamespace(completed=True,skipped=False,question={'card_id':42,'word':'test'})
finished._closed(0)
assert events==['schedule'],events
print('Qt: automatic next group, banner and Escape passed')
