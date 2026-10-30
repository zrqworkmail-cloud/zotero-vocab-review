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
from zotero_global_capture.review_logic import clean_detail
app=QApplication([])
for f in (r'C:\Windows\Fonts\segoeui.ttf',r'C:\Windows\Fonts\msyh.ttc'):QFontDatabase.addApplicationFont(f)

q={'kind':'new','mode':'listening','word':'differ','meaning':'v. differ 的现在分词 differing；不同','example':'','literature':'','options':[]}
for theme in ('dark','light'):
 spoken=[]
 ReviewDialog.speak_many=lambda self,texts: spoken.extend(texts) or True
 d=ReviewDialog(q,'center',lambda *_:None,{'review_auto_word':False,'review_theme':theme});d.show();QTest.qWait(60)
 assert spoken==['differ'] and d.listening_explanation.isVisible()
 assert '隐藏' in d.listening_explanation.text() and '释义提示' in d.listening_explanation.text()
 assert not d.question_label.isVisible()
 d.meaning_hint_button.click();app.processEvents()
 assert not d.listening_explanation.isVisible() and d.question_label.isVisible() and d.hint_uses==1
 assert 'differ' not in d.question_label.text().lower()
 d.close();app.processEvents()
print('listening instructions, answer masking, hint and autoplay passed')
