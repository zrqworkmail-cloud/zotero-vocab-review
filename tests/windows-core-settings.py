import os,sys,ctypes,types,ast
base=r'D:\Program Files (x86)\Anki\app_packages';sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
dlls=[os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin')),os.add_dll_directory(os.path.dirname(base))];ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
from PyQt6.QtWidgets import QApplication,QCheckBox,QComboBox,QDateEdit,QDialog,QDialogButtonBox,QFormLayout,QGroupBox,QHBoxLayout,QLabel,QLineEdit,QPushButton,QScrollArea,QSpinBox,QTimeEdit,QVBoxLayout,QWidget
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
	BOOK_TAGS=logic.BOOK_TAGS,local_tags=local_tags,scope_decks=logic.scope_decks,scope_tags=logic.scope_tags,scope_uses_all_decks=logic.scope_uses_all_decks,
	dialog_now=dialog_now,check=check,failures=failures)
exec(compile(module,path,'exec'),scope)

import types,sys
aqt=types.ModuleType('aqt'); aqt.__path__=[]
theme=types.ModuleType('aqt.theme');theme.theme_manager=types.SimpleNamespace(night_mode=True)
sys.modules['aqt']=aqt;sys.modules['aqt.theme']=theme


def tag_boxes(d):
 return d.findChild(QWidget,'reviewScopeTags').findChildren(QCheckBox)

def deck_boxes(d):
 return d.findChild(QWidget,'reviewExtraDeck').findChildren(QCheckBox)

def save_button(d):
 return d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save)

def open_and(act):
 QTimer.singleShot(100,act);open_settings(QWidget())

saved=[]
scope.update(save_settings=lambda data:saved.append(dict(data)),controller=types.SimpleNamespace(listener=types.SimpleNamespace(registered=True,registration_error=''),review=types.SimpleNamespace(dialog=object(),start=lambda:None)))

# 1. The hardcoded book combo is gone, tags come from the collection, and a saved
#    legacy book reappears as its tag already ticked rather than being dropped.
cfg.update(deck='四六级核心词汇',review_core_enabled=True,review_extra_decks=['四六级核心词汇','文献单词'],
	review_book='cet6_kyle',review_scope_decks=[],review_scope_tags=[],review_tags_all=False,review_scope_name='')
def inspect_first():
 d=dialog_now()
 check(d.findChild(QComboBox,'reviewBook') is None,'the hardcoded 复习词书 combo should be gone')
 check([x.property('tagName') for x in tag_boxes(d)]==sorted(LOCAL_TAGS),'tags must be read from the collection')
 checked=sorted(x.property('tagName') for x in tag_boxes(d) if x.isChecked())
 check(checked==['zvr_kyle_cet6'],'legacy book must map to its tag, got %s' % checked)
 core=next(x for x in deck_boxes(d) if x.property('deckName')=='四六级核心词汇')
 check(core.isChecked() and not core.isEnabled() and '主牌组' in core.text(),'main deck must stay selected and locked')
 save_button(d).click()
open_and(inspect_first)
check(bool(saved) and saved[-1]['review_core_enabled'],'save must keep the core-word preference')
check(saved[-1]['review_book']=='' and saved[-1]['review_scope_tags']==['zvr_kyle_cet6'],'legacy book must migrate into scope tags')
check(saved[-1]['review_scope_decks']==['四六级核心词汇','文献单词'],'scope decks must be written on save')

# 2. Reopening restores the selection; a tag with a slash, the match mode and the
#    display name all round-trip.
cfg.update(saved[0]);saved.clear()
def pick_tags():
 d=dialog_now()
 checked=sorted(x.property('tagName') for x in tag_boxes(d) if x.isChecked())
 check(checked==['zvr_kyle_cet6'],'reopen must restore saved tags, got %s' % checked)
 next(x for x in tag_boxes(d) if x.property('tagName')=='zvr_kyle_cet4').setChecked(True)
 next(x for x in tag_boxes(d) if x.property('tagName')=='工作/学习').setChecked(True)
 d.findChild(QLineEdit,'reviewScopeName').setText('四级 + 六级')
 d.findChild(QComboBox,'reviewTagsMatch').setCurrentIndex(1)
 save_button(d).click()
