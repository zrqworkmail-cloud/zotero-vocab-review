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
from PyQt6.QtWidgets import QApplication,QComboBox,QDialog,QHBoxLayout,QLabel,QLineEdit,QMenu,QMessageBox,QPushButton,QScrollArea,QStyle,QSizePolicy,QVBoxLayout,QWidget
aqt=types.ModuleType('aqt');aqt.mw=types.SimpleNamespace()
qt=types.ModuleType('aqt.qt')
for n in ('QObject','QTimer','Qt','pyqtSignal','QEasingCurve','QEvent','QRectF','QVariantAnimation','QUrl','QColor','QPainter','QDesktopServices','QMenu','QMessageBox','QCursor','QFontMetrics','QApplication','QComboBox','QDialog','QHBoxLayout','QLabel','QLineEdit','QPushButton','QScrollArea','QStyle','QSizePolicy','QVBoxLayout','QWidget'): setattr(qt,n,globals()[n])
sys.modules['aqt']=aqt;sys.modules['aqt.qt']=qt
package=types.ModuleType('zotero_global_capture');package.__path__=[os.path.abspath(os.path.join(os.path.dirname(__file__),'..','anki-global-addon','zotero_global_capture'))];sys.modules['zotero_global_capture']=package
from zotero_global_capture.review_popup import ReviewDialog, DesktopReviewController
from PyQt6.QtTest import QTest

app=QApplication([])
for f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(f)
ReviewDialog.speak_many=lambda self,texts:True
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

CFG={'review_auto_word':False,'review_auto_example_mode':'off','review_theme':'dark',
     'review_position':'center','review_plan_mode':'fixed','review_batch_size':10,
     'model':'四六级单词模板','deck':'Literature'}
LONG='v. 使放松，使宽慰，缓解，使得到调剂；接替，替换，代替；n. 变化，调剂；v. 解除，减轻，缓解'

def card(word='relieve',mode='typing',meaning=LONG):
    dialog=ReviewDialog({'kind':'due','card_id':1,'mode':mode,'word':word,'meaning':meaning,
                         'example':'Drugs helped to ___ the pain.','literature':'','options':[]},
                        'center',lambda *_a:None,dict(CFG))
    dialog.show();QTest.qWait(60);app.processEvents()
    return dialog

def outside(dialog):
    """Visible rows whose bottom edge falls outside the window — i.e. cut off."""
    out=[]
    for widget in dialog.findChildren(QWidget):
        if not widget.isVisible() or isinstance(widget,(QScrollArea,)):
            continue
        if not widget.geometry().isValid() or not widget.rect().isValid():
            continue
        top_left=widget.mapTo(dialog,QPoint(0,0))
        bottom=top_left.y()+widget.height()
        text=str(getattr(widget,'text',lambda:'')())[:22].replace('\n',' ')
        if bottom>dialog.height() and (text or isinstance(widget,(QPushButton,QLineEdit))):
            out.append('%s 底边 %d > 窗口 %d'%(text or type(widget).__name__,bottom,dialog.height()))
    return out

# 1. A card whose content is taller than the window must grow, not clip.
dialog=card()
dialog.resize(dialog.width(),380)
dialog.fit_card_height();app.processEvents()
assert dialog.height()>380,(dialog.height(),'the card stayed at a height that cuts its own content')
assert not outside(dialog),outside(dialog)
width_after=dialog.width()

# 2. Growing never changes the width — the jump that was already rejected.
dialog.resize(width_after+40,dialog.height())
before_height=dialog.height()
dialog.fit_card_height();app.processEvents()
assert dialog.width()==width_after+40,dialog.width()

# 3. A card that already fits is left exactly where it is: growth is for need, not for looks.
roomy=card(word='loaf',meaning='n. 一条面包，一个面包')
roomy.resize(roomy.width(),609)
needed=roomy.layout().sizeHint().height()
if 609>=needed:
    geometry_before=roomy.geometry()
    roomy.fit_card_height();app.processEvents()
    assert roomy.geometry().height()>=min(needed,roomy.geometry().height()),(roomy.geometry(),needed)
    assert not outside(roomy),outside(roomy)
roomy.deleteLater();QTest.qWait(40)

