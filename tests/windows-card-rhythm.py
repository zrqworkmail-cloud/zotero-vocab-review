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
from PyQt6.QtTest import QTest
app=QApplication([])

from zotero_global_capture import review_popup as rp
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False
aqt.mw.taskman=taskman

cfg={'review_auto_word':True,'review_auto_example':False,'review_auto_example_mode':'off',
     'review_hint_audio':False,'review_theme':'light','review_position':'center','review_plan_mode':'fixed','review_batch_size':2}
def card(cid, word): return {'kind':'due','card_id':cid,'mode':'typing','word':word,'meaning':'释义','example':'','literature':'','options':[],'phonetic':''}

first=ReviewDialog(card(1,'maintenance'),'center',lambda *_a:None,cfg)
first.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
stops=len(player.stops)
first.speak_many(['first sentence'])
assert player.plays[-1]==['first sentence'],player.plays
first.speak_many(['second sentence'])
assert len(player.stops)>stops,'a new utterance must cut the queue instead of stacking behind it'

second=ReviewDialog(card(2,'character'),'center',lambda *_a:None,cfg)
stops=len(player.stops)
second.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
assert len(player.stops)>stops,'showing a card must silence whatever the previous card was reading'

# 1b. With the gain dialled above 100%, SAPI may not keep the word: it speaks straight to
#     the sound card, where the filter cannot reach it. The word has to be rendered and then
#     queued as a FILE, and a render that lands after the next card was shown must stay quiet.
class SapiPlayer:
    speaker=object()
loud_cfg=dict(cfg, review_volume=240)
player.chosen=SapiPlayer()
loud=ReviewDialog(card(3,'thrive'),'center',lambda *_a:None,loud_cfg)
loud.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
plays=len(player.plays); jobs=len(taskman.jobs)
loud.speak_many(['loud word'])
assert len(taskman.jobs)==jobs+1,'a gain above 100% must hand the word to the renderer'
assert len(player.plays)==plays,'nothing may be queued before the wav exists'
taskman.jobs[-1][1](types.SimpleNamespace(result=lambda:['C:/tmp/zvr-speech-0.wav']))
assert player.plays[-1]==['C:/tmp/zvr-speech-0.wav'],player.plays

later=ReviewDialog(card(4,'anchor'),'center',lambda *_a:None,loud_cfg)
later.speak_many(['late word'])
later.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
plays=len(player.plays)
taskman.jobs[-1][1](types.SimpleNamespace(result=lambda:['C:/tmp/zvr-speech-1.wav']))
assert len(player.plays)==plays,'a render that lands after the next card must not speak the older word'
loud.close();later.close();app.processEvents()
first.close();second.close();app.processEvents()

notes=[]
ctl=DesktopReviewController(lambda:cfg,lambda *a:None,lambda message,*a:notes.append(str(message)),lambda *a:None)
ctl.session_target=2;ctl._lookup_known_words=lambda *a:None;ctl._lookup_relations=lambda *a:None;ctl.schedule=lambda **kw:None
real=(rp.submit_review, rp.collection_plan, rp.prepare_question, rp.book_progress)
rp.collection_plan=lambda *a,**k:{'batch':2,'new_remaining':1,'goal':10,'done':1,'due':0}
rp.book_progress=lambda *a,**k:(47,481)
next_card=card(12,'character')
asked={}
def fake_prepare(api, config, mode='mixed', rng=None, due_only=False):
    request=config.get('_review')
    asked['inflight_new']=request.inflight_new if request else config.get('_review_inflight_new')
    asked['inflight_due']=request.inflight_due if request else config.get('_review_inflight_due')
    return dict(next_card)
rp.prepare_question=fake_prepare

hold=threading.Event(); started=threading.Event(); finished=threading.Event()
def slow_submit(*_a, **_k):
    started.set(); hold.wait(10); finished.set(); return [True]
rp.submit_review=slow_submit
d1=ReviewDialog(card(11,'maintenance'),'center',ctl._grade,cfg)
ctl.dialog=d1; ctl.review_host=d1; d1.finished.connect(ctl._closed); d1.show(); QTest.qWait(60); app.processEvents()
d1.reveal(True); app.processEvents(); QTest.qWait(60)
stops=len(player.stops)
d1.start_grade(3)
assert '正在保存' not in d1.status.text(),d1.status.text()
for _ in range(240):
    app.processEvents(); QTest.qWait(5)
    if ctl.dialog is not d1: break
assert started.is_set(),'the save should have been attempted'
assert ctl.dialog is not d1,'the next card must appear while the save is still in flight'
assert not finished.is_set(),'the flip must not have waited for the save'
assert (asked['inflight_new'], asked['inflight_due'])==(0,1),asked
hold.set()
for _ in range(240):
    app.processEvents(); QTest.qWait(5)
    if finished.is_set(): break
QTest.qWait(120); app.processEvents(); QTest.qWait(120); app.processEvents()
assert [note for note in notes if '保存' in note]==[],notes
assert len(player.stops)>stops,'a finished session must not keep reading out loud'

