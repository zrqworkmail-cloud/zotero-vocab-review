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

cfg = {'review_auto_word': False, 'review_auto_example': False, 'review_auto_example_mode': 'off',
       'review_hint_audio': False, 'review_theme': 'dark', 'review_position': 'center'}


def typing_card(word='analyze'):
    dialog = ReviewDialog({'kind': 'due', 'card_id': 7, 'mode': 'typing', 'word': word,
                           'meaning': 'v. 分析', 'example': '', 'literature': '', 'options': []},
                          'center', lambda *_a: None, cfg)
    dialog.show()
    QTest.qWait(60); app.processEvents()
    return dialog


def graded_by(dialog):
    taken = []
    dialog.grade = lambda _dialog, ease: taken.append(ease)
    return taken


def visible(dialog):
    return [button for button in dialog.grade_buttons if not button.isHidden()]


def letters(dialog):
    return [button.toolTip().split(' ')[1] for button in visible(dialog)]


# A wrong answer collapses the row to two buttons; A and B must name those two, and
# a letter with no button under it must do nothing rather than grade the card.
dialog = typing_card()
dialog.answer_button.click()
app.processEvents(); QTest.qWait(60)
assert dialog.answer_shown and dialog.force_again, (dialog.answer_shown, dialog.force_again)
assert [b.text() for b in visible(dialog)] == ['再练一次并继续', '继续学习'], [b.text() for b in visible(dialog)]
assert letters(dialog) == ['A', 'B'], letters(dialog)
taken = graded_by(dialog)
QTest.keyClick(dialog, Qt.Key.Key_D)
app.processEvents(); QTest.qWait(40)
assert taken == [], 'D has no button in the collapsed row and must not grade'
QTest.keyClick(dialog, Qt.Key.Key_B)
app.processEvents(); QTest.qWait(40)
# B is the second *visible* button. Mapping letters over the raw list would hit the
# hidden 困难 button, whose click() does nothing, so this also proves the ordering.
# force_again then pins the recorded rating to Again regardless of which button came up.
assert taken == [1], 'B must activate the second visible button, got %s' % taken
dialog.close(); app.processEvents()

# Four ratings, four letters, in order.
dialog = typing_card()
width_before = dialog.width()
for box, letter in zip(dialog.letter_boxes, 'analyze'):
    box.setText(letter)
dialog.check_button.click()
app.processEvents(); QTest.qWait(60)
assert dialog.answer_shown and not dialog.force_again, (dialog.answer_shown, dialog.force_again)
assert [b.text() for b in visible(dialog)] == ['再练一次', '困难', '记住了', '很容易'], [b.text() for b in visible(dialog)]
assert letters(dialog) == ['A', 'B', 'C', 'D'], letters(dialog)
assert 'A–D' in dialog.status.text(), dialog.status.text()
taken = graded_by(dialog)
# Before anything is pressed the row must read as "Enter would use this", not as a
# decision already made: exactly one outlined suggestion, nothing filled in.
assert [b.objectName() for b in dialog.grade_buttons].count('suggest') == 1, \
    [b.objectName() for b in dialog.grade_buttons]
assert 'chosen' not in [b.objectName() for b in dialog.grade_buttons]
for letter, ease in ((Qt.Key.Key_A, 1), (Qt.Key.Key_B, 2), (Qt.Key.Key_C, 3), (Qt.Key.Key_D, 4)):
    # start_grade latches the row; rewind it the way the next card would.
    dialog.grading = False
    for button in dialog.grade_buttons:
        button.setEnabled(True)
    QTest.keyClick(dialog, letter)
    app.processEvents(); QTest.qWait(40)
    names = [b.objectName() for b in dialog.grade_buttons]
    assert names[ease - 1] == 'chosen', '%s filled in the wrong button: %s' % (chr(65 + ease - 1), names)
    assert names.count('chosen') == 1 and 'suggest' not in names, \
        'the suggestion must give way to the button actually picked: %s' % names
    assert not dialog.grade_buttons[ease - 1].isEnabled(), 'a chosen button must still be locked against a second rating'
assert taken == [1, 2, 3, 4], 'A/B/C/D must map to the four ratings in order, got %s' % taken
# Showing the rating row must not resize the card: the buttons share one row, so
# giving them letters used to push the card from 510 to 536 wide mid-flip.
assert dialog.width() == width_before, 'revealing the ratings changed the card width %d -> %d' % (width_before, dialog.width())
dialog.close(); app.processEvents()

# Before the answer is shown the same letters belong to the spelling boxes.
dialog = typing_card('bandage')
taken = graded_by(dialog)
QTest.keyClick(dialog.letter_boxes[0], Qt.Key.Key_B)
app.processEvents(); QTest.qWait(40)
assert taken == [], 'A-D must not grade while the answer is still being typed'
assert dialog.letter_boxes[0].text() == 'b', dialog.letter_boxes[0].text()
dialog.close(); app.processEvents()

print('Qt: the rating row answers A/B/C/D, follows a collapsed row, and leaves the spelling boxes alone')
