import os,sys,ctypes,types,ast
base=r'D:\Program Files (x86)\Anki\app_packages';sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
dlls=[os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin')),os.add_dll_directory(os.path.dirname(base))];ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
from PyQt6.QtWidgets import QApplication,QCheckBox,QComboBox,QDateEdit,QDialog,QDialogButtonBox,QFormLayout,QGroupBox,QHBoxLayout,QLabel,QLineEdit,QPushButton,QRadioButton,QScrollArea,QSpinBox,QTimeEdit,QVBoxLayout,QWidget
from PyQt6.QtCore import QTimer,Qt,QDate,QTime,QObject,pyqtSignal,QEvent,QPoint,QPointF
import threading
from PyQt6.QtGui import QFont,QFontDatabase,QPalette,QColor,QWheelEvent
app=QApplication([]);app.setStyle('Fusion');app.setStyleSheet('QGroupBox { background: #333333; color: #eeeeee; }')
for f in (r'C:\Windows\Fonts\segoeui.ttf',r'C:\Windows\Fonts\msyh.ttc'):QFontDatabase.addApplicationFont(f)
app.setFont(QFont('Microsoft YaHei',10))
palette=app.palette();palette.setColor(QPalette.ColorRole.Window,QColor('#242424'));palette.setColor(QPalette.ColorRole.WindowText,QColor('#eeeeee'));app.setPalette(palette)

# PyQt6 aborts the process with no traceback when a slot raises, so assertions inside
# these callbacks report through check() instead of `assert`.
failures=[]
def check(ok, detail):
	if not ok: failures.append(detail)
	return bool(ok)

def dialog_now():
	return next(w for w in app.topLevelWidgets() if isinstance(w,QDialog) and w.isVisible())

class Decks:
 def all_names_and_ids(self,include_filtered=False):return [types.SimpleNamespace(name=x) for x in ('文献单词','四六级单词','四六级核心词汇')]
class Models:
 def all_names_and_ids(self):return [types.SimpleNamespace(name=x) for x in ('四六级单词模板','Basic')]
 def by_name(self,name):return {'name':name} if name in ('四六级单词模板','Basic') else None
 def field_names(self,model):return ['正面','解释','例句'] if model['name']=='四六级单词模板' else ['Front','Back']
mw=types.SimpleNamespace(col=types.SimpleNamespace(decks=Decks(),models=Models()))
cfg={'mode':'preview','deck':'文献单词','model':'四六级单词模板','front_field':'正面','back_field':'解释','confirm_seconds':8,'modifiers':6,'virtual_key':121,'review_enabled':True,'review_interval_minutes':15,'review_batch_size':6,'review_auto_word':True,'review_auto_example_mode':'first','review_smart':True,'review_extra_deck':'四六级单词','review_position':'center','review_mode':'mixed','review_known_style':'underline','review_beautify':True,'review_start_at_login':True}
cfg.update(review_theme='light',review_hint_audio=False,review_plan_mode='fixed',review_daily_goal=0,review_computer_hours=8,review_deadline='',review_exam='manual',review_windows_enabled=False,review_windows=[{'enabled':True,'start':'09:00','end':'12:00'},{'enabled':True,'start':'14:00','end':'18:00'},{'enabled':True,'start':'19:00','end':'22:00'}])
import importlib.util
source=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','anki-global-addon','zotero_global_capture'))
sp=importlib.util.spec_from_file_location('review_logic',os.path.join(source,'review_logic.py'));logic=importlib.util.module_from_spec(sp);sp.loader.exec_module(logic)
sp2=importlib.util.spec_from_file_location('audio_volume',os.path.join(source,'audio_volume.py'));audio_volume=importlib.util.module_from_spec(sp2);sp2.loader.exec_module(audio_volume)
review_decks=logic.review_decks
selected_review_modes=logic.selected_review_modes
collection_plan=logic.collection_plan
validate_windows=logic.validate_windows
window_minutes=logic.window_minutes
fetch_cet=lambda: '2026-12-12'
mw.col.find_cards=lambda query: []
LOCAL_TAGS=['anki_global_capture','zvr_kyle_cet4','zvr_kyle_cet6','zvr_cet6_full','工作/学习']
local_tags=lambda: list(LOCAL_TAGS)
class ShortcutEdit(QLineEdit):
 feedback=pyqtSignal(str)
 def __init__(self,m,v):super().__init__('Ctrl+Shift+F10');self.modifiers=m;self.virtual_key=v;self.valid=True
path=os.path.join(source,'__init__.py')
tree=ast.parse(open(path,encoding='utf-8').read());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='open_settings');module=ast.Module(body=[node],type_ignores=[])
scope=globals();scope.update(settings=lambda:dict(cfg),show_feedback=lambda *_a,**_k:None,format_shortcut=lambda *_:'Ctrl+Shift+F10',
	local_tags=local_tags,study_books=logic.study_books,study_book_id=logic.study_book_id,refresh_toolbar=lambda:None,
	apply_sync_preference=lambda:None,
	apply_review_volume=lambda value=None:None, volume_preview=lambda value:None,
	dialog_now=dialog_now,check=check,failures=failures)
