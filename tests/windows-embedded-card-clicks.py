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
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QWidget

ReviewDialog.speak_many = lambda self, texts: True
for _f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(_f)
aqt.mw.col = object(); aqt.mw.state = 'deckBrowser'
cfg = {'review_auto_word': False, 'review_auto_example': False, 'review_auto_example_mode': 'off',
       'review_hint_audio': False, 'review_theme': 'dark', 'review_position': 'center'}


def press_on(widget):
    """Send a real left-press through the application-level event filters."""
    point = widget.rect().center()
    event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(point),
                        QPointF(widget.mapToGlobal(point)), Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    return QApplication.sendEvent(widget, event)


def build_session():
    ctl = DesktopReviewController(lambda: cfg, lambda *a: None, lambda *a: None, lambda *a: None)
    ctl.session_target = 3
    ctl._lookup_known_words = lambda *a: None
    ctl._lookup_relations = lambda *a: None
    ctl.schedule = lambda **kw: None
    host = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': 'listening', 'word': 'petrichor',
                         'meaning': '雨后泥土的气味', 'example': '', 'literature': '', 'options': []},
                        'center', ctl._grade, cfg)
    ctl.dialog = host; ctl.review_host = host
    host.finished.connect(ctl._closed)
    host.show(); QTest.qWait(60); app.processEvents()
    host.reveal(True)  # the user answered and saw the answer face
    QTest.qWait(40); app.processEvents()
    ctl._graded(host, None, ctl.generation,
                ({'kind': 'due', 'card_id': 2, 'mode': 'typing', 'word': 'sycophant',
                  'meaning': '马屁精，谄媚者', 'example': '', 'literature': '', 'options': []}, None))
    QTest.qWait(80); app.processEvents()
    return ctl, host, ctl.dialog


ctl, host, card = build_session()
assert card is not host and card.window() is host, "the second card should be embedded in the host"

# The host's own widgets from card one must not stay live under the new card.
stale = [name for name in ('later', 'answer_scroll', 'grade_widget', 'status')
         if getattr(host, name).isVisible()]
assert not stale, "host still shows card-one widgets that can swallow clicks: %s" % stale

# A press that reaches one of those host widgets must not destroy the active card.
for target in (host, host.later, host.answer_scroll, host.grade_widget):
    press_on(target)
    QTest.qWait(20); app.processEvents()
    assert ctl.dialog is card, "clicking %s killed the active card" % target
    assert card.isVisible(), "active card became invisible after a click on the host"
    assert host.isVisible(), "host window closed"

# And every pixel of the window must hit-test into the active card, not into card one.
foreign = []
for y in range(0, host.height(), 12):
    for x in range(0, host.width(), 12):
        hit = host.childAt(x, y)
        if hit is not None and hit is not card and not card.isAncestorOf(hit):
            foreign.append((x, y, type(hit).__name__))
assert not foreign, "host pixels still resolve to card-one widgets: %s" % foreign[:6]

print('Qt: embedded card survives clicks on the host and owns every pixel of the window')
