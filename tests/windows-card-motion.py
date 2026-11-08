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
from PyQt6.QtGui import QCursor,QFont,QFontDatabase,QFontMetrics,QColor,QPainter,QImage,QDesktopServices
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

# 3. A flawless spelling puts a celebration over the card — on top, harmless, and see-through
#    everywhere except the drawn shapes.
dialog = card()
spell(dialog)
overlay = dialog.celebration
assert overlay is not None and overlay.isVisible(), 'a clean spelling must celebrate'
assert overlay.parent() is dialog, 'the overlay belongs to this card and dies with it'
assert overlay.geometry() == dialog.rect(), (overlay.geometry(), dialog.rect())
assert overlay.tier in (1, 2), overlay.tier
assert overlay.hasFocus() is False and overlay.focusPolicy() == Qt.FocusPolicy.NoFocus
assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents), \
    'the celebration must never eat the Enter that pages the card'
assert overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground), \
    'the overlay has to be a layer, not a panel'

# 3b. The drawn badge itself must leave the card visible around it. The learner asked for
#     "有的地方需要透明处理" after the earlier version painted a flat disc the width of the
#     card; the only honest check is to paint into an alpha image and read the corners.
from zotero_global_capture import candy_badge
for tier in (1, 2, 3, 4):
    image = QImage(510, 541, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pose = card_motion.badge_pose(0.55, tier, card_motion.TIMING['badge']['duration'])
    candy_badge.draw(painter, QPoint(255, 325), card_motion.tier_caption(tier), tier, pose,
                     max_width=510 * 0.78)
    painter.end()
    for x, y in ((2, 2), (507, 2), (2, 538), (507, 538), (255, 30), (60, 500)):
        assert image.pixelColor(x, y).alpha() == 0, \
            ('nothing may be painted out there', tier, x, y, image.pixelColor(x, y).rgba())
    centre = image.pixelColor(255, 325)
    assert centre.alpha() > 200, ('the word itself has to be solid', tier, centre.rgba())
    painted = sum(1 for y in range(0, 541, 9) for x in range(0, 510, 9)
                  if image.pixelColor(x, y).alpha() > 8)
    assert painted < 510 * 541 / 81 * 0.55, \
        ('the badge should cover a band, not the card', tier, painted)

# 3c. The centre anchor is the learner's choice, but two rows must still survive it: the word
#     being celebrated and the rating buttons that page the card. Compared byte for byte, not
#     eyeballed — 0.24 once covered the word and nothing in the suite noticed.
dialog = card()
spell(dialog)
tier = dialog.celebration.tier
dialog.celebration.stop()
app.processEvents()
plain = dialog.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
painted = QImage(plain)
painter = QPainter(painted)
pose = card_motion.badge_pose(0.55, tier, card_motion.TIMING['badge']['duration'])
candy_badge.draw(painter, dialog.celebration._anchor(), card_motion.tier_caption(tier), tier,
                 pose, max_width=dialog.width() * 0.78)
painter.end()


def band(widgets):
    tops = [w.mapTo(dialog, QPoint(0, 0)).y() for w in widgets]
    bottoms = [w.mapTo(dialog, QPoint(0, 0)).y() + w.height() for w in widgets]
    return min(tops), max(bottoms)


def visible_word_label():
    """The answer face shows the word as one label (syllable dots in it); the letter boxes
    belong to the question face and are hidden here, so asking them where the word is would
    have failed for the wrong reason."""
    target = ''.join(dialog.answer_form).replace(' ', '')
    for widget in dialog.findChildren(QLabel):
        if not widget.isVisible():
            continue
        text = (widget.text() or '').replace('·', '').replace(' ', '')
        if text.casefold() == target.casefold():
            return widget
    return None


anchor = dialog.celebration._anchor()
# The contract changed on 2026-11-05. This line used to pin the anchor to
# `height × BADGE_TOP_FRACTION`, and that fraction was the bug: it cleared the answer word by
# 2 px on tier 3, which is luck, not a rule. The overlay now asks `card_motion.badge_anchor`
# for the centre of the tallest band its protected rows leave free, and shrinks rather than
# sit on the word. The band is recomputed here from the card's own rows, and the pixel loop
# below is what actually proves nothing lands on them.
_spans = [(row.top(), row.bottom()) for row in dialog.celebration.protected]
bands = card_motion.free_bands(dialog.celebration.height(), _spans)
_space, band_top, band_bottom = max(((b - t, t, b) for t, b in bands),
                                    default=(dialog.height(), 0, dialog.height()))
assert abs(anchor.y() - (band_top + band_bottom) / 2.0) <= 1, \
    ('the anchor is the centre of the free band, not of the card', anchor.y(),
     band_top, band_bottom, _spans)
assert _spans, ('the card must hand the overlay the rows it has to avoid', anchor.y())
word = visible_word_label()
assert word is not None, 'the answer face must show the word as a label to test against'
word_band = band([word])
grade_band = band(dialog.grade_buttons)
verdict_band = band([dialog.result_label])
for name, (y0, y1) in (('word', word_band), ('grade', grade_band), ('verdict', verdict_band)):
    for y in range(y0, y1):
        for x in range(0, dialog.width(), 3):
            assert plain.pixelColor(x, y) == painted.pixelColor(x, y), \
                ('the celebration must not paint over the %s row' % name, x, y, (y0, y1))

# 3d. Nothing inside the reward window may be drawn on top of its own word — at any tier.
#     The learner's rule, said twice: 「perfect不应该被下面这个东西挡住，所有的其他的那几个
#     都是这样的要求，不要被挡住」. This is about the badge's own parts (ribbon, gem, stars,
#     sparkles), not about the card behind it.
POP = card_motion.POP_TARGET
for tier in (1, 2, 3, 4):
    word_text = card_motion.tier_caption(tier)
    pixel = candy_badge.fit_pixel(word_text, dialog.width() * 0.78)
    badge_width = min(dialog.width() * 0.78, pixel * 5.4)
    geo = candy_badge.geometry(word_text, pixel, QPoint(255, 270), badge_width)
    assert candy_badge.overlaps_word(word_text, pixel, QPoint(255, 270), badge_width) == [], \
        ('these pieces would be drawn over the word', tier,
         candy_badge.overlaps_word(word_text, pixel, QPoint(255, 270), badge_width))
    assert geo['ribbon_top'] >= geo['word_bottom'], \
        ('the ribbon must start below the extruded word', tier, geo['ribbon_top'],
         geo['word_bottom'])
    # Worst reach is the entrance overshoot, measured from the anchor it scales about.
    reach = 270 + (geo['gem_bottom'] - 270) * POP
    assert reach < grade_band[0], ('even mid-pop the gem must not touch the rating row',
                                   tier, reach, grade_band[0])
    assert 270 + (geo['stars_top'] - 270) * POP > word_band[1], \
        ('and the star cluster must not touch the word row', tier,
         270 + (geo['stars_top'] - 270) * POP, word_band[1])

# 4. Motion does not block paging: Enter during the celebration still grades. A flawless
#    spelling recommends Easy, so that is the rating the keystroke must record.
dialog = card()
recorded = []
dialog.grade = lambda _dialog, ease: recorded.append(('grade', ease))
spell(dialog)
assert dialog.celebration.active(), 'the celebration should still be running here'
QTest.keyClick(dialog, Qt.Key.Key_Return)
run(60)
assert recorded == [('grade', 4)], 'Enter must reach the rating path while the badge is on screen: %s' % recorded

# 5. A wrong answer celebrates nothing, and neither does any other question type.
dialog = card()
dialog.answer_button.click()
app.processEvents(); QTest.qWait(60)
assert dialog.celebration is None, 'showing the answer is not a win'
choice = card(word='reward', mode='choice')
choice.reveal(True)
assert choice.celebration is None, 'only the spelling card celebrates'

# 6. The two switches really switch, and they are independent.
quiet = card(cfg={'review_motion_hop': False, 'review_motion_celebration': False})
spell(quiet)
assert quiet.celebration is None, 'both off must not build an overlay at all'
badge_only = card(cfg={'review_motion_hop': False, 'review_motion_celebration': True})
box = badge_only.letter_boxes[0]
home = box.pos()
box.setText(box.text())
app.processEvents()
QTest.qWait(60); app.processEvents()
assert box.pos() == home, 'with the hop switch off the letter box must not move'
spell(badge_only)
assert badge_only.celebration is not None and badge_only.celebration.isVisible(), \
    'the celebration switch on its own still celebrates'
hop_only = card(cfg={'review_motion_hop': True, 'review_motion_celebration': False})
spell(hop_only)
assert hop_only.celebration is None, 'the hop switch on must not drag the badge along'
full = card(cfg={'review_motion_hop': True, 'review_motion_celebration': True})
spell(full)
assert full.celebration.with_confetti, 'a clean recall in full gets the falling paper'

# 7. Hiding the card stops the celebration — the shape that produced the F-key ghosts.
dialog = card()
spell(dialog)
dialog.celebration.play(1, {'review_motion_hop': True, 'review_motion_celebration': True})
assert dialog.celebration.active()
dialog.hide()
app.processEvents(); QTest.qWait(60)
assert not dialog.celebration.isVisible(), 'a hidden card must not keep an overlay alive'
assert not dialog.celebration.active(), 'and its animation must be stopped, not left running'

# 8. The look-back must never celebrate again.
dialog = card()
dialog.review_note = {'correct': True, 'rating': 'Easy', 'hint_uses': 0,
                      'incorrect_letters': 0, 'failed_attempts': 0}
dialog.enter_review()
assert dialog.celebration is None, '回看 is a look, not an award'

print('Qt: 字母落格会跳、错字母会抖并回到原位；拼写全对才庆祝，金色立体字只有英文、四周完全透明、'
      '不挡回车，两个动效开关互不牵连，隐藏卡片即停止')
