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

import tempfile,json,hashlib
with tempfile.TemporaryDirectory() as temp:
 audio=b'test-audio';audio_path=os.path.join(temp,'cet6-202512-1.mp3');open(audio_path,'wb').write(audio)
 data={'title':'Local real exam','kind':'exam','audio_file':'cet6-202512-1.mp3','audio_sha256':hashlib.sha256(audio).hexdigest(),'questions':[{'question':'Choose','options':['A','B','C','D'],'answer':1} for _ in range(25)]}
 with open(os.path.join(temp,'cet6-202512-1.json'),'w',encoding='utf8') as f:json.dump(data,f)
 second=dict(data, title='Second paper', audio_file='second.mp3')
 open(os.path.join(temp,'second.mp3'),'wb').write(audio)
 with open(os.path.join(temp,'cet6-202601-1.json'),'w',encoding='utf8') as f:json.dump(second,f)
 played_files=[];sound.av_player.play_file_with_caller=lambda path,caller:played_files.append(path);sound.av_player.stop_and_clear_queue_if_caller=lambda caller:None
 d=ListeningPractice(local_dir=temp);d.show();app.processEvents();assert d.source_choice.currentData()=='local' and '25' in d.heading.text()
 d.play_audio();assert played_files==[audio_path]
 assert not d.transcript_button.isEnabled();d.buttons[1].click();assert '回答正确' in d.feedback.text() and not d.transcript_button.isEnabled()
 d.next_button.click();assert d.question_index==1
 d.source_choice.setCurrentIndex(d.source_choice.findData('local:1'));assert d.passages[0]['title']=='Second paper'
 d.buttons[1].click()
 with open(os.path.join(temp,'progress.jsonl'),encoding='utf8') as f: records=[json.loads(line) for line in f]
 assert records[-1]['paper']=='cet6-202601-1'
 d.source_choice.setCurrentIndex(d.source_choice.findData('practice'));assert d.passage_index==0 and d.question_index==0
 d.close();app.processEvents()
 open(audio_path,'ab').write(b'bad');d=ListeningPractice(local_dir=temp);assert len(d.local_papers)==1 and d.local_papers[0]['title']=='Second paper';d.close()
print('Qt: local paper integrity, playback, answers and source switching passed')
