"""Qt: the 答案面例句 switch removes the example cards and nothing else.

Three things have to stay true when the switch is off, and each one failed differently before
it was written down: the example cards must go, the 例句 hint button must NOT go (asking for an
example is the learner's own move and it prices itself as a hint), and 例句填空 must keep its
sentence because there the example *is* the question.
"""
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
from PyQt6.QtTest import QTest
app=QApplication([])

cfg_base={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
          'review_theme':'light','review_position':'center','review_plan_mode':'fixed','review_batch_size':2}
question={'kind':'due','card_id':401,'mode':'typing','word':'treat','meaning':'v. 对待；处理',
          'phonetic':'/tri:t/','example':'Treat the sample gently.| Always treat the data with care.',
          'literature':'文献例句：Treat the reagent cold.','options':[],'answer_form':'treat',
          'cloze_shown':'','roots':'','mnemonic':'','synonyms':'',
          'distinctions':'','similar_words':'','antonyms':''}


def example_headings(dialog):
    return [label.text() for label in dialog.findChildren(QLabel)
            if label.text().startswith('【') and '例句' in label.text()]


def revealed(mode='typing', show=None):
    cfg=dict(cfg_base)
    if show is not None:
        cfg['review_show_example']=show
    data=dict(question,mode=mode)
    if mode=='cloze':
        # A real cloze question carries its sentence; the other modes never do.
        data['cloze_shown']='Treat the {c1::sample} gently.'
    dialog=ReviewDialog(data,'center',lambda *_a: None,cfg)
    dialog.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
    dialog.reveal(True);app.processEvents();QTest.qWait(80)
    return dialog


# 1. Default: the examples are on the answer face, exactly as before the switch existed.
default=revealed()
assert len(example_headings(default))>=2, example_headings(default)
content_on=default.layout().sizeHint().height()

# 2. Off: no example card survives, and the answer face is measurably shorter — that is the
#    whole reason the switch exists.
off=revealed(show=False)
assert not example_headings(off), ('关掉开关后答案面不许再出现例句卡', example_headings(off))
assert off.layout().sizeHint().height()<content_on, (off.layout().sizeHint().height(), content_on)
#    Everything else on the answer face is untouched.
assert off.meaning_heading.isVisible() or any('解释' in label.text() for label in off.findChildren(QLabel))

# 3. The 例句 hint button (which the typing face carries) is not the switch's business: it is
#    the learner's own move, and it prices itself as a hint.
def aids(show):
    card=ReviewDialog(dict(question),'center',lambda *_a: None,dict(cfg_base,review_show_example=show))
    card.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
    found=[button.text() for button in card.findChildren(QPushButton) if button.objectName()=='aid']
    card.deleteLater();app.processEvents()
    return found


assert '例句' in aids(True), aids(True)
assert aids(False)==aids(True), (aids(False), aids(True))

# 4. 例句填空 keeps its sentences: there the example is the question itself, so the switch is
#    exempt — the 【例句中的形式】/【文献例句】 headings must survive it.
cloze=revealed(mode='cloze',show=False)
assert any('例句中的形式' in heading for heading in example_headings(cloze)), \
    ('例句填空的题目就是例句，开关不许把它吃掉', example_headings(cloze))
print('Qt: 答案面例句开关只删例句卡、只缩短答案面；提示按钮与例句填空都不受影响')