exec(compile(module,path,'exec'),scope)

import types,sys
aqt=types.ModuleType('aqt'); aqt.__path__=[]
theme=types.ModuleType('aqt.theme');theme.theme_manager=types.SimpleNamespace(night_mode=True)
sys.modules['aqt']=aqt;sys.modules['aqt.theme']=theme


def book_radios(d):
 return d.findChild(QWidget,'studyBookList').findChildren(QRadioButton)

def book_ids(d):
 return [x.property('bookId') for x in book_radios(d)]

def save_button(d):
 return d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save)

def open_and(act):
 QTimer.singleShot(100,act);open_settings(QWidget())

saved=[]
scope.update(save_settings=lambda data:saved.append(dict(data)),controller=types.SimpleNamespace(listener=types.SimpleNamespace(registered=True,registration_error=''),review=types.SimpleNamespace(dialog=object(),start=lambda:None)))

# 1. The old deck+tag scope controls are gone. The list only offers books that really
#    exist in this account, and a saved legacy book reopens as the same book checked.
cfg.update(deck='四六级核心词汇',review_core_enabled=True,review_extra_decks=['四六级核心词汇','文献单词'],
	review_book='cet6_kyle',review_scope_decks=[],review_scope_tags=[],review_tags_all=False,review_scope_name='')
def inspect_first():
 d=dialog_now()
 for name in ('reviewBook','reviewScopeTags','reviewExtraDeck','reviewTagsMatch','reviewAllDecks','reviewScopeName'):
  check(d.findChild(QWidget,name) is None,'%s must be gone from the book model' % name)
 check(book_ids(d)==['cet6_full','cet4_full','cet6_kyle','literature'],
       'only books present in the account are offered, got %s' % book_ids(d))
 checked=[x.property('bookId') for x in book_radios(d) if x.isChecked()]
 check(checked==['cet6_kyle'],'the legacy 词书 must reopen as its book checked, got %s' % checked)
 save_button(d).click()
open_and(inspect_first)
check(saved[-1]['study_book']=='cet6_kyle','save must write the book id')

# 2. Reopening restores the selection, and picking another book saves that one.
cfg.update(saved[0]);saved.clear()
def pick_other():
 d=dialog_now()
 checked=[x.property('bookId') for x in book_radios(d) if x.isChecked()]
 check(checked==['cet6_kyle'],'reopen must restore the saved book, got %s' % checked)
 next(x for x in book_radios(d) if x.property('bookId')=='cet4_full').setChecked(True)
 save_button(d).click()
open_and(pick_other)
check(saved[-1]['study_book']=='cet4_full','the picked book must save')

# 3. A saved book whose tag is not in this account must not be re-selected, and the
#    dialog must refuse to save until a real book is picked.
cfg.update(saved[-1]);cfg.update(study_book='cet6_core',review_book='');saved.clear()
def missing_book():
 d=dialog_now()
 check(not any(x.isChecked() for x in book_radios(d)),'a book with no cards must not be silently re-selected')
 check(not save_button(d).isEnabled(),'saving without a book must be blocked')
 check(any('请选择一本要学的词书' in x.text() for x in d.findChildren(QLabel)),'the reason must be on screen')
 next(x for x in book_radios(d) if x.property('bookId')=='literature').setChecked(True)
 check(save_button(d).isEnabled(),'picking a real book must unlock saving')
 save_button(d).click()
open_and(missing_book)
check(saved[-1]['study_book']=='literature','saving after the fix must write the real book')

