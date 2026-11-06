"""The celebration must never paint over the word it is celebrating — proved by pixels.

Why pixels and not geometry: a colour heuristic "found" the badge on the word row in 8/8 live
captures and every one of those hits was ClearType fringe, and the analytic reach under-read
the real one by 25%. So this renders the same card twice at the same size — celebration off,
celebration on — and asserts that **not one changed pixel** lands inside the answer word's
rectangle, on every tier. That is the only claim the learner can see, so it is the only claim
worth pinning.
"""
import os,sys,types
base=r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin')); os.add_dll_directory(os.path.dirname(base))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
from PyQt6.QtCore import QObject,QPoint,QRect,QEvent,Qt,pyqtSignal,QRectF,QVariantAnimation,QUrl,QTimer,QEasingCurve
from PyQt6.QtGui import QCursor,QFontDatabase,QFontMetrics,QColor,QPainter,QDesktopServices
from PyQt6.QtWidgets import QApplication,QComboBox,QDialog,QHBoxLayout,QLabel,QLineEdit,QMenu,QMessageBox,QPushButton,QScrollArea,QSizePolicy,QStyle,QVBoxLayout,QWidget
aqt=types.ModuleType('aqt');aqt.mw=types.SimpleNamespace()
qt=types.ModuleType('aqt.qt')
for n in ('QObject','QTimer','Qt','pyqtSignal','QEasingCurve','QEvent','QRect','QRectF','QVariantAnimation','QUrl','QColor','QPainter','QDesktopServices','QMenu','QMessageBox','QCursor','QFontMetrics','QApplication','QComboBox','QDialog','QHBoxLayout','QLabel','QLineEdit','QPushButton','QScrollArea','QStyle','QSizePolicy','QVBoxLayout','QWidget','QPoint'):
    setattr(qt,n,globals()[n])
sys.modules['aqt']=aqt;sys.modules['aqt.qt']=qt
package=types.ModuleType('zotero_global_capture');package.__path__=[os.path.abspath(os.path.join(os.path.dirname(__file__),'..','anki-global-addon','zotero_global_capture'))];sys.modules['zotero_global_capture']=package
from zotero_global_capture.review_popup import ReviewDialog
from zotero_global_capture import card_motion
from PyQt6.QtTest import QTest

app=QApplication([])
for f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(f)
ReviewDialog.speak_many=lambda self,texts:True
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

CFG={'review_auto_word':False,'review_auto_example_mode':'off','review_theme':'dark',
     'review_position':'center','review_plan_mode':'fixed','review_batch_size':10,
     'model':'四六级单词模板','deck':'Literature','review_motion_hop':True}
MEANING='adj. 能实行的；适用的；可行的'

def frame(word, tier, celebrate, height=630):
    dialog=ReviewDialog({'kind':'due','card_id':1,'mode':'typing','word':word,
                         'meaning':MEANING,'example':'It was a characteristic smile.',
                         'literature':'这是一条例句。','options':[],'phonetic':"præktɪkəb(ə)l"},
                        'center',lambda *_a:None,dict(CFG,review_motion_celebration=celebrate))
    dialog.show(); dialog.resize(526,height); app.processEvents(); QTest.qWait(60)
    for box,(_,expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText(expected)
    dialog.reveal(True); app.processEvents(); QTest.qWait(60)
    if celebrate:
        overlay=dialog.celebration
        word_row, rows = dialog.celebration_rows()
        overlay.play(tier, dialog.cfg, word_row=word_row, protected=rows)
        overlay.progress=0.42
        # Called outside paintEvent on purpose: PyQt turns an unhandled Python exception
        # raised inside a reimplemented virtual into qFatal/abort, which on Windows dies as
        # 0xC0000409 with no traceback at all — that is how a missing name hid for a whole
        # session while every Qt check "just exited 127". Here it still prints.
        overlay._place()
        overlay.update(); app.processEvents(); QTest.qWait(40)
    image=dialog.grab().toImage()
    word_row, rows = dialog.celebration_rows()
    dialog.deleteLater(); app.processEvents(); QTest.qWait(40)
    return image, word_row

def changed_in_row(a, b, row):
    total = 0
    for y in range(max(0, int(row.top())), min(a.height(), int(row.bottom()) + 1)):
        for x in range(a.width()):
            if a.pixelColor(x, y) != b.pixelColor(x, y):
                total += 1
    return total

for word in ('practicable', 'loaf'):
    for tier in (1, 2, 3, 4):
        plain, _ = frame(word, tier, False)
        badge, row = frame(word, tier, True)
        hits = changed_in_row(plain, badge, row)
        assert hits == 0, (word, tier, hits, '庆祝把像素画到了单词行上', row)
        # and the badge is still drawn at all — a guard that only passes because nothing
        # is painted would be worse than the bug it replaces
        painted = sum(1 for y in range(badge.height()) for x in range(0, badge.width(), 3)
                      if plain.pixelColor(x, y) != badge.pixelColor(x, y))
        assert painted > 200, (word, tier, painted, '庆祝根本没画出来，检查就失去了意义')

print('Qt: 四档庆祝都不往单词行上画一个像素，且确实画了东西')
