import os,sys,types
base=r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0,base)
os.environ['PATH']=';'.join([os.path.join(base,'PyQt6','Qt6','bin'),os.path.dirname(base),os.path.join(os.environ['SystemRoot'],'System32'),os.environ['SystemRoot']])
dll_dirs=[os.add_dll_directory(os.path.join(base,'PyQt6','Qt6','bin')),os.add_dll_directory(os.path.dirname(base))]
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_PLUGIN_PATH']=os.path.join(base,'PyQt6','Qt6','plugins')
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'))
from PyQt6.QtCore import QObject,QTimer,Qt,pyqtSignal,QEasingCurve,QEvent,QRectF,QRect,QVariantAnimation,QUrl,QPoint
from PyQt6.QtGui import QCursor,QFont,QFontDatabase,QFontMetrics,QColor,QPainter,QDesktopServices
from PyQt6.QtWidgets import QApplication,QComboBox,QDialog,QHBoxLayout,QLabel,QLineEdit,QMenu,QMessageBox,QPushButton,QScrollArea,QStyle,QVBoxLayout,QWidget
aqt=types.ModuleType('aqt');aqt.mw=types.SimpleNamespace()
qt=types.ModuleType('aqt.qt')
for n in ('QObject','QTimer','Qt','pyqtSignal','QEasingCurve','QEvent','QRectF','QRect','QVariantAnimation','QUrl','QColor','QPainter','QDesktopServices','QMenu','QMessageBox','QCursor','QFontMetrics','QApplication','QComboBox','QDialog','QHBoxLayout','QLabel','QLineEdit','QPushButton','QScrollArea','QStyle','QVBoxLayout','QWidget'): setattr(qt,n,globals()[n])
sys.modules['aqt']=aqt;sys.modules['aqt.qt']=qt
package=types.ModuleType('zotero_global_capture');package.__path__=[os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'anki-global-addon', 'zotero_global_capture'))];sys.modules['zotero_global_capture']=package
from zotero_global_capture.review_popup import ReviewDialog, DesktopReviewController


from PyQt6.QtTest import QTest
app=QApplication([])


from zotero_global_capture import review_popup as rp
aqt.mw.col = object(); aqt.mw.state = 'deckBrowser'


class Label:
    def __init__(self): self.text = ''
    def setText(self, value): self.text = value


def make_dialog(card_id):
    box = {'accept': 0, 'grade': [], 'finished': 0}
    # The group break is a panel inside the card's own window now, so the stand-in needs a
    # real window to parent it to; a bare SimpleNamespace made QWidget parenting abort.
    host = QWidget()
    host.resize(510, 570)
    dlg = types.SimpleNamespace(
        question={'card_id': card_id, 'word': 'testword', 'kind': 'new'},
        completed=False, skipped=False, status=Label(),
        accept=lambda: box.__setitem__('accept', box['accept'] + 1),
        grade_result=lambda error: box['grade'].append(error),
        input_mode=types.SimpleNamespace(restore=lambda: None),
        window=lambda: host,
        geometry=lambda: QRect(0, 0, 510, 570))
    finished = types.SimpleNamespace(disconnect=lambda *_a: box.__setitem__('finished', box['finished'] + 1),
                                     connect=lambda *_a: None)
    dlg.finished = finished
    dlg._host = host
    return dlg, box


def run_case(plan_mode, new_remaining, due, next_question):
    """Drive one real _grade() and report what card selection and messaging did."""
    cfg = {'review_plan_mode': plan_mode, 'review_batch_size': 3,
           'review_deadline': '2026-12-12', 'review_daily_goal': 0}
    asked = []
    notices = []
    prepared = []
    ctl = DesktopReviewController(lambda: cfg, lambda *a: None,
                                  lambda message, *a: notices.append(str(message)),
                                  lambda *a: None)
    ctl.session_target = 3
    dlg, box = make_dialog(11)
    ctl.dialog = dlg
    plan = {'goal': 1, 'done': 1, 'batch': 1, 'days': 44, 'introduced': 1,
            'new': 1, 'new_done': 1, 'new_goal': 1, 'new_remaining': new_remaining,
            'due': due, 'review_done': 0, 'review_remaining': due, 'review_goal': due,
            'remaining_new_total': 0, 'capacity_shortfall': 0}
    real_plan, real_prep, real_submit = rp.collection_plan, rp.prepare_question, rp.submit_review
    rp.collection_plan = lambda api, config, *a, **k: dict(plan)
    rp.submit_review = lambda *a, **k: None

    def prep(api, config, mode='mixed', rng=None, due_only=False):
        asked.append(due_only)
        return next_question
    rp.prepare_question = prep
    ctl._prepared = lambda question, error, generation, manual, previous=None: (
        prepared.append((question, error, previous is not None)) or True)
    try:
        ctl._grade(dlg, 3)
        for _ in range(200):
            app.processEvents(); QTest.qWait(5)
            if ctl.break_dialog is not None:
                # A group boundary now waits for the user. This check is about the
                # due-only gate, so agree to continue and let the handover run.
                ctl.break_dialog.accept()
                continue
            if prepared or box['grade'] or notices:
                break
    finally:
        rp.collection_plan, rp.prepare_question, rp.submit_review = real_plan, real_prep, real_submit
    return {'asked_due_only': asked, 'notices': notices, 'prepared': prepared, 'box': box}


