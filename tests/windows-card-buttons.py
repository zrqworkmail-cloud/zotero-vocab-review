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
from zotero_global_capture import review_popup as rp


from PyQt6.QtTest import QTest
app=QApplication([])
# The real card paints with the stylesheet's own family chain — 'Segoe UI', then
# 'Microsoft YaHei' for the CJK in the meanings — and YaHei's Latin glyphs are wider than
# the offscreen default. Measuring with the fallback font is how a rating row that passed
# every check still arrived cut on the user's screen.
from PyQt6.QtGui import QFontDatabase
for path in (r'C:\Windows\Fonts\segoeui.ttf', r'C:\Windows\Fonts\msyh.ttc'):
    if os.path.exists(path):
        QFontDatabase.addApplicationFont(path)
app.setFont(QFont('Microsoft YaHei', 10))
aqt.mw.col=object();aqt.mw.state='deckBrowser';aqt.mw.isActiveWindow=lambda:False;aqt.mw.isMinimized=lambda:False

cfg={'review_auto_word':False,'review_auto_example_mode':'off','review_hint_audio':False,
     'review_theme':'dark','review_position':'center','review_plan_mode':'fixed','review_batch_size':2}
def card(cid, word): return {'kind':'due','card_id':cid,'mode':'typing','word':word,'meaning':'释义',
                             'example':'','literature':'','options':[],'phonetic':'/straɪv/','snapshot':{}}

# 1. The rating row speaks Anki's own words with the key in front of them — four of
#    them since E/已掌握 was retired on 2026-11-07.
dialog=ReviewDialog(card(1,'strive'),'center',lambda *_a:None,cfg)
dialog.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
width_before=dialog.width()
for box,char in zip(dialog.letter_boxes,'strive'): box.setText(char)
dialog.check_input();app.processEvents();QTest.qWait(60)
assert dialog.width()==width_before, \
    'the rating row must not widen the card when it appears: %d -> %d' % (width_before, dialog.width())
texts=[dialog.grade_widget.layout().itemAt(i).widget().text() for i in range(dialog.grade_widget.layout().count())]
assert texts==['A. Again','B. Hard','C. Good','D. Easy'],texts
# 2026-11-05: the row is one short line now — it names the suggestion and the key, the
# counts moved to its tooltip. A flawless spelling recommends Easy since E was retired.
assert '建议 Easy' in dialog.status.text(),dialog.status.text()
assert '无提示' in dialog.status.toolTip(),dialog.status.toolTip()
assert '按 A' in dialog.grade_buttons[0].toolTip(),dialog.grade_buttons[0].toolTip()

# A wrong answer collapses the row, and the letters have to name what is actually there.
wrong=ReviewDialog(card(2,'thrive'),'center',lambda *_a:None,cfg)
wrong.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
wrong.answer_button.click();app.processEvents();QTest.qWait(60)
assert [button.text() for button in wrong.grade_buttons if not button.isHidden()]==['A. Again 并继续','B. 继续学习'],\
    [button.text() for button in wrong.grade_buttons if not button.isHidden()]

# 2. The pin is a drawn pushpin, not the word 置顶, and it stays readable for a
#    screen reader.
assert dialog.pin_button.text()=='' and not dialog.pin_button.icon().isNull()
assert any(size.width()>=16 for size in dialog.pin_button.icon().availableSizes())
assert '置顶' in dialog.pin_button.toolTip() and '置顶' in dialog.pin_button.accessibleName()
unpinned=rp.pin_icon(False, '#aab9ff').pixmap(18,18).toImage()
pinned=rp.pin_icon(True, '#aab9ff').pixmap(18,18).toImage()
assert unpinned.pixel(0,0)&0xFF000000==0 and pinned.pixel(0,0)&0xFF000000==0,'the pin must be drawn on a transparent field'
assert pinned.pixel(9,9)&0xFF000000!=0 and unpinned.pixel(9,9)&0xFF000000!=0,'the pin body must be drawn'
def ink(image): return sum(1 for y in range(image.height()) for x in range(image.width()) if image.pixel(x,y)&0xFF000000)
def only_in(left,right): return sum(1 for y in range(left.height()) for x in range(left.width())
                                    if left.pixel(x,y)&0xFF000000 and not right.pixel(x,y)&0xFF000000)
assert only_in(pinned,unpinned) >= 12, \
    'the pinned head must be filled where the unpinned one is hollow: %d px' % only_in(pinned,unpinned)
assert ink(pinned) >= 60 and ink(unpinned) >= 40,'both states must draw a pin'

