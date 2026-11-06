"""The answer face's status row must fit ONE line, and the evidence must still exist.

The learner's complaint was about space (2026-11-05): the row wrapped to two lines. The
fix moved the accounting into the tooltip, so this check measures the two things that
actually matter on screen — the row's height, and whether the tooltip still carries every
non-zero count — rather than asserting a string nobody reads.
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
from PyQt6.QtGui import QCursor,QFont,QFontDatabase,QFontMetrics,QColor,QPainter,QDesktopServices
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
SPOKEN=[]
ReviewDialog.speak_many=lambda self,texts: SPOKEN.append(tuple(texts)) or True
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

CFG={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':True,
     'review_theme':'dark','review_position':'center','review_plan_mode':'fixed',
     'review_batch_size':10,'model':'四六级单词模板','deck':'Literature'}
WORD='characteristic'

def card(mode='typing', word=WORD):
    dialog=ReviewDialog({'kind':'due','card_id':1,'mode':mode,'word':word,
                         'meaning':'adj. 典型的，特有的；n. 特征','example':'It was characteristic.',
                         'literature':'',
                         'options':['典型的','系数','观察','理想']},'center',lambda *_a:None,dict(CFG))
    dialog.show();QTest.qWait(60);app.processEvents()
    return dialog

def one_line(dialog):
    status=dialog.status
    metrics=status.fontMetrics()
    # A wrapped label reports the height it actually got; one line is lineSpacing plus the
    # label's own margin, so anything past that means the row took a second line.
    return status.height() <= metrics.lineSpacing()*2, status.height(), metrics.lineSpacing()

# 1. A spelling card that used every kind of hint still shows one line, and the tooltip
#    carries the counts that used to live in the line.
dialog=card()
for box,(_,expected) in zip(dialog.letter_boxes, dialog.letter_positions):
    box.setText('x' if box.index in (2,5) else expected)
dialog.check_input();app.processEvents()          # wrong letters -> 错误字母计数
dialog.hear_hint([WORD]);dialog.hear_hint([WORD]) # 发音两次
dialog.add_hint();dialog.add_hint()
for box,(_,expected) in zip(dialog.letter_boxes, dialog.letter_positions):
    box.setText(expected)
dialog.check_input();app.processEvents()          # now correct, and it flips
assert dialog.answer_shown, 'the card did not reveal'
fits,height,spacing=one_line(dialog)
assert fits, ('状态行必须只占一行', height, spacing)
assert dialog.status.text().startswith('建议 '), dialog.status.text()
assert '·' in dialog.status.text(), dialog.status.text()
tip=dialog.status.toolTip()
assert '发音提示' in tip and '字母提示' in tip, tip
assert '0 次' not in tip, ('零项不许出现在依据里', tip)
dialog.deleteLater();QTest.qWait(40)

# 2. A flawless spelling: the tooltip says 无提示 rather than a list of zeros.
dialog=card(mode='typing', word='loaf')
for box,(_,expected) in zip(dialog.letter_boxes, dialog.letter_positions):
    box.setText(expected)
dialog.check_input();app.processEvents()
assert dialog.status.toolTip()=='无提示', dialog.status.toolTip()
assert 'Mastered' in dialog.status.text(), dialog.status.text()
dialog.deleteLater();QTest.qWait(40)

# 3. A choice card keeps the clock, but in the tooltip — speed is why E was not offered.
dialog=card(mode='choice', word='shrimp')
import time
dialog.shown_at=time.monotonic()-9.2      # reveal() computes the clock from when it appeared
dialog.reveal(True);app.processEvents()
fits,height,spacing=one_line(dialog)
assert fits, ('选择题的状态行也只许一行', height, spacing)
assert '用时 9.2 秒' in dialog.status.toolTip(), dialog.status.toolTip()
assert '用时' not in dialog.status.text(), dialog.status.text()
dialog.deleteLater();QTest.qWait(40)

print('Qt: 答案面状态行只占一行，完整依据在鼠标提示里，零项不显示')
