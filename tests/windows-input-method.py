"""Qt check: the spelling card's letter boxes must be the ones the IME cannot reach.

What is proven where, so this file does not overclaim:
  - the lever that actually stops 微软拼音 on this machine was seen in the manual run
    (control box composed Chinese twice; the box with WA_InputMethodEnabled off produced
    literal `ceshi` twice). That is a human observation on a real desktop, recorded in AUDIT
    §9.47 — not something an offscreen harness can reproduce, because offscreen there is no
    IME at all.
  - what THIS check can prove is the code claim: every box the learner types a letter into
    has the flag set, it survives the answer flip and the look-back, and no other widget was
    silently switched.
"""
import os,sys,types
base=r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
dlls=[os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin')),os.add_dll_directory(os.path.dirname(base))]
ctypes_ok=True
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
from PyQt6.QtCore import QObject,QPoint,Qt,pyqtSignal,QEvent,QRectF,QVariantAnimation,QUrl,QTimer
from PyQt6.QtGui import QCursor,QFont,QFontDatabase,QFontMetrics,QColor,QPainter,QDesktopServices
from PyQt6.QtWidgets import QApplication,QComboBox,QDialog,QHBoxLayout,QLabel,QLineEdit,QMenu,QMessageBox,QPushButton,QScrollArea,QSizePolicy,QStyle,QVBoxLayout,QWidget
aqt=types.ModuleType('aqt');aqt.mw=types.SimpleNamespace()
qt=types.ModuleType('aqt.qt')
for n in ('QObject','QTimer','Qt','pyqtSignal','QEvent','QRectF','QVariantAnimation','QUrl','QColor','QPainter','QDesktopServices','QMenu','QMessageBox','QCursor','QFontMetrics','QApplication','QComboBox','QDialog','QHBoxLayout','QLabel','QLineEdit','QPushButton','QScrollArea','QStyle','QVBoxLayout','QWidget'): setattr(qt,n,globals()[n])
sys.modules['aqt']=aqt;sys.modules['aqt.qt']=qt
package=types.ModuleType('zotero_global_capture');package.__path__=[os.path.abspath(os.path.join(os.path.dirname(__file__),'..','anki-global-addon','zotero_global_capture'))];sys.modules['zotero_global_capture']=package
from zotero_global_capture.review_popup import ReviewDialog
from zotero_global_capture import input_mode
from PyQt6.QtTest import QTest
app=QApplication([])
for _f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(_f)
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_hint_audio': False,
       'review_theme': 'dark', 'review_position': 'center', 'review_plan_mode': 'fixed',
       'review_batch_size': 10, 'model': '四六级单词模板', 'deck': 'Literature'}


def card(word='reward', mode='typing'):
    dialog = ReviewDialog({'kind': 'due', 'card_id': 7, 'mode': mode, 'word': word,
                           'meaning': 'v. 奖励', 'example': '', 'literature': '', 'options': []},
                          'center', lambda *_a: None, CFG)
    dialog.show()
    QTest.qWait(60); app.processEvents()
    return dialog


# 1. Every box a letter goes into is Latin-only, and still carries the hint for the engines
#    that do read it.
dialog = card()
assert dialog.letter_boxes, 'a spelling card must have letter boxes to test'
for box in dialog.letter_boxes:
    assert input_mode.is_latin_only(box), ('the box can still be composed into', box.index)
    assert box.inputMethodHints(), 'the hint stays as a second, harmless lever'
assert isinstance(box, QLineEdit), 'the boxes are the real input widgets'

# 2. The flag survives typing into the box, the answer flip, and the F look-back — the
#    attribute belongs to the widget, so no later relayout can quietly hand the IME back.
for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
    box.setText(expected)
app.processEvents(); QTest.qWait(40)
dialog.check_input()
app.processEvents(); QTest.qWait(60)
for box in dialog.letter_boxes:
    assert input_mode.is_latin_only(box), ('the answer face must not re-enable the IME',
                                           box.index)
dialog.show_front_face(True)
app.processEvents(); QTest.qWait(60)
for box in dialog.letter_boxes:
    assert input_mode.is_latin_only(box), 'looking back at the question keeps it Latin-only'

# 3. Nothing else on the card was switched: the flag is applied where letters are typed, not
#    sprayed over the window.
others = [w for w in dialog.findChildren(QLineEdit) if w not in list(dialog.letter_boxes)]
for widget in others:
    assert not input_mode.is_latin_only(widget), \
        ('only the letter boxes should be Latin-only', type(widget).__name__)

# 4. The helper is idempotent, so a rebuilt card cannot leave a box in a half state.
box = dialog.letter_boxes[0]
assert input_mode.make_latin_only(box) is True or input_mode.is_latin_only(box)
assert input_mode.make_latin_only(box) is False, 'already Latin-only must report no change'

# 5. The lever that can actually beat a TSF input method: the thread keyboard layout follows
#    the card. This part uses the REAL user32 inside a Qt process, because that is the only
#    way to show the call works here at all — the learner's report (「我输入，也没有自动给我
#    选成英文输入啊」) proved the attribute alone is not enough on a machine with one layout.
typing_card = card(word='reward')
assert typing_card.keyboard.previous is not None, ('拼写卡一出现就该把本线程切到英文键盘布局',
                                                   typing_card.keyboard.current())
assert typing_card.keyboard.current() != 0x08040804, hex(typing_card.keyboard.current())
typing_card.close(); app.processEvents()
assert typing_card.keyboard.previous is None, '卡片关闭必须把布局还回去'

choice_card = card(word='shrimp', mode='choice')
assert choice_card.keyboard.previous is not None, (
    '选择题也吃 A–D 字母键，卡片在屏期间同样要英文布局')
choice_card.close(); app.processEvents()

# 6. The face transitions, asserted against a fake so the check itself does not depend on
#    what input methods this machine happens to have installed.
class FakeU32:
    def __init__(self):
        self.current = 0x08040804
        self.loaded, self.activated = [], []
    def LoadKeyboardLayoutW(self, klid, flags):
        self.loaded.append(klid)
        return 0x04090409
    def ActivateKeyboardLayout(self, hkl, flags):
        self.activated.append(hkl)
        self.current = hkl
        return hkl
    def GetKeyboardLayout(self, tid):
        return self.current

api = FakeU32()
dialog = card(word='characteristic')
dialog.keyboard = input_mode.ThreadKeyboardLayout(api)
dialog.keyboard.enable()                       # what showEvent does for a spelling card
assert api.loaded == ['00000409'], api.loaded
assert api.current == 0x04090409, hex(api.current)
# The layout now outlives the flip: the answer face takes A–E as letters, so handing the
# keyboard back at reveal is exactly what could have let the input method eat a rating.
dialog.reveal(True); app.processEvents()
assert api.current == 0x04090409, ('答案面仍须保持英文布局', hex(api.current))
dialog.show_front_face(True); app.processEvents()
assert api.current == 0x04090409, hex(api.current)
dialog.show_front_face(False); app.processEvents()
assert api.current == 0x04090409, hex(api.current)
dialog.hide(); app.processEvents()
assert api.current == 0x08040804, ('卡片收起才把键盘还回去', hex(api.current))
dialog.deleteLater()

print('Qt: 拼写框全部关掉输入法属性且保留 hint，其他输入框未被误改；英文键盘布局从卡片出现维持到卡片收起，翻面和回看都不交还键盘')
