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
class ShortcutEdit(QLineEdit):
 feedback=pyqtSignal(str)
 def __init__(self,m,v):super().__init__('Ctrl+Shift+F10');self.modifiers=m;self.virtual_key=v;self.valid=True
path=os.path.join(source,'__init__.py')
tree=ast.parse(open(path,encoding='utf-8').read());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='open_settings');module=ast.Module(body=[node],type_ignores=[])
scope=globals();scope.update(settings=lambda:dict(cfg),show_feedback=lambda *_a,**_k:None,format_shortcut=lambda *_:'Ctrl+Shift+F10')
exec(compile(module,path,'exec'),scope)

import types,sys
aqt=types.ModuleType('aqt'); aqt.__path__=[]
theme=types.ModuleType('aqt.theme');theme.theme_manager=types.SimpleNamespace(night_mode=True)
sys.modules['aqt']=aqt;sys.modules['aqt.theme']=theme


cfg.update(deck='四六级核心词汇',review_core_enabled=True,review_extra_decks=['四六级核心词汇','文献单词'])
saved=[]
scope.update(save_settings=lambda data:saved.append(dict(data)),controller=types.SimpleNamespace(listener=types.SimpleNamespace(registered=True,registration_error=''),review=types.SimpleNamespace(dialog=object(),start=lambda:None)))
def inspect_and_save():
 d=next(w for w in app.topLevelWidgets() if isinstance(w,QDialog) and w.isVisible())
 assert d.findChild(QComboBox,'reviewBook').findData('cet4_kyle') >= 0
 assert d.findChild(QComboBox,'reviewBook').findData('cet6_kyle') >= 0
 checks=d.findChild(QWidget,'reviewExtraDeck').findChildren(QCheckBox)
 core=next(x for x in checks if x.property('deckName')=='四六级核心词汇')
 assert core.isChecked() and not core.isEnabled() and '主牌组' in core.text()
 d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
QTimer.singleShot(100,inspect_and_save);open_settings(QWidget())
assert saved and saved[0]['review_core_enabled'] and '四六级核心词汇' in saved[0]['review_extra_decks']
cfg.update(saved[0]);QTimer.singleShot(100,inspect_and_save);open_settings(QWidget())
assert len(saved)==2
def choose_main():
 d=next(w for w in app.topLevelWidgets() if isinstance(w,QDialog) and w.isVisible())
 main=d.findChild(QComboBox,'mainReviewDeck');main.setCurrentIndex(main.findData('四六级单词'))
 checks=d.findChild(QWidget,'reviewExtraDeck').findChildren(QCheckBox)
 selected=next(x for x in checks if x.property('deckName')=='四六级单词')
 assert selected.isChecked() and not selected.isEnabled()
 d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
QTimer.singleShot(100,choose_main);open_settings(QWidget())
assert saved[-1]['review_main_deck']=='四六级单词' and saved[-1]['deck']=='四六级核心词汇'
cfg.update(saved[-1])
def inspect_main():
 d=next(w for w in app.topLevelWidgets() if isinstance(w,QDialog) and w.isVisible())
 assert d.findChild(QComboBox,'mainReviewDeck').currentData()=='四六级单词'
 d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
QTimer.singleShot(100,inspect_main);open_settings(QWidget())
cfg.update(review_extra_decks=['missing deck'], review_main_deck='四六级核心词汇')
def choose_book():
 d=next(w for w in app.topLevelWidgets() if isinstance(w,QDialog) and w.isVisible())
 book=d.findChild(QComboBox,'reviewBook');book.setCurrentIndex(book.findData('cet6_kyle'))
 save=d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save)
 assert save.isEnabled()
 save.click()
QTimer.singleShot(100,choose_book);open_settings(QWidget())
assert saved[-1]['review_book']=='cet6_kyle' and 'missing deck' in saved[-1]['review_extra_decks']
print('Qt: core main deck stays selected on save and reopen')
