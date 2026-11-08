import os,sys,types,time
base=r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
dll_dirs=[os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin')),os.add_dll_directory(os.path.dirname(base))]
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont,QFontDatabase
from PyQt6.QtWidgets import QApplication,QCheckBox,QLabel,QPushButton,QWidget
package=types.ModuleType('zotero_global_capture');package.__path__=[os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'anki-global-addon', 'zotero_global_capture'))];sys.modules['zotero_global_capture']=package
from zotero_global_capture.selection_ui import SelectionPicker
from zotero_global_capture import review_logic as logic

app=QApplication([])
for path in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    if os.path.exists(path): QFontDatabase.addApplicationFont(path)
app.setFont(QFont('Microsoft YaHei', 10))

BOOKS=[{'id':'core','name':'六级核心','tag':'zvr_cet6_core'},
       {'id':'full','name':'六级全表','tag':'zvr_cet6_full'},
       {'id':'lit','name':'文献单词','deck':'文献单词'}]
CFG={'deck':'文献单词','model':'Words','study_books':BOOKS}
DELAY=[0.0]
CALLS=[]
TAG_CARDS={'zvr_cet6_core':9,'zvr_cet6_full':9,'高频':5,'真题':3}
def api(action,params):
    CALLS.append(action)
    if DELAY[0]: time.sleep(DELAY[0])
    if action=='deckNames': return ['文献单词']
    if action=='getDeckStats': return {'1':{'name':params['decks'][0],'new_count':7,'learn_count':2,'review_count':3}}
    if action=='getTags': return list(TAG_CARDS)
    if action=='multi':
        answers=[]
        for inner in params['actions']:
            tag=inner['params']['query'].rstrip().split('tag:"')[-1].rstrip('"')
            answers.append(list(range(TAG_CARDS.get(tag,0))))
        return answers
    if action=='findCards':
        query=params['query']
        if '-tag:' in query: return [1,2]          # （无标签）count
        if 'is:new' in query: return list(range(7))
        if 'is:due' in query: return list(range(5))
        return [1]
    raise AssertionError(action)

def wait_for(predicate,timeout=5.0):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate(): return True
        time.sleep(0.02)
    return False

def rows(picker):
    # Layout order, not findChildren order — findChildren returns creation order and would
    # mask a reorder that never moved the widget on screen.
    layout=picker.layout()
    return [layout.itemAt(i).widget() for i in range(layout.count())
            if layout.itemAt(i).widget() is not None and layout.itemAt(i).widget().objectName()=='selectionRow']
def row(picker,book_id):
    return next(w for w in rows(picker) if w.property('bookId')==book_id)
def check_of(r): return r.findChild(QCheckBox,'selectionBook')
def summary_of(r): return r.findChild(QLabel,'selectionSummary').text()
def tags_of(r): return r.findChild(QWidget,'selectionTags').findChildren(QCheckBox,'selectionTag')
def tag_box(r,tag): return next(b for b in tags_of(r) if b.property('tag')==tag)

def entries(*items):
    return [{'book':next(b for b in BOOKS if b['id']==book_id),'tags':list(tags)} for book_id,tags in items]

# 1. Rows render at once: selected entries first in their saved order, the rest after.
picker=SelectionPicker(BOOKS,entries(('full',['高频']),('core',[])),api,CFG)
assert [w.property('bookId') for w in rows(picker)]==['full','core','lit'],[w.property('bookId') for w in rows(picker)]
assert check_of(row(picker,'full')).isChecked() and check_of(row(picker,'core')).isChecked()
assert not check_of(row(picker,'lit')).isChecked()
assert picker.value()==[{'book':'full','tags':['高频']},{'book':'core','tags':[]}],picker.value()
assert '标签 1 项' in summary_of(row(picker,'full')),summary_of(row(picker,'full'))
assert '整本' in summary_of(row(picker,'core')),summary_of(row(picker,'core'))

# 2. Unchecking removes the entry but keeps its tag subset for when it comes back.
check_of(row(picker,'full')).setChecked(False)
assert picker.value()==[{'book':'core','tags':[]}],picker.value()
check_of(row(picker,'full')).setChecked(True)
assert picker.value()==[{'book':'full','tags':['高频']},{'book':'core','tags':[]}],picker.value()

# 3. ↑↓ reorders the list, and the saved order follows the rows.
changed=[]
picker.changed.connect(lambda: changed.append(True))
row(picker,'core').findChild(QPushButton,'selectionUp').click()
assert [w.property('bookId') for w in rows(picker)]==['core','full','lit']
assert picker.value()==[{'book':'core','tags':[]},{'book':'full','tags':['高频']}],picker.value()
assert changed,'reordering must emit changed'
row(picker,'core').findChild(QPushButton,'selectionDown').click()
assert [w.property('bookId') for w in rows(picker)]==['full','core','lit']

# 4. Expanding lists the tags really on the book, with counts, plus （无标签）as a row.
row(picker,'full').findChild(QPushButton,'selectionExpand').click()
assert wait_for(lambda: len(tags_of(row(picker,'full')))>=4),'tag checkboxes never arrived'
full=row(picker,'full')
labels=[b.text() for b in tags_of(full)]
assert '高频 (5)' in labels and '真题 (3)' in labels and '（无标签） (2)' in labels,labels
assert tag_box(full,'高频').isChecked() and not tag_box(full,'真题').isChecked()
tag_box(full,'真题').setChecked(True)
assert '标签 2 项' in summary_of(full),summary_of(full)
assert picker.value()[0]=={'book':'full','tags':['高频','真题']},picker.value()
tag_box(full,'高频').setChecked(False);tag_box(full,'真题').setChecked(False)
assert '整本' in summary_of(full),summary_of(full)
assert picker.value()[0]=={'book':'full','tags':[]},picker.value()

# 5. （无标签）is checkable and travels in the tags list as the sentinel.
tag_box(full,logic.UNTAGGED).setChecked(True)
assert picker.value()[0]=={'book':'full','tags':[logic.UNTAGGED]},picker.value()
tag_box(full,logic.UNTAGGED).setChecked(False)

# 6. A saved tag with no cards left is still listed, checked, counted zero.
picker2=SelectionPicker(BOOKS,entries(('full',['已消失'])),api,CFG)
row(picker2,'full').findChild(QPushButton,'selectionExpand').click()
assert wait_for(lambda: len(tags_of(row(picker2,'full')))>=4)
ghost=tag_box(row(picker2,'full'),'已消失')
assert ghost.isChecked() and '(0)' in ghost.text(),ghost.text()
picker2.deleteLater()

# 7. Stats are async: the constructor returns before any number is on screen, and the
#    numbers fill in later. A settings page that waited for these would be the slow dialog.
DELAY[0]=0.3
picker3=SelectionPicker(BOOKS,entries(('core',[])),api,CFG)
assert all('新词' not in summary_of(r) for r in rows(picker3)),'stats must not block construction'
assert wait_for(lambda: all('新词 7' in summary_of(r) and '到期 5' in summary_of(r) for r in rows(picker3))),'stats never arrived'
DELAY[0]=0.0
picker3.deleteLater()

# 8. An empty catalogue renders no rows and saves an empty selection.
picker4=SelectionPicker([],[],api,CFG)
assert rows(picker4)==[] and picker4.value()==[]
picker4.deleteLater()
picker.deleteLater()
app.processEvents()
print('Qt: 词组多选勾选/排序/展开标签/异步统计/子集保留/无标签行/零计数标签')