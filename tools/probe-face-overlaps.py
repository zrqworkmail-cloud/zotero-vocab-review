"""Which widget is on top of which — measured on the *question* face, not the answer face.

The learner's report (2026-11-05): 「拼写题的字母提示按钮太靠上了，被题目挡住看不全」 and
「庆祝徽章位置不对，会挡住单词」. Both are geometry claims, so both get measured before
anything is moved: this prints every visible row of the front face per mode, then lists
(a) sibling rectangles that actually overlap, and (b) rows whose bottom falls outside the
window, and (c) the rectangle that holds the word being celebrated — the band the badge
must stay clear of.

Read-only. Nothing here writes to Anki or to the add-on.
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

from PyQt6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer, QVariantAnimation, \
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

QUESTIONS = {
    'typing': {'kind': 'new', 'card_id': 1, 'mode': 'typing', 'word': 'characteristic',
               'meaning': 'adj. 典型的，特有的；n. 特征，特性',
               'example': 'It was a characteristic smile.', 'literature': '',
               'options': [], 'phonetic': "kærəktə'rɪstɪk"},
    'short typing': {'kind': 'new', 'card_id': 2, 'mode': 'typing', 'word': 'drive',
                     'meaning': 'v. 驾驶，开车；n. 驱动力', 'example': '', 'literature': '',
                     'options': [], 'phonetic': 'draɪv'},
    'choice': {'kind': 'new', 'card_id': 3, 'mode': 'choice', 'word': 'shrimp',
               'meaning': 'n.（小）虾，河虾，褐虾', 'example': '', 'literature': '',
               'options': ['n. 协同因素；系数，率', 'n.（小）虾，河虾，褐虾',
                           'n. 详细检查， 仔细观察', 'n. 唯心主义；理想主义'],
               'phonetic': 'ʃrɪmp'},
    'reverse': {'kind': 'new', 'card_id': 4, 'mode': 'reverse', 'word': 'shrimp',
                'meaning': 'n.（小）虾，河虾，褐虾', 'example': '', 'literature': '',
                'options': ['coefficient', 'shrimp', 'examination', 'idealism'],
                'phonetic': 'ʃrɪmp'},
    'judgment': {'kind': 'new', 'card_id': 5, 'mode': 'judgment', 'word': 'shrimp',
                 'meaning': 'n.（小）虾，河虾，褐虾', 'example': '', 'literature': '',
                 'options': ['正确', '错误'], 'judgment_statement': 'n. 协同因素；系数，率',
                 'judgment_correct': False, 'phonetic': 'ʃrɪmp'},
    'cloze': {'kind': 'new', 'card_id': 6, 'mode': 'cloze', 'word': 'characteristic',
              'meaning': 'adj. 典型的，特有的', 'cloze': 'It was a ___ smile.',
              'answer_form': 'characteristic',
              'example': 'It was a characteristic smile.', 'literature': '',
              'options': [], 'phonetic': "kærəktə'rɪstɪk"},
    'choice long': {'kind': 'new', 'card_id': 8, 'mode': 'choice', 'word': 'examination',
                    'meaning': 'n. 详细检查，仔细观察；考试，测验；审讯，调查',
                    'example': '', 'literature': '',
                    'options': ['n. 详细检查，仔细观察；考试，测验；审讯，调查',
                                'n.（小）虾，河虾，褐虾',
                                'n. 协同因素；系数，率，系数，比例系数，相互作用系数',
                                'n. 唯心主义；理想主义，空想，不切实际的信念'],
                    'phonetic': 'ɪɡ,zæmɪ' + "'neɪʃn"},

    'listening': {'kind': 'new', 'card_id': 7, 'mode': 'listening', 'word': 'advantage',
                  'meaning': 'n. 优势，有利条件', 'example': '', 'literature': '',
                  'options': [], 'phonetic': 'əd' + "'vɑːntɪdʒ"},
}


def rows_for(dialog):
    out = []
    for widget in dialog.findChildren(QWidget):
        if not widget.isVisible() or not widget.geometry().isValid():
            continue
        if isinstance(widget, (QScrollArea,)) or type(widget).__name__ == 'Celebration':
            continue
        top_left = widget.mapTo(dialog, QPoint(0, 0))
        text = str(getattr(widget, 'text', lambda: '')())[:26].replace('\n', ' ')
        out.append({'widget': widget, 'name': type(widget).__name__, 'text': text,
                    'rect': QRect(top_left.x(), top_left.y(), widget.width(), widget.height())})
    return out


def related(left, right):
    """True when one of these two widgets contains the other — nesting is not overlap."""
    for a, b in ((left, right), (right, left)):
        parent = b['widget'].parentWidget()
        while parent is not None:
            if parent is a['widget']:
                return True
            parent = parent.parentWidget()
    return False


def overlaps(rows):
    """Sibling rectangles that really intersect — the smallest one is the victim."""
    found = []
    for i, left in enumerate(rows):
        for right in rows[i + 1:]:
            if related(left, right):
                continue
            shared = left['rect'].intersected(right['rect'])
            if shared.width() <= 1 or shared.height() <= 1:
                continue
            a, b = left['rect'].width() * left['rect'].height(), right['rect'].width() * right['rect'].height()
            victim, other = (left, right) if a <= b else (right, left)
            found.append('%dx%d  [%s] 被 [%s] 盖住' % (shared.width(), shared.height(),
                                                    (victim['text'] or victim['name']),
                                                    (other['text'] or other['name'])))
    return found


def clipped_text(rows):
    """A label whose wrapped text needs more room than it was given is cut, and the
    learner reads that as 选项被截断. Measure the text, do not trust the rectangle."""
    found = []
    for row in rows:
        label = row['widget']
        if type(label).__name__ != 'QLabel' or not label.text() or label.width() <= 0:
            continue
        metrics = label.fontMetrics()
        if label.hasHeightForWidth():
            need = label.heightForWidth(label.width())
        else:
            need = metrics.boundingRect(0, 0, label.width(), 10000,
                                        int((Qt.TextFlag.TextWordWrap if label.wordWrap() else Qt.TextFlag(0))
                                            | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                                        label.text()).height()
        if need > label.height() + 1:
            found.append('[%s] 文字需要 %d px 高，只有 %d px — 少 %d px'
                         % (row['text'], need, label.height(), need - label.height()))
    return found


def badge_vs_word(dialog, rows):
    """Where the celebration lands, against the rows the card shows the word in.

    Both the anchor and the painted footprint come from the shipped rule
    (`motion_view.badge_centre` / `badge_footprint`), so this reports what the card will
    actually do instead of a number copied from an older revision. Worst case is tier 1.
    """
    from zotero_global_capture import motion_view
    max_width = dialog.width() * 0.78
    try:
        protected_rows = dialog.celebration_rows()[1]
    except Exception:
        protected_rows = ()
    y, fit = motion_view.badge_centre(dialog.height(), 1, max_width, protected_rows)
    reach = motion_view.badge_footprint(1, max_width, fit)
    anchor = QPoint(dialog.width() // 2, y)
    protected = QRect(0, int(y - reach / 2.0), dialog.width(), int(reach))
    found = []
    groups = {}
    for row in rows:
        widget = row['widget']
        if type(widget).__name__ == 'LetterBox':
            groups.setdefault('字母格（正在拼的单词）', []).append(row['rect'])
        elif widget.objectName() == 'question':
            groups.setdefault('单词行 [%s]' % row['text'][:18], []).append(row['rect'])
    for name, rects in groups.items():
        union = rects[0]
        for rect in rects[1:]:
            union = union.united(rect)
        shared = union.intersected(protected)
        if shared.width() > 1 and shared.height() > 1:
            found.append('%s y %d-%d 与徽章 y %d-%d 相交 %d px（锚点 y=%d，卡高=%d）'
                         % (name, union.top(), union.bottom() + 1, protected.top(),
                            protected.bottom() + 1, shared.height(), anchor.y(), dialog.height()))
    return found


for label, question in QUESTIONS.items():
    for face in ('题目面', '答案面'):
        dialog = ReviewDialog(dict(question), 'center', lambda *_a: None, dict(CFG))
        dialog.resize(510, 630)
        dialog.show()
        app.processEvents()
        if face == '答案面':
            if question['mode'] in ('typing', 'cloze', 'listening'):
                for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
                    box.setText(expected)
                dialog.check_input()
            else:
                dialog.reveal(True)
            app.processEvents()
        # The live card trims its own height at birth; measuring an untrimmed window would
        # miss exactly the clipping the learner sees.
        dialog.fit_card_height()
        app.processEvents()
        rows = rows_for(dialog)
        print('== %s / %s  card %d x %d ==' % (label, face, dialog.width(), dialog.height()))
        for row in sorted(rows, key=lambda r: (r['rect'].y(), r['rect'].x())):
            rect = row['rect']
            print('   y %3d-%3d  x %3d-%3d  %-12s %s' % (rect.y(), rect.bottom() + 1, rect.x(),
                                                         rect.right() + 1, row['name'], row['text']))
        for line in overlaps(rows):
            print('   OVERLAP  ' + line)
        for line in clipped_text(rows):
            print('   CLIPTEXT  ' + line)
        for line in badge_vs_word(dialog, rows):
            print('   BADGE  ' + line)
        for row in rows:
            if row['rect'].bottom() + 1 > dialog.height():
                print('   OUTOFWINDOW  [%s] 底边 %d 超出窗口 %d' % (row['text'] or row['name'],
                                                                 row['rect'].bottom() + 1, dialog.height()))
        print()
        dialog.deleteLater()
        app.processEvents()
