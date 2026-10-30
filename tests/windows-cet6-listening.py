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

from zotero_global_capture import cet6_listening as listening_module
from zotero_global_capture.cet6_listening import ListeningPractice,PASSAGES
opened=[];listening_module.QDesktopServices=types.SimpleNamespace(openUrl=lambda url:opened.append(url.toString()) or True)
anki=types.ModuleType('anki');anki.__path__=[];sys.modules['anki']=anki;ankisound=types.ModuleType('anki.sound');ankisound.TTSTag=lambda **kw:types.SimpleNamespace(**kw);sys.modules['anki.sound']=ankisound
sound=types.ModuleType('aqt.sound'); played=[];sound.av_player=types.SimpleNamespace(play_tags=lambda tags:played.extend(tags));sys.modules['aqt.sound']=sound
d=ListeningPractice();d.show();app.processEvents();d.real_exam_button.click();assert opened==['https://eol.nju.edu.cn/cet6/index.html'];d.play_audio();assert len(played)==1 and played[0].field_text==PASSAGES[0]['audio']
assert '不是历年真题' in d.heading.text() and not d.transcript_button.isEnabled() and not d.next_button.isEnabled()
answers=[]
for passage in PASSAGES:
 for q in passage['questions']:
  assert d.question.text()==q['question']
  d.buttons[q['answer']].click();app.processEvents();assert '回答正确' in d.feedback.text() and d.transcript_button.isEnabled()
  d.transcript_button.click();assert d.transcript_area.isVisible() and passage['audio'] in d.transcript.text()
  d.next_button.click();app.processEvents();answers.append(q)
assert d.correct_count==len(answers) and '练习完成' in d.heading.text()
d.close()
print('Qt: six listening questions, answer feedback and transcript reveal passed')
