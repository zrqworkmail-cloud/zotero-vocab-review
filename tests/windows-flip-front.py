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

# 看回题目：答案翻出来之后，正面并没有消失的权利。用户要求翻到反面后还能再看一眼题目，
# 而这一眼不许改动评分、不许重开窗口、不许动宽度。
cfg={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
     'review_theme':'light','review_position':'center','review_plan_mode':'fixed','review_batch_size':2}
graded=[]
question={'kind':'due','card_id':301,'mode':'typing','word':'treat','meaning':'v. 对待；处理',
          'phonetic':'/tri:t/','example':'Treat the sample gently.','literature':'','options':[],
          'answer_form':'treat'}
dialog=ReviewDialog(question,'center',lambda *_a: graded.append(_a),cfg)
dialog.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)

# 1. On the question face F is an ordinary letter: it must reach the spelling boxes.
dialog.letter_boxes[0].setFocus();app.processEvents();QTest.qWait(40)
QTest.keyClick(dialog.letter_boxes[0], Qt.Key.Key_F);app.processEvents();QTest.qWait(40)
assert dialog.letter_boxes[0].text().upper()=='F',    'F has to type on the question face, not flip it: %r' % [b.text() for b in dialog.letter_boxes]
assert not dialog.answer_shown

# 2. Type the word and reveal.
for box, char in zip(dialog.letter_boxes, 'treat'):
    box.setText(char); box.textChanged.emit(box.text())
app.processEvents();QTest.qWait(40)
dialog.answer_button.click();app.processEvents();QTest.qWait(80)
assert dialog.answer_shown and not graded, (dialog.answer_shown, graded)
assert dialog.grade_widget.isVisible() and dialog.result_label.isVisible()
front=[w for w in (dialog.question_label, dialog.meaning_heading, getattr(dialog,'phonetic_label',None)) if w is not None]
assert not any(w.isVisible() for w in front), 'the answer face hides the prompt'
width_before, top_before = dialog.width(), dialog.y()

# 3. Shift+F shows the front again, without un-revealing or grading anything. Plain f must
#    then type into the spelling box: until 2026-11-06 the flip sat on bare F, and the probe
#    showed the letter being eaten — the face flipped back and nothing was typed.
QTest.keyClick(dialog, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier);app.processEvents();QTest.qWait(80)
assert dialog.showing_front, 'Shift+F must report the face it is on'
assert all(w.isVisible() for w in front), [ (w.objectName(), w.isVisible()) for w in front ]
assert dialog.letter_boxes and dialog.letter_scroll.isVisible(), 'the typed letters belong to the front'
assert not dialog.grade_widget.isVisible() and not dialog.result_label.isVisible(),    'no rating row on the front: A-E would fire while the user is only reading'
assert not dialog.book_chip.isVisible(), 'the word-list pills describe the answer'
assert dialog.answer_shown and not graded, (dialog.answer_shown, graded)

# 3b. The letter that used to be stolen now reaches the box, and the face does not move.
dialog.letter_boxes[0].setFocus();app.processEvents();QTest.qWait(40)
QTest.keyClick(dialog.letter_boxes[0], Qt.Key.Key_F);app.processEvents();QTest.qWait(40)
assert dialog.letter_boxes[0].text().upper()=='F',    'plain f must type on the flipped-back front: %r' % [b.text() for b in dialog.letter_boxes]
assert dialog.showing_front, 'typing a letter must not flip the card back to the answer'
dialog.letter_boxes[0].setText('t');dialog.letter_boxes[0].textChanged.emit('t');app.processEvents()

# 4. Shift+F again returns to the answer, same width, same top edge, cursor back on the row.
QTest.keyClick(dialog, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier);app.processEvents();QTest.qWait(80)
assert not dialog.showing_front
assert dialog.grade_widget.isVisible() and dialog.result_label.isVisible()
assert dialog.width()==width_before, (dialog.width(), width_before)
assert abs(dialog.y()-top_before)<=2, (dialog.y(), top_before)
assert not graded

# 5. The menu carries the same action, so it is findable without the keyboard.
menu=dialog.findChild(QMenu)
assert any('题目' in action.text() for action in menu.actions()), [a.text() for a in menu.actions()]
menu_action=[action for action in menu.actions() if '题目' in action.text()][0]
menu_action.trigger();app.processEvents();QTest.qWait(60)
assert dialog.showing_front, 'the menu entry must do what the key does'
menu_action.trigger();app.processEvents();QTest.qWait(60)
assert not dialog.showing_front

# 6b. The card the user actually sees is usually the one embedded in the previous card's
#     window (in-place swap). Pressing F there must not resize the widget past its frame —
#     that is what turned the front face into overlapping pixels on the real machine.
def card(cid, word): return dict(question, kind='due', card_id=cid, word=word, answer_form=word)
host=ReviewDialog(card(50,'anchor'),'center',lambda *_a: graded.append(_a),cfg)
host.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
inner=ReviewDialog(card(51,'preference'),'center',lambda *_a: graded.append(_a),cfg)
inner._embedded=True
inner.setParent(host, Qt.WindowType.Widget)
inner.setGeometry(host.rect())
host._embedded_dialog=inner
# Mirror what the controller actually does at handover: the outgoing card's widgets are
# hidden. Left visible, the host's own layout would set a floor on its height and the
# shrink being tested here could never happen — that is a test artefact, not behaviour.
for widget in host.findChildren(QWidget):
    if widget is not inner and not inner.isAncestorOf(widget):
        widget.hide()
inner.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
inner.reveal(True);QTest.qWait(60);app.processEvents()
window_before=host.geometry()
QTest.keyClick(inner, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier);QTest.qWait(60);app.processEvents();QTest.qWait(60)
assert inner.showing_front, 'Shift+F must work on the embedded card too'
# Height follows whichever face is up (learner's decision, 2026-11-05); width and the
# card-fills-the-window invariant are the parts that must not move — the second is what
# made the front face a pile of overlapping pixels on the real machine.
assert host.width() == window_before.width(), (host.width(), window_before.width())
assert inner.geometry() == host.rect(), (inner.geometry(), host.rect())
assert abs(host.height() - inner.layout().sizeHint().height()) <= 24, (
    host.height(), inner.layout().sizeHint().height(), 'the front face is not fully inside')
assert not inner.grade_widget.isVisible() and not inner.result_label.isVisible()
assert inner.question_label.isVisible()
QTest.keyClick(inner, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier);QTest.qWait(60);app.processEvents();QTest.qWait(60)
assert not inner.showing_front and inner.grade_widget.isVisible()
assert host.width() == window_before.width(), (host.width(), window_before.width())
assert inner.geometry() == host.rect(), (inner.geometry(), host.rect())
assert abs(host.height() - inner.layout().sizeHint().height()) <= 24, (
    host.height(), inner.layout().sizeHint().height())
host.close();app.processEvents()

# 7. Esc on the front still ends the card without rating it, and does not rate silently.
QTest.keyClick(dialog, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier);app.processEvents();QTest.qWait(60)
dialog.reject();app.processEvents();QTest.qWait(60)
assert not graded, 'leaving the front must not answer the card'
print('Qt: Shift+F looks at the question again without un-revealing, grading, resizing or reopening, and plain f types')
