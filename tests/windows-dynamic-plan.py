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

from PyQt6.QtTest import QTest
from zotero_global_capture import review_popup as rp
aqt.mw.col=object();aqt.mw.state='deckBrowser'
for mode, target in [('daily',6),('fixed',4)]:
 cfg={'review_plan_mode':mode,'review_mode':'typing'}
 ctl=DesktopReviewController(lambda:cfg,lambda *args:None,lambda *args:None,lambda *args:None);ctl.session_target=4;ctl.session_seen={1}
 dlg=types.SimpleNamespace(question={'card_id':2,'word':'test'});ctl.dialog=dlg;got=[]
 ctl.signals.saved.disconnect(ctl._saved);ctl.signals.graded.disconnect(ctl._graded);ctl.signals.graded.connect(lambda d,e,g,n:got.append((e,n)))
 rp.submit_review=lambda *a,**k:None;rp.collection_plan=lambda *a,**k:{'batch':6};rp.prepare_question=lambda *a,**k:{'card_id':3}
 ctl._grade(dlg,3)
 for _ in range(100):
  app.processEvents();QTest.qWait(5)
  if got:break
 assert got and got[0][0] is None and got[0][1][2]==target,got
print('Qt: post-rating recalculates automatic target; fixed plan retains target')
