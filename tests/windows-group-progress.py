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
# The card header has to name the book, its progress and what this card is.
named=ReviewDialog(dict(q),'center',lambda *_:None,{'review_auto_word':False,'study_book':'cet4_core','_book_progress':(128,439)},'1 / 3')
named.show();app.processEvents()
header=next(x for x in named.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert header.text()=='VOCABULARY  ·  四级核心  ·  128/439  ·  到期复习',header.text()
lit=ReviewDialog(dict(q),'center',lambda *_:None,{'review_auto_word':False,'study_book':'literature'},'1 / 3')
lit.show();app.processEvents()
header=next(x for x in lit.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert header.text()=='VOCABULARY  ·  文献单词  ·  到期复习',header.text()
newness=ReviewDialog(dict(q,kind='new'),'center',lambda *_:None,{'review_auto_word':False,'study_book':'cet6_full','_book_progress':(0,4803)},'1 / 3')
newness.show();app.processEvents()
header=next(x for x in newness.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert header.text()=='VOCABULARY  ·  六级全表  ·  0/4803  ·  新词',header.text()
# A due card that never graduated is yesterday's mistake, not an old review word: 252 of the
# 253 cards due in this book were labelled 到期复习, which is what made the user ask whether
# they had ever studied a word at all.
learning=ReviewDialog(dict(q,learning=True),'center',lambda *_:None,{'review_auto_word':False,'study_book':'cet6_full','_book_progress':(0,4803)},'1 / 3')
learning.show();app.processEvents()
header=next(x for x in learning.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert header.text()=='VOCABULARY  ·  六级全表  ·  0/4803  ·  刚学过',header.text()
assert '学习步长' in header.toolTip(),header.toolTip()
legacy=ReviewDialog(dict(q),'center',lambda *_:None,{'review_auto_word':False,'review_book':'cet6_kyle'},'1 / 3')
legacy.show();app.processEvents()
header=next(x for x in legacy.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert header.text()=='VOCABULARY  ·  六级词表（KyleBing）  ·  到期复习',header.text()
unnamed=ReviewDialog(dict(q),'center',lambda *_:None,{'review_auto_word':False},'1 / 3')
unnamed.show();app.processEvents()
header=next(x for x in unnamed.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert header.text()=='VOCABULARY  ·  未选词书  ·  到期复习',header.text()
named.close();lit.close();newness.close();learning.close();legacy.close();unnamed.close();app.processEvents()
# Spec §8: with several 词组 chosen, the eyebrow names the entry this card was drawn from
# (_selection_index), not the first book of the selection and not 未选词书.
multi_cfg={'review_auto_word':False,'study_selection':[{'book':'cet4_core','tags':[]},{'book':'cet6_full','tags':[]}],
           '_book_progress':(0,4803)}
multi=ReviewDialog(dict(q,_selection_index=1),'center',lambda *_:None,multi_cfg,'1 / 3')
multi.show();app.processEvents()
header=next(x for x in multi.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert header.text()=='VOCABULARY  ·  六级全表  ·  0/4803  ·  到期复习',header.text()
assert '六级全表' in header.toolTip(),header.toolTip()
multi.close();app.processEvents()
q['_new_group']=True
d=ReviewDialog(q,'center',lambda *_:None,{'review_auto_word':False},'1 / 3');d.show();app.processEvents()
assert not any('自动进入下一组' in label.text() for label in d.findChildren(QLabel)), \
    'the group boundary is a countdown the user answers, not a silent roll-over'
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
assert got and got[0][0] is None and got[0][1][2:4]==(2,True),got
# a card was produced, so the "why did the session end" slot must stay empty
assert len(got[0][1])==5 and got[0][1][4] is None,got
finished=DesktopReviewController(lambda:{},lambda *_:None,lambda *_:None,lambda *_:None)
finished.session_target=1;events=[];finished.schedule=lambda **kw:events.append('schedule')
finished.show_next=lambda *a,**kw:events.append('next')
finished.dialog=types.SimpleNamespace(completed=True,skipped=False,question={'card_id':42,'word':'test'})
finished._closed(0)
assert events==['schedule'],events

# The worker must compute the book progress and hand it to the preview, not just the
# name: a book label without 已学/总数 was the state before this check existed.
prog_cfg={'review_plan_mode':'fixed','review_batch_size':1,'review_auto_word':False,
          'study_book':'cet4_core','review_theme':'dark','review_known_style':'none'}
ctl=DesktopReviewController(lambda:dict(prog_cfg),lambda *_:None,lambda *_:None,lambda *_:None)
ctl.session_target=1;ctl._lookup_relations=lambda *_:None
rp.prepare_question=lambda *a,**k:dict(q,card_id=44)
rp.book_progress=lambda api,cfg:(128,439)
ctl.show_next(True)
for _ in range(200):
 app.processEvents();QTest.qWait(5)
 if ctl.dialog:break
assert ctl.dialog is not None,'the prepared card must be shown'
assert ctl.dialog.cfg.get('_book_progress')==(128,439),ctl.dialog.cfg.get('_book_progress')
header=next(x for x in ctl.dialog.findChildren(QLabel) if 'VOCABULARY' in x.text())
assert header.text()=='VOCABULARY  ·  四级核心  ·  128/439  ·  到期复习',header.text()
ctl.dialog.close();app.processEvents()
print('Qt: automatic next group, banner, Escape and live book progress passed')
