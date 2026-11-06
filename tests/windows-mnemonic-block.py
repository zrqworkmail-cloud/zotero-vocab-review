"""The card paints the mnemonic block from the shipped table, and stays silent without a row.

The harness is copied from windows-question-audio.py so the stubbed speech, the config and
the import dance cannot drift. What is pinned is the visible half of the 2026-11-06 change:
a word the table knows gets the block with its decomposition inside, and a word it does not
know gets no block at all -- not an empty frame.
"""
import os,sys,types
base=r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin'))
os.add_dll_directory(os.path.dirname(base))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
from PyQt6.QtCore import QObject,QTimer,Qt,pyqtSignal,QEasingCurve,QEvent,QRectF,QVariantAnimation,QUrl,QPoint
from PyQt6.QtGui import QCursor,QFont,QFontDatabase,QFontMetrics,QColor,QPainter,QDesktopServices,QKeyEvent
from PyQt6.QtWidgets import QApplication,QComboBox,QDialog,QHBoxLayout,QLabel,QLineEdit,QMenu,QMessageBox,QPushButton,QScrollArea,QStyle,QVBoxLayout,QWidget
aqt=types.ModuleType('aqt');aqt.mw=types.SimpleNamespace()
qt=types.ModuleType('aqt.qt')
for n in ('QObject','QTimer','Qt','pyqtSignal','QEasingCurve','QEvent','QRectF','QVariantAnimation','QUrl','QColor','QPainter','QDesktopServices','QMenu','QMessageBox','QCursor','QFontMetrics','QApplication','QComboBox','QDialog','QHBoxLayout','QLabel','QLineEdit','QPushButton','QScrollArea','QStyle','QVBoxLayout','QWidget'): setattr(qt,n,globals()[n])
sys.modules['aqt']=aqt;sys.modules['aqt.qt']=qt
package=types.ModuleType('zotero_global_capture');package.__path__=[os.path.abspath(os.path.join(os.path.dirname(__file__),'..','anki-global-addon','zotero_global_capture'))];sys.modules['zotero_global_capture']=package
from zotero_global_capture.review_popup import ReviewDialog
from PyQt6.QtTest import QTest

app=QApplication([])
for f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(f)
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

CFG={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
     'review_theme':'dark','review_position':'center','review_plan_mode':'fixed',
     'review_batch_size':10,'model':'四六级单词模板','deck':'Literature'}
MEANING='adj. 危险的；冒险的'
OPTIONS=['adj. 量的；定量的','adj. 危险的；冒险的','adj. 外部的；对外的','adj. 口头的；口的']

SPOKEN=[]
ReviewDialog.speak_many=lambda self,texts: SPOKEN.append(tuple(texts)) or True

def card(mode, word='hazardous'):
    question={'kind':'due','card_id':1,'mode':mode,'word':word,'meaning':MEANING,
              'example':'','literature':'','options':OPTIONS,'phonetic':'hɑːzədəs'}
    if mode=='judgment':
        # A judgment card is the word paired with a claim about it; the claim is what the
        # learner reads, so the builder needs it.
        question.update(options=['正确','错误'], judgment_statement=MEANING, judgment_correct=True)
    dialog=ReviewDialog(question,'center',lambda *_a:None,dict(CFG))
    dialog.show();QTest.qWait(60);app.processEvents()
    return dialog

def press_enter(dialog):
    target=dialog.focusWidget() or dialog
    QApplication.sendEvent(target,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Return,
                                           Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(target,QKeyEvent(QEvent.Type.KeyRelease,Qt.Key.Key_Return,
                                           Qt.KeyboardModifier.NoModifier))
    app.processEvents();QTest.qWait(40);app.processEvents()

from zotero_global_capture.review_logic import mnemonic_for as env_mnemonic, question_mnemonic as env_question_mnemonic

# ---------------------------------------------------------------------------
# The answer face must actually paint the 【识记方法】 block. That heading has existed
# in the card since the template era, but the 四六级单词模板 has no such field, so the
# block was dead code for every word until the shipped table was wired in (2026-11-06).
def headings(dialog):
    return [label.text() for label in dialog.findChildren(QLabel)
            if label.isVisible() and (label.text() or '').startswith('【')]


def detail_text(dialog, heading):
    for label in dialog.findChildren(QLabel):
        if label.text() == heading:
            card = label.parentWidget().parentWidget()
            return ' '.join(other.text() for other in card.findChildren(QLabel))
    return ''


def env_note_mnemonic(word):
    """What the card gets for a real note: the 四六级单词模板 has no 识记方法 field at all,
    so an empty note is exactly the production case, and it must still come back with text."""
    return env_question_mnemonic({'fields': {}}, word)


hit = dict(CFG)
question = {'kind': 'due', 'card_id': 1, 'mode': 'typing', 'word': 'rebellion',
            'meaning': 'n. 反叛；反抗；谋反', 'example': 'an armed rebellion',
            'literature': '', 'options': [], 'phonetic': 'rɪˈbeljən',
            'mnemonic': env_note_mnemonic('rebellion')}
dialog = ReviewDialog(question, 'center', lambda *_a: None, dict(hit))
dialog.show(); QTest.qWait(60); app.processEvents()
dialog.reveal(True); app.processEvents(); QTest.qWait(40)
assert question['mnemonic'], '样本词必须在表里，否则这条检查证明不了任何事'
assert '【识记方法】' in headings(dialog), headings(dialog)
body = detail_text(dialog, '【识记方法】')
assert 'bell' in body, ('标题有了但内容没画上', body[:120])
dialog.deleteLater(); QTest.qWait(40)

miss = ReviewDialog({'kind': 'due', 'card_id': 2, 'mode': 'typing', 'word': 'zzznotaword',
                     'meaning': 'n. 占位', 'example': '', 'literature': '', 'options': [],
                     'phonetic': '', 'mnemonic': env_note_mnemonic('zzznotaword')},
                    'center', lambda *_a: None, dict(hit))
miss.show(); QTest.qWait(60); app.processEvents()
miss.reveal(True); app.processEvents(); QTest.qWait(40)
assert env_note_mnemonic('zzznotaword') == '', '样本词不该在表里'
assert '【识记方法】' not in headings(miss), \
    ('表里没有就该完全不出现，而不是留个空框', headings(miss))
miss.deleteLater(); QTest.qWait(40)

print('Qt: 表里有就画出【识记方法】并带上拆解内容，表里没有就一个像素都不占')
