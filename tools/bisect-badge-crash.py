"""Bisect the 0xC0000409 fail-fast that kills the badge checks.

One stage per process: a fastfail bypasses every Python handler, so the only way to
see where it dies is to leave a flushed marker on disk before each step and read the
last one afterwards. Stages are cumulative (stage 4 also does 1-3).

    python tools/bisect-badge-crash.py 1   ... 7
"""
import os, sys, types

STAGE = int(sys.argv[1]) if len(sys.argv) > 1 else 1
LOG = r'C:\tmp\bisect-stage-%d.log' % STAGE
_fh = open(LOG, 'w', encoding='utf-8')


def step(msg):
    _fh.write('%s\n' % msg)
    _fh.flush()
    os.fsync(_fh.fileno())


base = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, base)
os.environ['PATH'] = ';'.join([os.path.join(base, 'PyQt6', 'Qt6', 'bin'),
                               os.path.dirname(base),
                               os.path.join(os.environ['SystemRoot'], 'System32'),
                               os.environ['SystemRoot']])
os.add_dll_directory(os.path.join(base, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(base))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_PLUGIN_PATH'] = os.path.join(base, 'PyQt6', 'Qt6', 'plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))
from PyQt6.QtCore import QObject, QPoint, QRect, QEvent, Qt, pyqtSignal, QRectF, QVariantAnimation, QUrl, QTimer, QEasingCurve
from PyQt6.QtGui import QCursor, QFontDatabase, QFontMetrics, QColor, QPainter, QDesktopServices
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStyle, QVBoxLayout, QWidget
aqt = types.ModuleType('aqt'); aqt.mw = types.SimpleNamespace()
qt = types.ModuleType('aqt.qt')
for n in ('QObject', 'QTimer', 'Qt', 'pyqtSignal', 'QEasingCurve', 'QEvent', 'QRect', 'QRectF',
          'QVariantAnimation', 'QUrl', 'QColor', 'QPainter', 'QDesktopServices', 'QMenu',
          'QMessageBox', 'QCursor', 'QFontMetrics', 'QApplication', 'QComboBox', 'QDialog',
          'QHBoxLayout', 'QLabel', 'QLineEdit', 'QPushButton', 'QScrollArea', 'QStyle',
          'QSizePolicy', 'QVBoxLayout', 'QWidget', 'QPoint'):
    setattr(qt, n, globals()[n])
sys.modules['aqt'] = aqt; sys.modules['aqt.qt'] = qt
sys.modules['aqt'] = aqt; sys.modules['aqt.qt'] = qt
package = types.ModuleType('zotero_global_capture')
package.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                                'anki-global-addon', 'zotero_global_capture'))]
sys.modules['zotero_global_capture'] = package
step('imports ok')

from zotero_global_capture.review_popup import ReviewDialog
from zotero_global_capture import card_motion, candy_badge, motion_view
step('modules ok: motion_view reach margin=%s' % getattr(motion_view, 'BADGE_REACH_MARGIN', None))

app = QApplication([])
for f in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    QFontDatabase.addApplicationFont(f)
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object(); aqt.mw.state = 'deckBrowser'
aqt.mw.isActiveWindow = lambda: False; aqt.mw.isMinimized = lambda: False
step('QApplication ok')

CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_theme': 'dark',
       'review_position': 'center', 'review_plan_mode': 'fixed', 'review_batch_size': 10,
       'model': '四六级单词模板', 'deck': 'Literature', 'review_motion_hop': True}
QUESTION = {'kind': 'due', 'card_id': 1, 'mode': 'typing', 'word': 'practicable',
            'meaning': 'adj. 能实行的；适用的；可行的',
            'example': 'It was a characteristic smile.', 'literature': '这是一条例句。',
            'options': [], 'phonetic': 'præktɪkəb(ə)l'}


def make(celebrate):
    return ReviewDialog(dict(QUESTION), 'center', lambda *_a: None,
                        dict(CFG, review_motion_celebration=celebrate))


dialog = make(True)
dialog.show(); dialog.resize(526, 630); app.processEvents()
step('stage1 dialog shown')

if STAGE >= 2:
    for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
        box.setText(expected)
    dialog.reveal(True); app.processEvents()
    step('stage2 revealed')

if STAGE >= 3:
    rows = dialog.celebration_rows()
    step('stage3 celebration_rows -> %r' % (rows,))

if STAGE >= 4:
    word_row, protected = dialog.celebration_rows()
    dialog.celebration.play(1, dialog.cfg, word_row=word_row, protected=protected)
    app.processEvents()
    step('stage4 play() returned')

if STAGE >= 5:
    dialog.celebration.progress = 0.42
    dialog.celebration.update(); app.processEvents()
    step('stage5 progress set + repaint queued')

if STAGE >= 6:
    image = dialog.grab().toImage()
    step('stage6 grabbed %dx%d' % (image.width(), image.height()))

if STAGE >= 7:
    dialog.celebration.set_word_only(True) if hasattr(dialog.celebration, 'set_word_only') else None
    dialog.deleteLater(); app.processEvents()
    step('stage7 deleted')

os._exit(0)