# 2b. The card is a real window, not a tool window: a tool window has no taskbar button
#     and Windows hides it the moment the app loses focus, which is what made an unpinned
#     card "disappear" when the user clicked elsewhere. Qt overlaps these type bits, so
#     the test has to compare the masked type rather than AND the Tool flag.
TYPE_MASK=0xff
window_type=int(dialog.windowFlags()) & TYPE_MASK
assert window_type != int(Qt.WindowType.Tool),'a Qt tool window cannot be found on the taskbar'
assert window_type == int(Qt.WindowType.Window),'the card needs its own window, beside Anki 账户 1: %s' % hex(window_type)

# 3. Every speaker button is a circle: the disc is drawn into the icon, because a
#    stylesheet radius on a 32px box was not rounding on this Qt build.
for button in [b for b in dialog.findChildren(QPushButton) if b.objectName()=='speaker']:
    image=button.icon().pixmap(32,32).toImage()
    assert image.pixel(16,16)&0xFF000000!=0,'the disc must cover the centre'
    assert image.pixel(1,1)&0xFF000000==0,'the corner must be transparent, or it is a square'
    assert image.pixel(16,0)&0xFF000000!=0 and image.pixel(0,16)&0xFF000000!=0,'the edge midpoints must be inside the disc'
    # ... and it must be *shown* at that size: a push button defaults to a 16px icon, which
    # is what made the disc arrive at half the size it was drawn.
    assert button.iconSize().width()==button.width(),\
        'the disc must fill its button: icon %d in a %d box' % (button.iconSize().width(), button.width())

# 3b. The card is wide enough for all four ratings to show their whole label, and the
#     answer boxes keep their text in the middle instead of clinging to the top edge.
row=dialog.grade_widget.layout()
labels=[row.itemAt(i).widget().text() for i in range(row.count())]
for i in range(row.count()): row.itemAt(i).widget().ensurePolished()
# Measured with each button's own font — the one the stylesheet paints with — because the
# dialog's font at "13px" is a different face and that is how an estimate came up short.
demand=sum(QFontMetrics(row.itemAt(i).widget().font()).horizontalAdvance(row.itemAt(i).widget().text())+26
           for i in range(row.count()))+row.spacing()*(row.count()-1)
font=dialog.font(); font.setPixelSize(13)
metrics=QFontMetrics(font)
assert dialog.grade_widget.minimumWidth()>=demand,     'the row must demand its own text width: %d vs %d' % (dialog.grade_widget.minimumWidth(), demand)
assert dialog.width()>=demand+52,'the rating row needs %d px, the card is %d' % (demand, dialog.width())

# 3c. And on the revealed card no button may be cut. The row shares the card's width rather
#     than widening it, so an estimate that comes in short becomes clipped text, not a
#     wider window — which is how "E. Mastered" once reached the user as ". Mastere".
for button in [b for b in dialog.grade_buttons if b.text() and not b.isHidden()]:
    needed = QFontMetrics(button.font()).horizontalAdvance(button.text()) + 26
    assert button.width() >= needed,\
        '%r paints in %d px but needs %d' % (button.text(), button.width(), needed)
row_right = dialog.grade_widget.mapTo(dialog, QPoint(dialog.grade_widget.width(), 0)).x()
assert row_right <= dialog.width() - 8,\
    'the rating row must end inside the card: right edge %d of a %d px window' % (row_right, dialog.width())
assert dialog.layout().totalMinimumSize().width() <= dialog.width(),\
    'Qt itself must agree the row fits: %d of %d' % (dialog.layout().totalMinimumSize().width(), dialog.width())

# 3e. The row also has to sit symmetrically: the gap left of A. Again must equal the gap
#     right of D. Easy, or the row reads as shoved against one edge.
first_button = dialog.visible_grade_buttons()[0]
last_button = dialog.visible_grade_buttons()[-1]
left_gap = first_button.mapTo(dialog, QPoint(0, 0)).x()
right_gap = dialog.width() - last_button.mapTo(dialog, QPoint(last_button.width(), 0)).x()
assert abs(left_gap - right_gap) <= 2, ('A gap %d, D gap %d' % (left_gap, right_gap))
assert right_gap >= 8, 'D. Easy must clear the edge, gap was %d' % right_gap

# 3d. And when the row does need more than the card has, the card adapts rather than cutting
#     the last button. The birth minimum is only an estimate, so force the window narrower
#     than the row and check the reveal brings it back.
narrow=ReviewDialog(card(30,'thrive'),'center',lambda *_a:None,cfg)
narrow.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
narrow.setMinimumWidth(360);narrow.resize(360,narrow.height());app.processEvents();QTest.qWait(40)
assert narrow.width()<=400, 'the fixture needs a deliberately too-narrow card, got %d' % narrow.width()
narrow.answer_button.click();app.processEvents();QTest.qWait(60)
room=narrow.layout().contentsMargins().left()+narrow.layout().contentsMargins().right()
demand=narrow.row_demand()+room
assert narrow.width() >= demand,\
    'the card must grow to the row instead of clipping it: %d px window, %d px needed' % (narrow.width(), demand)