# A save that fails has to be said out loud, because the card has already moved on.
d2=ctl.dialog
d2.reveal(True); app.processEvents(); QTest.qWait(60)
def failing_submit(*_a, **_k): raise ValueError('Anki 没有确认保存评分')
rp.submit_review=failing_submit
before=len(notes)
d2.start_grade(3)
for _ in range(240):
    app.processEvents(); QTest.qWait(5)
    if len(notes)>before: break
assert any('没有保存' in note for note in notes[before:]),notes[before:]
assert any('character' in note for note in notes[before:]),'the message has to name the card that was lost: %s' % notes[before:]

# 3. The next card is prepared while you are still reading this one, so rating flips
#    without another round trip. Each prepare call is tagged by who asked for it.
prep=[]
def timed_prepare(api, config, mode='mixed', rng=None, due_only=False):
    request=config.get('_review')
    prefetch=request.prefetch if request else config.get('_review_prefetch')
    prep.append('prefetch' if prefetch else 'flip')
    QTest.qWait(200)
    return card(30+ len(prep), 'prefetched')
rp.prepare_question=timed_prepare
rp.submit_review=lambda *a,**k:[True]
notes2=[]
ctl3=DesktopReviewController(lambda:cfg, lambda *a:None, lambda message,*a: notes2.append(str(message)), lambda *a:None)
ctl3._lookup_known_words=lambda *a:None;ctl3._lookup_relations=lambda *a:None;ctl3.schedule=lambda **kw:None
ctl3.show_next(True)
for _ in range(400):
    app.processEvents(); QTest.qWait(5)
    if ctl3.dialog is not None: break
assert ctl3.dialog is not None and prep[0]=='flip',prep
for _ in range(400):
    app.processEvents(); QTest.qWait(5)
    if ctl3.prefetched is not None: break
assert ctl3.prefetched is not None,'the next card must be prepared while the current one is on screen: %s' % prep
shown=ctl3.dialog
shown.start_grade(3)
flipped=False
for _ in range(16):
    app.processEvents(); QTest.qWait(5)
    if ctl3.dialog is not shown: flipped=True; break
assert flipped,'rating must not wait for a fresh prepare: %s' % prep
assert prep.count('flip')==1,'the flip must reuse the prefetched card, not prepare again: %s' % prep
ctl3.stop();app.processEvents()

# 4. Rating while the prefetch is STILL running must wait for it, not start a second
#    full prepare. The old 0.4 s cap turned a slow prefetch into double work — two
#    threads racing the same round trips — which is what made every rating lag
#    (measured 2026-11-10: answer phase <=1 s for 365/381 ratings, prefetch ~3 s).
prep4=[]
def slow_prepare(api, config, mode='mixed', rng=None, due_only=False):
    request=config.get('_review')
    prefetch=request.prefetch if request else config.get('_review_prefetch')
    prep4.append('prefetch' if prefetch else 'flip')
    QTest.qWait(700)
    return card(60+len(prep4), 'inflight')
rp.prepare_question=slow_prepare
ctl4=DesktopReviewController(lambda:cfg, lambda *a:None, lambda *a:None, lambda *a:None)
ctl4._lookup_known_words=lambda *a:None;ctl4._lookup_relations=lambda *a:None;ctl4.schedule=lambda **kw:None
ctl4.show_next(True)
for _ in range(400):
    app.processEvents(); QTest.qWait(5)
    if ctl4.dialog is not None: break
assert ctl4.dialog is not None and prep4[0]=='flip',prep4
shown4=ctl4.dialog
# Rate at once: the 700 ms prefetch cannot have finished in the ~5 ms since display.
shown4.start_grade(3)
flipped=False
for _ in range(400):
    app.processEvents(); QTest.qWait(5)
    if ctl4.dialog is not shown4: flipped=True; break
assert flipped,'rating must still flip while the prefetch is in flight'
assert prep4.count('flip')==1,'the flip must wait for the in-flight prefetch, not prepare a second time: %s' % prep4
ctl4.stop();app.processEvents()

rp.submit_review, rp.collection_plan, rp.prepare_question, rp.book_progress = real

# Dismissing the card must not leave a sentence talking in the background.
ctl2=DesktopReviewController(lambda:cfg,lambda *a:None,lambda *a:None,lambda *a:None)
ctl2._lookup_known_words=lambda *a:None;ctl2._lookup_relations=lambda *a:None;ctl2.schedule=lambda **kw:None
third=ReviewDialog(card(20,'predict'),'center',ctl2._grade,cfg)
ctl2.dialog=third;ctl2.review_host=third;third.finished.connect(ctl2._closed)
third.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
assert ctl2.card_on_screen(),'a card that is up has to be seen as on screen'
third.reveal(True);app.processEvents();QTest.qWait(60)
stops=len(player.stops)
third.reject();app.processEvents();QTest.qWait(60)
assert len(player.stops)>stops,'closing the card must stop the reading'
assert not ctl2.card_on_screen(),'a dismissed card must stop holding the main window open'

print('Qt: a new card silences the last one, and rating flips immediately with the save in the background')
