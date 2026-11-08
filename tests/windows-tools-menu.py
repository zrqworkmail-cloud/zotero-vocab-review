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
from zotero_global_capture.review_popup import ReviewDialog
from zotero_global_capture import review_logic as logic
from PyQt6.QtTest import QTest
app=QApplication([])

# Anki 的工具菜单被插件塞进了 11 条，日常只用的三条被七条词书维护项淹了。
# 现在插件只留两条：设置入口 + 一个「单词随身复习」子菜单。
import ast, importlib.util, os
source=os.path.join(os.path.dirname(__file__), '..', 'anki-global-addon', 'zotero_global_capture', '__init__.py')
tree=ast.parse(open(source,encoding='utf-8').read())
wanted=('menu_action','study_book_menu')
scope=globals()
cfg={'review_enabled':True,'study_book':'cet6_core','review_book':'','deck':'文献单词',
     'review_scope_tags':[],'review_tags_all':False,'review_core_enabled':True}
scope.update(settings=lambda: dict(cfg), mw=aqt.mw, controller=types.SimpleNamespace(
    review=types.SimpleNamespace(show_next=lambda *_a: None)),
    open_settings=lambda *a: None, import_core_words=lambda: None, browse_core_words=lambda: None,
    setup_cet6_books=lambda: None, browse_cet6_book=lambda key: None, open_cet6_listening=lambda: None,
    study_books=lambda c: [{'id':'cet6_core','name':'六级核心'},{'id':'cet6_full','name':'六级全表'}],
    study_book_id=lambda c: 'cet6_core', book_card_count=lambda book: 439,
    selection_entries=logic.selection_entries,
    choose_study_book=lambda key: None, write_quality_report=lambda: None)
for name in wanted:
    node=next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), source, 'exec'), scope)

tools=QMenu()
aqt.mw.form=types.SimpleNamespace(menuTools=tools)
scope['mw'].form=aqt.mw.form
scope['menu_action']()

top=[action for action in tools.actions()]
ours=[action.text() for action in top if action.text() and not action.isSeparator()]
assert len(ours)==2, 'the plug-in should leave exactly two entries in Tools, got %s' % ours
assert '全局划词入 Anki 设置…' in ours, ours
assert '单词随身复习' in ours, ours

menu=[action.menu() for action in top if action.text()=='单词随身复习'][0]
daily=[action.text() for action in menu.actions() if action.text()]
assert daily[:3]==['立即弹出一张','切换词书','六级听力：本地真题与模拟'], daily
assert any('词书与词表管理' in text for text in daily), daily
# The audit entry belongs with the daily actions, and its name has to say what it will not do.
assert any('复习质量报告' in text and '只读' in text for text in daily),     daily
assert not any('浏览核心词汇' in text or '补充缺失词汇' in text for text in daily),     'the maintenance actions must not sit next to the daily ones: %s' % daily

manage=[action.menu() for action in menu.actions() if action.text()=='词书与词表管理'][0]
kept=[action.text() for action in manage.actions() if action.text()]
for label in ('四六级核心词：补充缺失词汇','四六级核心词：查看词表','六级词书：建立核心与完整词书',
              '六级词书：浏览核心词汇','六级词书：浏览完整词汇','四级词书（KyleBing）：查看词汇',
              '六级词书（KyleBing）：查看词汇'):
    assert label in kept, 'nothing may be dropped, only moved: %s not in %s' % (label, kept)
assert any(action.isSeparator() for action in menu.actions()), 'daily and maintenance need a line between them'

# 切换词书 still counts its cards on open, wherever it now lives.
book_menu=[action.menu() for action in menu.actions() if action.text()=='切换词书'][0]
book_menu.aboutToShow.emit()
assert [action.text() for action in book_menu.actions()]==['六级核心　439 张','六级全表　439 张'],     [action.text() for action in book_menu.actions()]
assert book_menu.actions()[0].isChecked(), 'the current book must read as chosen'
print('Qt: Tools carries two plug-in entries, the daily three plus the read-only report up front, the seven maintenance items one level down')