narrow_right=narrow.grade_widget.mapTo(narrow, QPoint(narrow.grade_widget.width(), 0)).x()
assert narrow_right <= narrow.width() - 8, (narrow_right, narrow.width())
narrow.close();app.processEvents()
choice=card(20,'option'); choice.update(mode='choice', options=['第一个释义','第二个释义','第三个释义','第四个释义'])
choice_dialog=ReviewDialog(choice,'center',lambda *_a:None,cfg)
choice_dialog.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
assert len(choice_dialog.choice_buttons)==4,len(choice_dialog.choice_buttons)
for choice_row in choice_dialog.choice_buttons:
    inner=choice_row.layout()
    assert int(inner.alignment()) & int(Qt.AlignmentFlag.AlignVCenter),\
        'the letter and its meaning must sit in the middle of the box'
choice_dialog.close()

# 4. Unpinning must work on the card the user is actually looking at, which after a
#    flip is a child embedded in the host window: window flags belong to the host.
ctl=DesktopReviewController(lambda:cfg, lambda *a:None, lambda *a:None, lambda *a:None)
ctl._lookup_known_words=lambda *a:None;ctl._lookup_relations=lambda *a:None;ctl.schedule=lambda **kw:None
ctl.session_target=2
first=ReviewDialog(card(3,'maintain'),'center',ctl._grade,cfg)
ctl.dialog=first;ctl.review_host=first;first.finished.connect(ctl._closed)
first.show();QTest.qWait(60);app.processEvents();QTest.qWait(60)
assert int(first.window().windowFlags()) & int(Qt.WindowType.WindowStaysOnTopHint)
first.pin_button.click();app.processEvents();QTest.qWait(60)
assert not (int(first.window().windowFlags()) & int(Qt.WindowType.WindowStaysOnTopHint)),'unpin must clear the flag'
first.pin_button.click();app.processEvents();QTest.qWait(60)
assert int(first.window().windowFlags()) & int(Qt.WindowType.WindowStaysOnTopHint),'re-pin must set it back'
second=card(4,'character')
ctl._prepared(second, None, ctl.generation, False, previous=first)
QTest.qWait(60);app.processEvents();QTest.qWait(60)
embedded=ctl.dialog
assert embedded is not first and getattr(embedded,'_embedded',False),(embedded is first, getattr(embedded,'_embedded',None))
assert embedded.window() is first,'the flipped card lives inside the host window'
assert int(embedded.window().windowFlags()) & int(Qt.WindowType.WindowStaysOnTopHint)
embedded.pin_button.click();app.processEvents();QTest.qWait(60)
assert not (int(embedded.window().windowFlags()) & int(Qt.WindowType.WindowStaysOnTopHint)),\
    'unpinning a flipped card must un-pin the host window, not the child widget'
assert embedded.isVisible() and embedded.window().isVisible(),'the card must not vanish when unpinned'

# 4b. Clearing the flag is not enough on Windows: the window keeps its band until
#     SetWindowPos is told otherwise, which is the gap between "the style changed" and
#     "the card actually stopped floating above everything".
bands=[]
real_band=rp.set_topmost_band
rp.set_topmost_band=lambda window,value: bands.append(value) or False
try:
    embedded.pin_button.click();app.processEvents();QTest.qWait(60)
    assert bands[-1:]==[True],'re-pin must move the window into the top band: %s' % bands
    del bands[:]
    embedded.pin_button.click();app.processEvents();QTest.qWait(60)
    assert bands[-1:]==[False],'unpin must move it out of the top band: %s' % bands
finally:
    rp.set_topmost_band=real_band

# 4c. Every pop-up starts pinned again. The toggle belongs to the window in hand; writing
#     it to the settings is what made the next card open behind everything.
cfg['review_pin']=True
fresh=ReviewDialog(card(9,'refuse'),'center',lambda *a:None,cfg)
assert int(fresh.windowFlags()) & int(Qt.WindowType.WindowStaysOnTopHint),'a new card must default to pinned'
assert fresh.pin_button.isChecked(),'the button must show the state the window is in'
assert cfg['review_pin'] is True,'the toggle must not be written back to the settings'
fresh.close()

print('Qt: ratings read A. Again … D. Easy, the card is a taskbar window, the pin is a drawn pushpin that moves the band, and unpin works on the flipped card')
