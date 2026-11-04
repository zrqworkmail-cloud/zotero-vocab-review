"""Measure how tall the question-side option rows actually get, per mode.

The judgment card came in with two 240px blocks, which is a layout fact I can read straight
off the widgets instead of guessing from a screenshot.
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
aqt.mw.col=object();aqt.mw.state='deckBrowser'

cfg={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
     'review_theme':'dark','review_position':'center','review_plan_mode':'fixed','review_batch_size':10,
     'model':'四六级单词模板','deck':'Literature'}


def card(mode, options, height):
    dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': mode, 'word': 'statistic',
                           'meaning': 'n. 程度', 'example': '', 'literature': '',
                           'options': options, 'judgment_correct': True,
                           'judgment_statement': 'statistic — n. 程度'},
                          'center', lambda *_a: None, cfg)
    dialog.resize(510, height)
    dialog.show()
    QTest.qWait(60); app.processEvents(); QTest.qWait(60)
    return dialog


for mode, options in (('judgment', ['正确', '错误']), ('choice', ['程度', '统计', '学位', '状态'])):
    for height in (360, 710):
        dialog = card(mode, options, height)
        rows = dialog.choice_buttons
        used = sum(row.height() for row in rows)
        print('%-9s card=%d  rows=%s  used=%d (%d%% of the card)' % (
            mode, dialog.height(), [row.height() for row in rows], used,
            round(100 * used / dialog.height())))
        print('           sizeHints=%s' % [row.sizeHint().height() for row in rows])
