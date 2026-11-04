import os,sys,types
base=r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
dll_dirs=[os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin')),os.add_dll_directory(os.path.dirname(base))]
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
from PyQt6.QtCore import QObject,QTimer,Qt,pyqtSignal,QEvent,QRectF,QVariantAnimation,QUrl,QPoint,QEasingCurve
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
for _f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(_f)
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

cfg={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
     'review_theme':'dark','review_position':'center','review_plan_mode':'fixed',
     'review_batch_size':10,'model':'四六级单词模板','deck':'Literature'}


def card(mode, options, height=710):
    dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': mode, 'word': 'statistic',
                           'meaning': 'n. 程度', 'example': '', 'literature': '',
                           'options': options, 'judgment_correct': True,
                           'judgment_statement': 'statistic — n. 程度'},
                          'center', lambda *_a: None, cfg)
    dialog.resize(510, height)
    dialog.show()
    QTest.qWait(60); app.processEvents(); QTest.qWait(60)
    return dialog


# 1. 判断题的两个选项不许被窗口剩余高度撑大。量出来的事实：选项自身高度是 37 px，
#    而在 710 px 的窗口里它们被拉成 190 px —— 因为每个选项都带了 stretch=1。
judgment = card('judgment', ['正确', '错误'])
heights = [row.height() for row in judgment.choice_buttons]
natural = [row.sizeHint().height() for row in judgment.choice_buttons]
assert max(heights) <= max(natural) + 8, ('选项应当只占自己内容的高度', heights, natural)
assert sum(heights) <= 100, ('两个判断题选项不该吃掉半扇窗口', heights)

# 2. 四选项的选择题同理：短选项不该变成 100 px 的色块。
choice = card('choice', ['程度', '统计', '学位', '状态'])
choice_heights = [row.height() for row in choice.choice_buttons]
assert max(choice_heights) <= max(r.sizeHint().height() for r in choice.choice_buttons) + 8, choice_heights

# 3. 选项高度与窗口高度解耦：把窗口拉高一倍，选项不该跟着长。
tall = card('judgment', ['正确', '错误'], height=710)
short = card('judgment', ['正确', '错误'], height=430)
tall_rows = [row.height() for row in tall.choice_buttons]
short_rows = [row.height() for row in short.choice_buttons]
assert tall_rows == short_rows, ('同一道题，窗口高低不该改变选项高度', tall_rows, short_rows)
assert max(tall_rows) <= 45, tall_rows

# 4. 换卡时窗口几何不许跳（windows-next-card-transition.py 钉过的既定行为）：
#    修选项不能以"收缩宿主窗口"为代价。
host = card('judgment', ['正确', '错误'], height=680)
before = host.geometry()
inner = card('judgment', ['正确', '错误'])
inner._embedded = True
inner.setParent(host, Qt.WindowType.Widget)
host._embedded_dialog = inner
inner.setGeometry(host.rect())
inner.show()
QTest.qWait(60); app.processEvents(); QTest.qWait(60)
inner.fit_card_height()
QTest.qWait(60); app.processEvents()
assert host.geometry() == before, ('内嵌卡的收缩只许动自己，不许动宿主窗口',
                                   host.geometry(), before)
assert inner.geometry() == host.rect(), ('内嵌卡必须铺满它的窗口，否则就是重影',
                                          inner.geometry(), host.rect())

print('Qt: 判断题/选择题的选项只占内容高度，窗口贴住内容，内嵌卡始终铺满窗口')
