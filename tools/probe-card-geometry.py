"""Where is the dead space on the answer face? Dump real widget geometry at the real size.

The celebration overlay has to land somewhere that does not sit on top of the content the
learner still needs to read, so before drawing anything we measure the card.
"""
import os
import sys
import types

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32')])
os.add_dll_directory(os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(BASE))
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))
os.environ['QT_PLUGIN_PATH'] = os.path.join(BASE, 'PyQt6', 'Qt6', 'plugins')

from PyQt6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QVariantAnimation, \
    QUrl, pyqtSignal, QEvent
from PyQt6.QtGui import (QColor, QCursor, QDesktopServices, QFont, QFontDatabase, QFontInfo,
                         QFontMetrics, QFontMetricsF, QImage, QLinearGradient, QPainter,
                         QPainterPath, QPen, QRadialGradient, QPixmap)
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStyle,
                             QVBoxLayout, QWidget)

aqt = types.ModuleType('aqt')
aqt.mw = types.SimpleNamespace()
qt = types.ModuleType('aqt.qt')
for name in ('QObject', 'QTimer', 'Qt', 'pyqtSignal', 'QEvent', 'QRectF', 'QVariantAnimation',
             'QUrl', 'QColor', 'QPainter', 'QDesktopServices', 'QMenu', 'QMessageBox', 'QCursor',
             'QFontMetrics', 'QApplication', 'QComboBox', 'QDialog', 'QHBoxLayout', 'QLabel',
             'QLineEdit', 'QPushButton', 'QScrollArea', 'QStyle', 'QVBoxLayout', 'QWidget'):
    setattr(qt, name, globals()[name])
sys.modules['aqt'] = aqt
sys.modules['aqt.qt'] = qt
package = types.ModuleType('zotero_global_capture')
package.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                                 'anki-global-addon', 'zotero_global_capture'))]
sys.modules['zotero_global_capture'] = package

from zotero_global_capture.review_popup import ReviewDialog

app = QApplication([])
ReviewDialog.speak_many = lambda self, texts: True
aqt.mw.col = object()
aqt.mw.state = 'deckBrowser'

CFG = {'review_auto_word': False, 'review_auto_example_mode': 'off', 'review_hint_audio': False,
       'review_theme': 'dark', 'review_position': 'center', 'review_plan_mode': 'fixed',
       'review_batch_size': 10, 'model': '四六级单词模板', 'deck': 'Literature'}

dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': 'typing', 'word': 'characteristic',
                       'meaning': 'adj. 典型的，特有的；n. 特征',
                       'example': 'It was a characteristic smile.', 'literature': '',
                       'options': [], '音标': "kærəktə'rɪstɪk"},
                      'center', lambda *_a: None, CFG)
dialog.resize(510, 630)
dialog.show()
for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
    box.setText(expected)
dialog.check_input()
app.processEvents()

print('card', dialog.width(), 'x', dialog.height())
rows = []
for widget in dialog.findChildren(QWidget):
    if not widget.isVisible() or not widget.geometry().isValid():
        continue
    top_left = widget.mapTo(dialog, QPoint(0, 0))
    text = getattr(widget, 'text', lambda: '')()
    rows.append((top_left.y(), top_left.x(), widget.width(), widget.height(),
                 type(widget).__name__, str(text)[:34]))
for row in sorted(rows):
    y, x, w, h, kind, text = row
    print('y %3d-%3d  x %3d-%3d  %-12s %s' % (y, y + h, x, x + w, kind, text))

HEIGHT = dialog.height()
WIDTH = dialog.width()
occupied = {}
for y, x, w, h, kind, text in rows:
    if kind in ('Celebration', 'QScrollArea'):
        continue
    if not text and kind == 'QWidget':
        continue
    for line in range(max(0, y), min(HEIGHT, y + h)):
        occupied.setdefault(line, []).append((max(0, x), min(WIDTH, x + w)))

print()
print('free horizontal bands (gap >= 60px), every 10px:')
for line in range(0, HEIGHT, 10):
    spans = sorted(occupied.get(line, []))
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1] + 6:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    gaps = []
    cursor = 0
    for start, end in merged:
        if start - cursor >= 60:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if WIDTH - cursor >= 60:
        gaps.append((cursor, WIDTH))
    print('y %3d: %s' % (line, gaps if gaps else '-'))
