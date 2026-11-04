import os,sys,types,threading
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


# Anki's audio backend is the one thing this check must not really run, so the player
# is replaced by a recorder. Everything else is the production card and controller.
class Tag:
    def __init__(self, **kw): self.field_text = kw.get('field_text', '')
class FileTag:
    def __init__(self, **kw): self.filename = kw.get('filename', '')
anki_pkg=types.ModuleType('anki'); anki_sound=types.ModuleType('anki.sound'); anki_sound.TTSTag=Tag
anki_sound.SoundOrVideoTag=FileTag
sys.modules['anki']=anki_pkg; sys.modules['anki.sound']=anki_sound
class Player:
    def __init__(self): self.plays=[]; self.stops=[]; self.chosen=None
    def _best_player_for_tag(self, tag): return self.chosen
    def play_tags(self, tags):
        self.plays.append([getattr(tag,'field_text',None) or getattr(tag,'filename','') for tag in tags])
    def stop_and_clear_queue(self): self.stops.append(len(self.plays))
player=Player()
aqt_sound=types.ModuleType('aqt.sound'); aqt_sound.av_player=player
sys.modules['aqt.sound']=aqt_sound; aqt.sound=aqt_sound

class Taskman:
    def __init__(self): self.jobs=[]
    def run_in_background(self, fn, on_done=None): self.jobs.append((fn,on_done))
taskman=Taskman()

from zotero_global_capture.review_popup import ReviewDialog, DesktopReviewController
from zotero_global_capture import review_popup as rp
from PyQt6.QtTest import QTest
app=QApplication([])

# 回看上一张：做完的卡翻过去之后，用户要能再看一眼上一张——只看，不许再评分、不许动
# Anki 的排程，也不许把当前这张的输入状态弄丢。
cfg={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
     'review_theme':'light','review_position':'center','review_plan_mode':'fixed','review_batch_size':3}
notes=[]
ctl=DesktopReviewController(lambda:cfg,lambda *a:None,lambda message,*a:None,lambda event: notes.append(str(event)))
ctl._lookup_known_words=lambda *a:None; ctl._lookup_relations=lambda *a:None; ctl.schedule=lambda **kw:None
ctl.session_target=3
def card(cid, word): return {'kind':'due','card_id':cid,'mode':'typing','word':word,'meaning':'释义 '+word,
                             'example':'','literature':'','options':[],'phonetic':'/x/','answer_form':word,
                             'profile':'p','snapshot':{}}
submitted=[]
def fake_grade(dialog, ease):
    submitted.append((dialog.question['card_id'], ease))
    ctl.remember(dialog, ease)
    return True

shown=[]
def build(cid, word):
    dialog=ReviewDialog(card(cid,word),'center',fake_grade,cfg)
    ctl.dialog=dialog; ctl.review_host=dialog
    dialog.review_requested.connect(lambda _d=None: ctl.review_previous())
    dialog.review_back_requested.connect(lambda _d=None: ctl.review_back())
    dialog.show();QTest.qWait(50);app.processEvents();QTest.qWait(50)
    shown.append(dialog)
    return dialog

first=build(41,'increase'); first.reveal(True); app.processEvents(); QTest.qWait(50)
first.start_grade(4); app.processEvents(); QTest.qWait(50)
second=build(42,'treat'); second.reveal(True); app.processEvents(); QTest.qWait(50)
second.start_grade(2); app.processEvents(); QTest.qWait(50)
current=build(43,'perform'); current.reveal(True); app.processEvents(); QTest.qWait(50)
assert len(ctl.history)==2, ctl.history
before=len(submitted)

# 1. P on the answer face opens the look-back on the card before this one.
QTest.keyClick(current, Qt.Key.Key_P); app.processEvents(); QTest.qWait(80)
review=ctl.dialog
assert review is not current, 'P must bring the previous card up'
assert review.question['card_id']==42, review.question['card_id']
assert review.answer_shown and review.review_note, 'the look-back shows the answer side'
assert not review.grade_widget.isVisible(), 'a card that is already rated has no rating row'
assert review.findChild(QPushButton,'reviewExit') is not None
assert '回看' in review.status.text(), review.status.text()
assert len(submitted)==before, 'looking back may not answer anything: %s' % submitted
assert not current.isVisible(), 'the current card waits hidden, it is not closed'

# 2. The back button walks one further, still without submitting.
review.findChild(QPushButton,'reviewBack').click(); app.processEvents(); QTest.qWait(80)
assert ctl.dialog.question['card_id']==41, ctl.dialog.question['card_id']
assert len(submitted)==before, submitted

# 3. Exiting returns the card the user was on, with its answer face still up.
ctl.dialog.findChild(QPushButton,'reviewExit').click(); app.processEvents(); QTest.qWait(80)
assert ctl.dialog is current, 'leaving the look-back must come home to the same card'
assert current.isVisible() and current.answer_shown
assert len(submitted)==before, submitted
assert not ctl.history or ctl.dialog is current

# 4. Ratings after the look-back still work normally.
current.start_grade(3); app.processEvents(); QTest.qWait(50)
assert len(submitted)==before+1, submitted
print('Qt: P looks back through rated cards without answering, and comes home with the card intact')