open_and(pick_tags)
check(sorted(saved[-1]['review_scope_tags'])==['zvr_kyle_cet4','zvr_kyle_cet6','工作/学习'],'tag selection must save, got %s' % saved[-1]['review_scope_tags'])
check(saved[-1]['review_tags_all'] is True and saved[-1]['review_scope_name']=='四级 + 六级','match mode and name must round-trip')

# 3. A deck the saved config still names but which no longer exists must not clutter
#    the picker — it matches nothing either way — and must not block saving.
cfg.update(saved[-1]);cfg.update(review_extra_decks=['missing deck']);saved.clear()
def stale_legacy():
 d=dialog_now()
 check('missing deck' not in [x.property('deckName') for x in deck_boxes(d)],'a deleted deck must not be listed')
 check(save_button(d).isEnabled(),'a deleted deck alone must not block saving')
 save_button(d).click()
open_and(stale_legacy)
check(bool(saved) and saved[-1]['review_scope_name']=='四级 + 六级','saving must still work')
check('missing deck' not in saved[-1]['review_scope_decks'],'saving must not resurrect a deleted deck')

# 4. Dropped decks are named in the help text, so the scope does not change quietly,
#    and saving rewrites the scope without them.
cfg.update(saved[-1]);cfg.update(review_scope_decks=['四六级核心词汇','已删除的牌组'],review_main_deck='已删除的牌组');saved.clear()
def stale_scope():
 d=dialog_now()
 names=[x.property('deckName') for x in deck_boxes(d)]
 check('已删除的牌组' not in names,'a missing deck must not be listed, got %s' % names)
 help_text=d.findChild(QLabel,'scopeHelp').text()
 check('已删除的牌组' in help_text,'the help line should say which deck was dropped, got %r' % help_text)
 check(save_button(d).isEnabled(),'a deleted deck must not block saving')
 save_button(d).click()
open_and(stale_scope)
check(saved[-1]['review_scope_decks'] and '已删除的牌组' not in saved[-1]['review_scope_decks'],
   'saving must rewrite the scope without the deleted deck, got %s' % saved[-1]['review_scope_decks'])

# 5. Even with no tags the deleted main deck must not come back.
cfg.update(saved[-1]);cfg.update(review_scope_tags=[], review_tags_all=False)
def no_tags_left():
 d=dialog_now()
 check('已删除的牌组' not in [x.property('deckName') for x in deck_boxes(d)],'still absent without tags')
 check(d.findChild(QComboBox,'mainReviewDeck').currentData() in [x.property('deckName') for x in deck_boxes(d)],
    'the main deck must be a deck that exists')
 d.reject()
open_and(no_tags_left)

# 6. A scope that was saved as "all decks, filtered by tag" must come back that way,
#    with the now-meaningless deck list visibly disabled rather than silently applied.
cfg.update(review_scope_decks=[], review_scope_tags=['zvr_kyle_cet4'], review_tags_all=False, review_scope_name='')
def cross_deck():
	 d=dialog_now()
	 box=d.findChild(QCheckBox,'reviewAllDecks')
	 check(box is not None and box.isChecked(),'an explicit cross-deck scope must reopen with 不限牌组 ticked')
	 check(all(not x.isEnabled() for x in deck_boxes(d)),'deck choices are meaningless in cross-deck mode, so they must look disabled')
	 box.setChecked(False)
	 check(all(x.isEnabled() for x in deck_boxes(d) if '主牌组' not in x.text()),'unticking it must give the decks back')
	 box.setChecked(True)
	 save_button(d).click()
open_and(cross_deck)
check(saved[-1]['review_scope_decks']==[],'cross-deck mode must save an empty deck list')
check(saved[-1]['review_scope_tags']==['zvr_kyle_cet4'],'cross-deck mode must keep its tag')

if failures:
 print('FAIL')
 for f in failures: print('  -', f)
 sys.exit(1)
print('Qt: study scope reads from the collection, migrates the legacy book, and reports a missing in-scope deck')
