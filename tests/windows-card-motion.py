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
from zotero_global_capture import motion_view, card_motion
from PyQt6.QtTest import QTest
app=QApplication([])
for _f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(_f)
ReviewDialog.speak_many = lambda self, texts: True

aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

BASE_CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_hint_audio': False,
            'review_theme': 'dark', 'review_position': 'center', 'review_plan_mode': 'fixed',
            'review_batch_size': 10, 'model': '四六级单词模板', 'deck': 'Literature'}


def card(word='reward', mode='typing', cfg=None):
    dialog = ReviewDialog({'kind': 'due', 'card_id': 7, 'mode': mode, 'word': word,
                           'meaning': 'v. 奖励', 'example': '', 'literature': '', 'options':
                           (['奖励', '回报', '要求', '回顾'] if mode == 'choice' else [])},
                          'center', lambda *_a: None, dict(BASE_CFG, **(cfg or {})))
    dialog.show()
    QTest.qWait(60); app.processEvents(); QTest.qWait(60)
    return dialog


def spell(dialog, letters=None):
    for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText((letters or {}).get(box.index, expected))
    dialog.check_input()
    app.processEvents(); QTest.qWait(40)
    return dialog


def run(ms):
    """Let the animation clocks advance for a while, the way an event loop does."""
    steps = max(1, ms // 20)
    for _ in range(steps):
        app.processEvents(); QTest.qWait(20)


# 1. A correct letter hops up and comes back to exactly the slot the layout gave it.
dialog = card()
box = dialog.letter_boxes[0]
home = box.pos()
box.setText('r')
app.processEvents()
peak = None
for _ in range(14):
    app.processEvents(); QTest.qWait(15)
    if box.pos().y() < home.y():
        peak = box.pos().y()
run(300)
assert peak is not None, ('a correct letter must visibly hop', home.y(), box.pos().y())
assert box.pos() == home, ('the hop must end where the layout put the box', box.pos(), home)
assert box.property('zvr_home') == home, 'the home position is captured once and reused'

# 2. A wrong letter swings sideways and also comes home.
dialog = card()
box = dialog.letter_boxes[1]
home = box.pos()
box.setText('q')
app.processEvents()
offsets = set()
for _ in range(14):
    app.processEvents(); QTest.qWait(15)
    offsets.add(box.pos().x() - home.x())
run(300)
assert min(offsets) < 0 < max(offsets), ('a wrong letter must swing both ways', sorted(offsets))
assert box.pos() == home, ('the shake must end in the layout slot', box.pos(), home)

# 3. A flawless spelling puts a celebration over the card — in Chinese, on top, harmless.
dialog = card()
spell(dialog)
overlay = dialog.celebration
assert overlay is not None and overlay.isVisible(), 'a clean spelling must celebrate'
assert overlay.parent() is dialog, 'the overlay belongs to this card and dies with it'
assert overlay.geometry() == dialog.rect(), (overlay.geometry(), dialog.rect())
assert overlay.tier in (1, 2), overlay.tier
badge = card_motion.tier_label(overlay.tier)
assert badge and any('\u4e00' <= char <= '\u9fff' for char in badge), \
    ('the badge word is Chinese, per the approved change to the mockup', badge)
assert not overlay.hasFocus() and overlay.focusPolicy() == Qt.FocusPolicy.NoFocus
assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents), \
    'the celebration must never eat the Enter that pages the card'

# 4. Motion does not block paging: Enter during the celebration still grades. A flawless
#    spelling routes Enter to the mastered path (E is the mastered button), so listen for
#    both — what matters is that the keystroke arrives at all.
dialog = card()
recorded = []
dialog.grade = lambda _dialog, ease: recorded.append(('grade', ease))
dialog.mastered.connect(lambda _dialog=None: recorded.append(('mastered', None)))
spell(dialog)
assert dialog.celebration.active(), 'the celebration should still be running here'
QTest.keyClick(dialog, Qt.Key.Key_Return)
run(60)
assert recorded, 'Enter must reach the rating path while the badge is on screen'

# 5. A wrong answer celebrates nothing, and neither does any other question type.
dialog = card()
dialog.answer_button.click()
app.processEvents(); QTest.qWait(60)
assert dialog.celebration is None, 'showing the answer is not a win'
choice = card(word='reward', mode='choice')
choice.reveal(True)
assert choice.celebration is None, 'only the spelling card celebrates'

# 6. The settings switch really switches.
quiet = card(cfg={'review_motion': 'off'})
spell(quiet)
assert quiet.celebration is None, 'off must not build an overlay at all'
calm = card(cfg={'review_motion': 'calm'})
spell(calm)
assert calm.celebration is not None and calm.celebration.isVisible()
assert not calm.celebration.with_sparks and not calm.celebration.with_confetti, \
    'calm keeps the badge but drops the decoration'
full = card(cfg={'review_motion': 'full'})
spell(full)
assert full.celebration.with_sparks, 'full keeps the sparks for a clean recall'

# 7. Hiding the card stops the celebration — the shape that produced the F-key ghosts.
dialog = card()
spell(dialog)
dialog.celebration.play(1, 'full')
assert dialog.celebration.active()
dialog.hide()
app.processEvents(); QTest.qWait(60)
assert not dialog.celebration.isVisible(), 'a hidden card must not keep an overlay alive'
assert not dialog.celebration.active(), 'and its animation must be stopped, not left running'

# 8. The look-back must never celebrate again.
dialog = card()
dialog.review_note = {'correct': True, 'rating': 'Mastered', 'hint_uses': 0,
                      'incorrect_letters': 0, 'failed_attempts': 0}
dialog.enter_review()
assert dialog.celebration is None, '回看 is a look, not an award'

print('Qt: 字母落格会跳、错字母会抖并回到原位；拼写全对才庆祝，中文徽章不挡回车，'
      '三档开关与隐藏卡片都按预期停止')