# A. fixed mode: the deadline-derived plan must not stop new cards from being offered.
result = run_case('fixed', 0, 0, {'card_id': 12, 'kind': 'new', 'mode': 'typing',
                                 'word': 'next', 'meaning': '下一个', 'options': [],
                                 'example': '', 'literature': ''})
assert result['asked_due_only'] == [False], \
    "fixed mode must not gate new cards on the daily plan: %s" % result['asked_due_only']
assert result['prepared'] and result['prepared'][0][0], \
    "fixed mode should still hand over the next card: %s" % result

# B. daily mode keeps the existing behaviour: once the new-word plan is spent, due only.
result = run_case('daily', 0, 0, {'card_id': 12, 'kind': 'due', 'mode': 'typing',
                                 'word': 'next', 'meaning': '下一个', 'options': [],
                                 'example': '', 'literature': ''})
assert result['asked_due_only'] == [True], \
    "daily mode must still fall back to due-only once the plan is spent: %s" % result['asked_due_only']

# C. when there really is no next card, the user must be told why instead of the window vanishing.
result = run_case('fixed', 0, 0, None)
assert not result['prepared'], "no card should be handed over: %s" % result['prepared']
assert result['notices'], "ending the session silently is the reported bug"
assert any('没有' in text or '完成' in text for text in result['notices']), result['notices']


def run_manual_case(new_remaining, available, next_question):
    """Drive the real toolbar entry point and report the selection flag it used."""
    cfg = {'review_plan_mode': 'daily', 'review_batch_size': 3,
           'review_deadline': '2026-12-12', 'review_daily_goal': 0,
           'study_book': 'cet6_core', 'model': '四六级单词模板'}
    asked, captured = [], []
    ctl = DesktopReviewController(lambda: cfg, lambda *a: None, lambda *a: None, lambda *a: None)
    ctl.signals.prepared.disconnect()
    ctl.signals.prepared.connect(
        lambda question, error, generation, manual: captured.append((question, error)))
    plan = {'goal': 1, 'done': 1, 'batch': 0, 'days': 44, 'introduced': 1,
            'new': 1, 'new_done': 1, 'new_goal': 1, 'new_remaining': new_remaining,
            'due': 0, 'review_done': 0, 'review_remaining': 0, 'review_goal': 0,
            'remaining_new_total': 434, 'capacity_shortfall': 0}
    real = (rp.collection_plan, rp.prepare_question, rp.book_progress, rp.book_availability)
    rp.collection_plan = lambda *a, **k: dict(plan)
    rp.book_progress = lambda *a, **k: (47, 481)
    rp.book_availability = lambda *a, **k: available

    def prep(api, config, mode='mixed', rng=None, due_only=False):
        asked.append(due_only)
        return next_question
    rp.prepare_question = prep
    try:
        ctl.show_next(True)
        for _ in range(200):
            app.processEvents(); QTest.qWait(5)
            if captured:
                break
    finally:
        rp.collection_plan, rp.prepare_question, rp.book_progress, rp.book_availability = real
    return {'asked_due_only': asked, 'captured': captured}


CARD = {'card_id': 12, 'kind': 'new', 'mode': 'typing', 'word': 'next', 'meaning': '下一个',
        'options': [], 'example': '', 'literature': ''}

# D. A manual click is an explicit request. The deadline plan being spent must not
# forbid new cards while Anki's own deck quota still has room — that was the toast.
result = run_manual_case(0, (40, 0), dict(CARD))
assert result['asked_due_only'] == [False], \
    "manual start must not be gated by the plan's new-word target: %s" % result['asked_due_only']
assert result['captured'] and result['captured'][0][0] is not None, result

# E. When both queues are empty, name the quota that is gone instead of the old catch-all.
result = run_manual_case(0, (0, 0), None)
assert result['captured'] and not result['captured'][0][0], result
assert '新词额度' in str(result['captured'][0][1]), result

print('Qt: manual start bypasses a spent plan, and an empty book names the spent quota')