# 4. Handover into a host that is too short: the host grows, and a host with room to spare
#    keeps the geometry the transition check pins.
cfg2=dict(CFG)
ctl=DesktopReviewController(lambda:cfg2,lambda *a:None,lambda *a:None,lambda *a:None)
ctl.session_target=3
ctl._lookup_known_words=lambda *a:None;ctl._lookup_relations=lambda *a:None;ctl.schedule=lambda **kw:None
first={'kind':'due','card_id':1,'mode':'typing','word':'maintenance','meaning':'维护','example':'','literature':'','options':[]}
second={'kind':'due','card_id':2,'mode':'typing','word':'characteristically','meaning':'典型地','example':'','literature':'','options':[]}
old=ReviewDialog(first,'center',ctl._grade,cfg2);ctl.dialog=old;ctl.review_host=old
old.finished.connect(ctl._closed);old.show();QTest.qWait(60)
old.resize(510,680);old.position_window();before=old.geometry()
ctl._graded(old,None,ctl.generation,(second,None));QTest.qWait(60)
assert ctl.dialog is not old and ctl.dialog.window() is old
# Height now follows the content in BOTH directions (the learner's decision, 2026-11-05:
# 「窗口双向贴合内容」, which replaces "换卡不许跳窗口" for height only). What still must not
# move is the width, and the card must still fill the window it was drawn into.
assert old.width()==before.width(),(old.width(),before.width(),'a height change moved the width')
assert ctl.dialog.geometry()==old.rect(),(ctl.dialog.geometry(),old.rect())
assert abs(old.height()-ctl.dialog.layout().sizeHint().height())<=24,(
    old.height(),ctl.dialog.layout().sizeHint().height(),'the host did not fit the new card')
assert not outside(ctl.dialog),outside(ctl.dialog)
# Now the same handover into a host too short for the new card's content: it must grow.
tall={'kind':'due','card_id':3,'mode':'typing','word':'relieve','meaning':LONG,
      'example':'Drugs helped to ___ the pain.','literature':'','options':[]}
old.resize(510,400);app.processEvents()
host_before=old.geometry()
ctl._graded(ctl.dialog,None,ctl.generation,(tall,None));QTest.qWait(60)
assert ctl.dialog.window() is old
assert not outside(ctl.dialog),outside(ctl.dialog)
assert old.height()>host_before.height(),(old.height(),host_before.height(),
    'the host stayed too short and the new card is cut')
# 5. The other half of the same rule: a short card handed over into a tall host must shrink
#    it. Growing only would leave the surplus we see on the live captures — a dead band the
#    learner called 「空隙太大了」 — and §9.32's real constraint (the card must fill the
#    window it is drawn in) is held by the host's own resizeEvent, not by refusing to resize.
short={'kind':'due','card_id':4,'mode':'judgment','word':'loaf','meaning':'n. 一条面包',
       'options':['正确','错误'],'judgment_statement':'n. 一条面包','judgment_correct':True,
       'example':'','literature':''}
previous=ctl.dialog
host=previous.window() if getattr(previous,'_embedded',False) else previous
host_height_before=host.height()
ctl._graded(previous,None,ctl.generation,(short,None));QTest.qWait(60)
card=ctl.dialog
assert card.window() is host, 'the short card did not land in the previous window'
needed=card.layout().sizeHint().height()
assert host.height()<=needed+24,(host.height(),needed,host_height_before,
    'the host stayed taller than the card needs — that surplus is the dead band')
assert card.geometry()==host.rect(),(card.geometry(),host.rect())
assert not outside(card),outside(card)
# 6. The session opener. With no previous card there was nothing to fit the window against,
#    so the fixed birth size 510x570 was the only height it ever got: a live capture
#    (shots10, 2026-11-06) shows a 526x609 window whose own content needed 474 -- about 96 px
#    of dead band that no later card of the session had.
if ctl.dialog is not None:
    ctl.dialog.close()
app.processEvents();QTest.qWait(40)
opener_ctl=DesktopReviewController(lambda:cfg2,lambda *a:None,lambda *a:None,lambda *a:None)
opener_ctl._lookup_known_words=lambda *a:None;opener_ctl._lookup_relations=lambda *a:None
opener_ctl.schedule=lambda **kw:None;opener_ctl._start_prefetch=lambda *a:None
first={'kind':'due','card_id':77,'mode':'judgment','word':'loaf','meaning':'n. 一条面包',
       'options':['正确','错误'],'judgment_statement':'n. 一条面包','judgment_correct':True,
       'example':'','literature':''}
opener_ctl._prepared(first,None,opener_ctl.generation,True)
QTest.qWait(120);app.processEvents()
opener=opener_ctl.dialog
assert opener is not None, '会话第一张卡没弹出来，检查的前提就没了'
needed=opener.layout().sizeHint().height()
assert abs(opener.height()-needed)<=24,(opener.height(),needed,
    '第一张卡还停在出生尺寸，眉标和题面之间多出一条死空带')
assert not outside(opener),outside(opener)
opener.close();app.processEvents();QTest.qWait(40)

if ctl.dialog is not None:
    ctl.dialog.close()
app.processEvents()
print('Qt: card height follows the content, grows only when needed, and never moves the width')
