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

for theme in ('light','dark'):
 for position in ('center','corner'):
  cfg={'review_auto_word':False,'review_auto_example_mode':'off','review_theme':theme,'review_position':position}
  aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False
  ctl=DesktopReviewController(lambda:cfg,lambda *args:None,lambda *args:None,lambda *args:None);ctl.session_target=2
  ctl._lookup_known_words=lambda *args:None;ctl._lookup_relations=lambda *args:None;ctl.schedule=lambda **kw:None
  first={'kind':'due','card_id':1,'mode':'typing','word':'maintenance','meaning':'维护','example':'','literature':'','options':[]}
  second={'kind':'due','card_id':2,'mode':'typing','word':'characteristically','meaning':'典型地','example':'','literature':'','options':[]}
  old=ReviewDialog(first,position,ctl._grade,cfg);ctl.dialog=old;ctl.review_host=old;old.finished.connect(ctl._closed);old.show();QTest.qWait(50);old.resize(510,680);old.position_window();before=old.geometry()
  observations=[];original_show=ReviewDialog.show
  def checked_show(self):
   if self is not old: observations.append(old.isVisible())
   return original_show(self)
  ReviewDialog.show=checked_show
  try: ctl._graded(old,None,ctl.generation,(second,None));QTest.qWait(60)
  finally: del ReviewDialog.show
  assert observations==[True],observations
  assert ctl.dialog is not old and ctl.dialog.isVisible() and old.isVisible() and ctl.dialog.window() is old and not ctl.dialog.isWindow()
  assert old.geometry()==before,(old.geometry(),before)
  assert ctl.session_seen=={1} and ctl.session_words=={'maintenance'}
  assert ctl.dialog.letter_boxes[0].hasFocus()
  viewport=ctl.dialog.letter_scroll.viewport()
  assert ctl.dialog.letter_scroll.horizontalScrollBar().maximum()==0
  assert all(viewport.rect().contains(box.mapTo(viewport,box.rect().topLeft())) and
             viewport.rect().contains(box.mapTo(viewport,box.rect().bottomRight())) for box in ctl.dialog.letter_boxes)
  for char in second['word']:
   QTest.keyClicks(app.focusWidget(),char)
  assert ''.join(box.text() for box in ctl.dialog.letter_boxes)==second['word']
  ctl.session_target=3
  second_dialog=ctl.dialog
  third=dict(second,card_id=3,word='prediction')
  ctl._graded(second_dialog,None,ctl.generation,(third,None));QTest.qWait(60)
  assert ctl.dialog is not second_dialog and ctl.dialog.window() is old and old.isVisible()
  assert old.geometry()==before and ctl.session_seen=={1,2}
  current=ctl.dialog; old.resize(old.width()+10,old.height()+10);app.processEvents();assert current.geometry()==old.rect()
  ratings=[];current.grade=lambda _d,ease:ratings.append(ease);current.reveal(True);app.processEvents();QTest.keyClick(current,Qt.Key.Key_Return);assert ratings==[3],ratings
  ctl.dialog.close();app.processEvents();assert not old.isVisible() and ctl.dialog is None
print('Qt: next card overlaps old window and keeps geometry, focus, and session state')