# 4. With no tags at all, tag books are not offered; the deck book still is, and a
#    legacy tag book resolves to nothing rather than to a dangling selection.
cfg.update(saved[-1]);cfg.update(study_book='',review_book='cet6_kyle');saved.clear()
scope.update(local_tags=lambda: [])
def no_tags():
 d=dialog_now()
 check(book_ids(d)==['literature'],'only the deck book should remain, got %s' % book_ids(d))
 check(not any(x.isChecked() for x in book_radios(d)),'an unavailable legacy book must not stay selected')
 check(not save_button(d).isEnabled(),'nothing selected must block saving')
 next(x for x in book_radios(d) if x.property('bookId')=='literature').setChecked(True)
 save_button(d).click()
open_and(no_tags)
check(saved and saved[-1]['study_book']=='literature','the deck book must still be saveable')

# 5. The window and sync controls are on the page with their defaults, because both
#    change how Anki itself behaves and must not be buried in a config file.
cfg.update(saved[-1]);cfg.pop('hide_main_on_close',None);cfg.pop('sync_background',None);saved.clear()
def window_controls():
 d=dialog_now()
 next(x for x in book_radios(d) if x.property('bookId')=='literature').setChecked(True)
 hide=d.findChild(QWidget,'hideMainOnClose'); sync=d.findChild(QWidget,'syncBackground'); mins=d.findChild(QWidget,'syncBackgroundMinutes')
 check(hide is not None and hide.isChecked(),'关闭主窗口 must default to 只隐藏')
 check(sync is not None and sync.isChecked(),'后台同步 must be offered and on by default')
 check(mins is not None and mins.value()==5,'同步间隔 must default to 5 分钟')
 hide.setChecked(False); sync.setChecked(False)
 save_button(d).click()
open_and(window_controls)
check(saved and saved[-1]['hide_main_on_close'] is False and saved[-1]['sync_background'] is False,saved[-1] if saved else None)
check(saved and saved[-1]['sync_background_minutes']==5,saved[-1] if saved else None)

# 6. 朗读音量: Anki has no volume control, so the plug-in carries the gain itself. The dial
#    must be free (no invented cap), must apply while it is being moved, and must survive a
#    missing key as the default rather than as a crash.
applied=[]
scope.update(apply_review_volume=lambda value=None: applied.append(value), volume_preview=lambda value: applied.append(('试听', value)))
cfg.update(saved[-1]); cfg.pop('review_volume',None); saved.clear()
def volume_default():
 d=dialog_now()
 next(x for x in book_radios(d) if x.property('bookId')=='literature').setChecked(True)
 dial=d.findChild(QSpinBox,'reviewVolume')
 check(dial is not None,'朗读音量 must be on the page')
 check(dial.value()==180,'a saved profile without the key still gets the louder default, got %s' % dial.value())
 check((dial.minimum(),dial.maximum())==(50,300),'the dial must not invent a cap smaller than the plug-in supports: %s' % ((dial.minimum(),dial.maximum()),))
 check(dial.suffix()==' %','the number must read as a percentage, got %r' % dial.suffix())
 dial.setValue(240)
 check(applied and applied[-1]==240,'moving the dial must take effect at once, got %s' % applied)
 save_button(d).click()
open_and(volume_default)
check(saved and saved[-1]['review_volume']==240,saved[-1] if saved else None)

cfg.update(saved[-1]); saved.clear(); applied.clear()
def volume_reopens():
 d=dialog_now()
 next(x for x in book_radios(d) if x.property('bookId')=='literature').setChecked(True)
 dial=d.findChild(QSpinBox,'reviewVolume')
 check(dial.value()==240,'the saved gain must reopen as itself, got %s' % dial.value())
 hear=d.findChild(QWidget,'volumePreview')
 check(hear is not None,'试听 must be next to the dial so the change can be heard')
 hear.click()
 check(applied==[('试听',240)],'试听 must speak at the dialled gain, got %s' % applied)
 save_button(d).click()
open_and(volume_reopens)
check(saved and saved[-1]['review_volume']==240,saved[-1] if saved else None)

if failures:
 print('FAIL')
 for f in failures: print('  -', f)
 sys.exit(1)
print('Qt: the book list is single-select, reads the collection, migrates the legacy book, and never offers a missing one')
