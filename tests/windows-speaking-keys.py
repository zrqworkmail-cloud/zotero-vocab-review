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
from zotero_global_capture.review_popup import ReviewDialog, DesktopReviewController


from PyQt6.QtTest import QTest
app=QApplication([])

from zotero_global_capture import review_popup as rp

ReviewDialog.speak_many = lambda self, texts: True
for _f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(_f)

cfg = {'review_auto_word': False, 'review_auto_example': False, 'review_auto_example_mode': 'off',
       'review_hint_audio': False, 'review_theme': 'dark', 'review_position': 'center'}
question = {'kind': 'due', 'card_id': 7, 'mode': 'speaking', 'word': 'instance',
            'meaning': 'n. 情况，例子\nn. 例子，实例，事例', 'example': '', 'literature': '', 'options': []}


def open_card():
    dialog = ReviewDialog(dict(question), 'center', lambda *_a: None, cfg)
    dialog.show()
    QTest.qWait(80)
    app.processEvents()
    QTest.qWait(80)
    return dialog


def menu_button(dialog):
    return next(button for button in dialog.findChildren(QPushButton) if button.objectName() == 'cardMenu')


# Focus must land on the answering button, not on the '...' menu.
dialog = open_card()
assert dialog.spoken_answer_button.hasFocus(), \
    'Enter would activate whatever has focus; menu button focused = %s' % menu_button(dialog).hasFocus()
assert '回车' in dialog.status.text() and '空格' in dialog.status.text(), dialog.status.text()

# Enter: "I said it" -> reveal without forcing Again.
QTest.keyClick(dialog, Qt.Key.Key_Return)
app.processEvents(); QTest.qWait(60)
assert not menu_button(dialog).menu().isVisible(), 'Enter opened the card menu instead of answering'
assert dialog.answer_shown and dialog.enter_ease is None and not dialog.force_again, \
    (dialog.answer_shown, dialog.enter_ease, dialog.force_again)
assert '请听发音并选择评分' in dialog.status.text(), dialog.status.text()
dialog.close(); app.processEvents()

# Space: "could not recall" -> reveal as incorrect, which forces Again.
dialog = open_card()
QTest.keyClick(dialog, Qt.Key.Key_Space)
app.processEvents(); QTest.qWait(60)
assert not menu_button(dialog).menu().isVisible(), 'Space opened the card menu'
assert dialog.answer_shown and dialog.force_again, (dialog.answer_shown, dialog.force_again)
assert dialog.grade_buttons[0].text() == '再练一次并继续', dialog.grade_buttons[0].text()
dialog.close(); app.processEvents()

# After the answer is shown, Enter must go back to grading, not to the two prompts.
dialog = open_card()
dialog.spoken_answer_button.click()
app.processEvents(); QTest.qWait(60)
graded = []
dialog.grade = lambda *_a: graded.append('grade')
dialog.enter_ease = 3
QTest.keyClick(dialog, Qt.Key.Key_Return)
app.processEvents(); QTest.qWait(60)
assert graded == ['grade'], 'Enter after reveal should submit the suggested rating, got %s' % graded
dialog.close()

print('Qt: speaking card answers with Enter/Space and never opens the card menu')
