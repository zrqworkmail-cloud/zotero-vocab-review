"""The hint row of the spelling and listening cards, laid out as the learner reads it.

Built on the same harness as windows-question-audio.py (its preamble is copied here, so the
fixture card, the stubbed speech and the config cannot drift from that check). What is pinned
is the 2026-11-06 redesign: aids as quiet text under the letter boxes, 检查拼写 as the only
filled control on its own line, the two ways out of a card together in the foot, and the
transcription one tap away for anyone who cannot hear the audio -- priced as a hint.
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


# ---------------------------------------------------------------------------
# The listening/spelling hint row, redesigned (user 2026-11-06: 提示排的排版需要重新
# 设计, plus 听写题要能在听不见声音时看音标). Pinned here is the shape the learner
# sees: aids under the boxes, one filled action on its own line, the two ways out in
# the foot -- and the 音标 control priced as a hint.
def siblings(widget):
    """The controls that share a layout with this one, in order.

    Qt does not tell a widget which layout holds it, so the card's layout tree is walked
    until the item is found -- which is exactly the structure this check is about.
    """
    def walk(layout):
        if layout is None:
            return None
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is widget:
                return layout
            found = walk(item.layout())
            if found is not None:
                return found
        return None

    layout = walk(widget.parentWidget().layout() if widget.parentWidget() else None)
    if layout is None:
        return []
    return [layout.itemAt(index).widget() for index in range(layout.count())
            if layout.itemAt(index).widget() is not None]


dialog = card('listening')
assert dialog.phonetic_hint_button is not None, '这题的词有音标，听写题就该给音标按钮'
texts = [button.text() for button in siblings(dialog.hint_button)]
assert texts == ['释义', '音标', '字母 0/9'], ('提示行就这三个，顺序也要钉住', texts)
for button in siblings(dialog.hint_button):
    assert button.objectName() == 'aid', ('提示是描边小按钮，不是隐形文字', button.text(),
                                          button.objectName())
assert dialog.check_button.objectName() == 'primary'
assert siblings(dialog.check_button) == [dialog.check_button], '主动作独占一行'
foot = [widget for widget in siblings(dialog.later)]
assert dialog.answer_button in foot, \
    ('显示答案和稍后再说这两条退路要在同一排', [widget.text() for widget in foot])
assert dialog.answer_button not in siblings(dialog.check_button), '显示答案不许再挨着检查拼写'
assert not any('点击下方' in (label.text() or '') for label in dialog.findChildren(QLabel)), \
    '那句指向按钮的说明文字应该删掉'
assert dialog.status.text() == '回车重听 · 空格给字母 · Shift+空格给音标', dialog.status.text()

# The transcription is hidden until asked for, and asking costs a hint.
assert not dialog.front_phonetic.isVisible(), '音标默认不可见'
dialog.phonetic_hint_button.click()
app.processEvents()
assert dialog.front_phonetic.isVisible(), '点完音标必须显示出来'
assert dialog.front_phonetic.text() == dialog.question['phonetic'], \
    ('显示的就是这条笔记的音标字段', dialog.front_phonetic.text(), dialog.question['phonetic'])
assert (dialog.hint_uses, dialog.other_hint_uses) == (1, 1), \
    ('看过音标就是用过一次提示', dialog.hint_uses, dialog.other_hint_uses)
assert not dialog.phonetic_hint_button.isEnabled(), '一次卡片只给一次音标提示'
assert '音标' in dialog.status.text(), dialog.status.text()
dialog.phonetic_hint_button.click()
assert dialog.hint_uses == 1, ('按钮已禁用，重复点不许再计一次', dialog.hint_uses)
dialog.reveal(True)
app.processEvents(); QTest.qWait(40)
assert '建议 Hard' in dialog.status.text(), \
    ('用过音标的听写题，建议必须掉到 Hard', dialog.status.text())
assert not dialog.check_button.isVisible() and not dialog.answer_button.isVisible(), \
    '翻到答案面，题目面的控件都要收走'
dialog.deleteLater(); QTest.qWait(40)

# The control: the same card answered without touching 音标 must not read as Hard, or the
# claim above is just the card always saying Hard.
plain = card('listening')
plain.reveal(True)
app.processEvents(); QTest.qWait(40)
assert '建议 Hard' not in plain.status.text(), \
    ('没看音标的听写题不该被压到 Hard', plain.status.text())
plain.deleteLater(); QTest.qWait(40)

# 音标有键盘入口：Shift+空格驱动的是同一个按钮，所以计数、禁用、状态行只有一份实现。
dialog = card('listening')
key_box = dialog.letter_boxes[0]
key_box.setFocus()
app.processEvents()
assert not dialog.front_phonetic.isVisible(), '键盘这条路也该从"还没显示"开始'
QTest.keyClick(key_box, Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)
app.processEvents()
assert dialog.front_phonetic.isVisible(), 'Shift+空格必须把音标叫出来'
assert (dialog.hint_uses, dialog.other_hint_uses) == (1, 1), \
    ('键盘和鼠标同账', dialog.hint_uses, dialog.other_hint_uses)
assert not dialog.phonetic_hint_button.isEnabled(), '看过一次就该禁用'
QTest.keyClick(key_box, Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)
app.processEvents()
assert dialog.hint_uses == 1, ('再按一次不许再计一次', dialog.hint_uses)
assert '已经看过' in dialog.status.text(), dialog.status.text()
dialog.deleteLater(); QTest.qWait(40)

# A card whose note has no 音标 gets no dead button.
dialog = ReviewDialog({'kind': 'due', 'card_id': 2, 'mode': 'listening', 'word': 'hazardous',
                       'meaning': MEANING, 'example': '', 'literature': '',
                       'options': OPTIONS, 'phonetic': ''}, 'center', lambda *_a: None, dict(CFG))
dialog.show(); QTest.qWait(60); app.processEvents()
assert dialog.phonetic_hint_button is None, '没有音标的词不该出现音标按钮'
assert [button.text() for button in siblings(dialog.hint_button)] == ['释义', '字母 0/9'], \
    '少一个提示，行里就少一个'
dialog.deleteLater(); QTest.qWait(40)

# 拼写题共用这一排：例句代替释义，没有音标，计数跟着 add_hint 走。
dialog = card('typing')
assert [button.text() for button in siblings(dialog.hint_button)] == ['例句', '字母 0/9'], \
    '拼写题的提示行'
assert dialog.phonetic_hint_button is None, '音标只给听写题'
assert dialog.status.text() == '空格给字母提示 · 回车检查拼写', dialog.status.text()
dialog.add_hint()
app.processEvents()
assert dialog.hint_button.text() == '字母 1/9', dialog.hint_button.text()
# Shift+空格在没有音标字段的卡上必须安静：不计数、不改变状态行。
before = (dialog.hint_uses, dialog.status.text())
QTest.keyClick(dialog.letter_boxes[0], Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)
app.processEvents()
assert (dialog.hint_uses, dialog.status.text()) == before, \
    ('没有音标的卡，Shift+空格不该有任何后果', before, dialog.hint_uses, dialog.status.text())
dialog.deleteLater(); QTest.qWait(40)

# 回看题目：提示回来，显示答案不回来（这题已经答过了）。
dialog = card('listening')
dialog.reveal(True)
app.processEvents(); QTest.qWait(40)
QTest.keyClick(dialog, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier)
app.processEvents(); QTest.qWait(40)
assert dialog.showing_front and dialog.hint_button.isVisible(), '回看要能看到提示'
assert not dialog.answer_button.isVisible(), '回看时显示答案没有意义'
dialog.deleteLater(); QTest.qWait(40)

print('Qt: 提示是描边小按钮、主动作独占一行、两条退路进页脚；音标可点可 Shift+空格，一次一点且计入提示')
