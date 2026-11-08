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
from zotero_global_capture.review_popup import ReviewDialog


from PyQt6.QtTest import QTest
app=QApplication([])

# The four things the user asked the card to look like: answers as their own letter
# column with a hanging indent, round speaker buttons everywhere, the word and its
# phonetic on the centre line, and the word-list attribution as a small chip at the
# foot of the card with no provenance line printed on it.
cfg={'review_auto_word':False,'review_auto_example':False,'review_auto_example_mode':'off',
     'review_hint_audio':False,'review_theme':'light','review_position':'center'}
long_meaning='n. 一种用于在长时间运行之后仍然保持稳定的机制，并且需要在部署前经过完整的回归测试'
question={'kind':'new','card_id':201,'mode':'choice','word':'increase','meaning':long_meaning,
          'phonetic':'/ɪnˈkriːs/','example':'','literature':'',
          'options':[long_meaning,'第二项释义','第三项释义','第四项释义']}
dialog=ReviewDialog(question,'center',lambda *_a:None,cfg)
dialog.show();QTest.qWait(80);app.processEvents();QTest.qWait(80)

row=dialog.choice_buttons[0]
assert row.objectName()=='choice' and isinstance(row,QWidget) and not isinstance(row,QPushButton)
# A plain QWidget ignores its stylesheet background/border unless it opts into styled
# drawing, which is why the options looked like loose text instead of boxed choices.
assert row.testAttribute(Qt.WidgetAttribute.WA_StyledBackground),'each option needs its own box'
from zotero_global_capture import review_popup as rp
for theme in ('light','dark'):
    style=rp.popup_style({'review_theme':theme})
    assert 'QWidget#choice {' in style and 'border: 1px solid' in style, theme
    # E/已掌握 was retired on 2026-11-07: no stylesheet rule may resurrect its own colours.
    assert 'QPushButton#mastered' not in style, (theme, 'the retired 已掌握 button must stay gone')
    assert 'suggestMastered' not in style, (theme, 'its suggestion highlight must stay gone too')
assert row.letter_label.text()=='A' and row.letter_label.width()==18,(row.letter_label.text(),row.letter_label.width())
assert row.text_label.wordWrap() and row.text_label.text()==long_meaning,row.text_label.text()
assert '…' not in row.text_label.text(),'the option is still being truncated'
assert row.text_label.x()>=row.letter_label.x()+row.letter_label.width(),(row.text_label.x(),row.letter_label.x())
# Both columns must paint from the top of the row. A default QLabel centres its text
# vertically, so in a stretched row the letter sat above the word — the misalignment
# the user saw on the real card.
for label in (row.letter_label, row.text_label):
    assert int(label.alignment()) & int(Qt.AlignmentFlag.AlignTop),(label.objectName(),label.alignment())
assert int(row.text_label.alignment()) & int(Qt.AlignmentFlag.AlignLeft)

centered=int(Qt.AlignmentFlag.AlignHCenter)
assert int(dialog.question_label.alignment())&centered,dialog.question_label.alignment()
assert int(dialog.phonetic_label.alignment())&centered,dialog.phonetic_label.alignment()

assert not dialog.book_chip.isVisible(),'the pill row is written at birth but stays hidden'
assert [pill.text() for pill in dialog.book_chips]==['四级词表','六级词表','六级核心'],\
    'one pill per list the word belongs to, decided before the card is sized: %s' % [p.text() for p in dialog.book_chips]
row.click();app.processEvents();QTest.qWait(80)
assert dialog.answer_shown
assert dialog.book_chip.isVisible() and all(pill.isVisible() for pill in dialog.book_chips)

# 4b. The word itself sits on the centre line and the speaker hugs its right edge; and the
#     disc carries only the speaker, no leftover arc that reads as a stray dot.
content = dialog.answer_word.parentWidget()
word_left = dialog.answer_word.mapTo(content, QPoint(0, 0)).x()
word_centre = word_left + dialog.answer_word.width() / 2.0
assert abs(word_centre - content.width() / 2.0) <= 6, (word_centre, content.width())
speaker_left = dialog.answer_speaker.mapTo(content, QPoint(0, 0)).x()
assert speaker_left >= word_left + dialog.answer_word.width(), (speaker_left, word_left)
plain = rp.speaker_icon('#27344d', '#eef2ff', '#8996e8', 32).pixmap(32, 32).toImage()
assert (plain.pixel(25, 16) >> 24) & 0xFF and (plain.pixel(25, 16) & 0x00FFFFFF) == 0xeef2ff,     'the space right of the speaker must stay the disc colour: %s' % hex(plain.pixel(25, 16))
chip_font=dialog.font(); chip_font.setPixelSize(12)
fm=QFontMetrics(chip_font)
if dialog.book_chips:
    # The pills paint with the stylesheet's own face, so measure with a pill's own font:
    # the dialog font at "12px" is a different face and under-reads the text.
    dialog.book_chips[0].ensurePolished()
    fm=QFontMetrics(dialog.book_chips[0].font())

# 4c. The word-list attribution is a row of small pills rather than one long label: the
#     dots between the names are gone, each box is only just bigger than its own text,
#     and the provenance lives in the tooltip of the pill it explains.
assert '来源' not in ' '.join(pill.text() for pill in dialog.book_chips)
for pill in dialog.book_chips:
    assert '·' not in pill.text(),(pill.text(),'the separator is what read as a stray dot')
    assert pill.objectName()=='bookChip',pill.objectName()
    advance=fm.horizontalAdvance(pill.text())
    assert 0 < pill.width()-advance <= 2*rp.CHIP_PADDING_X+6,(pill.text(),pill.width(),advance)
    assert 0 < pill.height()-fm.height() <= 2*rp.CHIP_PADDING_Y+8,(pill.text(),pill.height(),fm.height())
assert [pill.toolTip() for pill in dialog.book_chips]==['来源：ECDICT 四六级词表','来源：ECDICT 四六级词表',
                                                        '来源：CET-6 Top 500 社区整理'],[p.toolTip() for p in dialog.book_chips]
assert '六级社区核心词' not in ' '.join(pill.text() for pill in dialog.book_chips),\
    'the pills use the same names as the 词书 menu'
chip_rule=rp.POPUP_STYLE[rp.POPUP_STYLE.index('QLabel#bookChip {'):]
chip_rule=chip_rule[:chip_rule.index('}')+1]
assert 'padding: %dpx %dpx;' % (rp.CHIP_PADDING_Y, rp.CHIP_PADDING_X) in chip_rule,\
    'the measured padding must be the padding the stylesheet paints: %s' % chip_rule
assert 'margin: 0;' in chip_rule,\
    'Qt gives a styled QLabel a 6px margin, which is what made these boxes roomier than their text: %s' % chip_rule
pills_width=sum(pill.width() for pill in dialog.book_chips)+rp.CHIP_GAP*(len(dialog.book_chips)-1)
assert dialog.book_chip.width()>=pills_width,(dialog.book_chip.width(),pills_width)
row_left=dialog.book_chip.mapTo(dialog,QPoint(0,0)).x()
assert abs((row_left+dialog.book_chip.width()/2.0)-(dialog.width()/2.0))<=8,\
    'the pill row reads as one line at the foot only if it is centred: %s' % (row_left,dialog.width())
printed=''.join(label.text() for label in dialog.findChildren(QLabel) if label.isVisible())
assert '来源' not in printed and '词表归属' not in printed,printed[:400]
assert dialog.layout().itemAt(dialog.layout().count()-1).widget() is dialog.book_chip,'the pill row belongs at the foot'

# 4d. ... and the foot means directly under the rating row. The answer used to leave the
#     window's leftover height as a blank band with the pills stranded in it, which read as
#     a broken layout rather than as a card that had finished its content.
assert not dialog.later.isVisible(),'「不评分，结束」 must not take a row of its own any more'
row_bottom = dialog.grade_widget.mapTo(dialog, QPoint(0, dialog.grade_widget.height())).y()
pills_top = dialog.book_chip.mapTo(dialog, QPoint(0, 0)).y()
pills_bottom = dialog.book_chip.mapTo(dialog, QPoint(0, dialog.book_chip.height())).y()
assert 0 <= pills_top - row_bottom <= dialog.layout().spacing() + 8,\
    ('the pills must hug the row above them', row_bottom, pills_top)
assert 0 <= dialog.height() - pills_bottom <= 24,\
    ('the card must end where its content ends', dialog.height(), pills_bottom)
assert dialog.answer_scroll.minimumHeight() >= 240,\
    'the explanations need a real floor: they are why the card exists'
ungraded=[action.text() for action in dialog.findChild(QMenu).actions() if '不评分' in action.text()]
assert ungraded,'ending without a rating still has to be reachable: %s' % ungraded

# 5. Pin: the card can be taken off the top of the screen without hiding it, and the
#    choice is reported back so the next card starts the same way.
top_row=dialog.findChild(QMenu)
menu_texts=[action.text() for action in top_row.actions()]
assert any('隐藏 Anki 主窗口' in text for text in menu_texts),menu_texts
assert any('退出 Anki' in text for text in menu_texts),menu_texts
assert dialog.pin_button.isCheckable() and dialog.pin_button.isChecked(),'the card starts pinned'
# The pin is the usual pushpin shape, not the word 置顶: a shape is readable at a glance
# and keeps the header narrow. Screen readers still get the words.
assert dialog.pin_button.text()=='',dialog.pin_button.text()
assert not dialog.pin_button.icon().isNull(),'the pin needs a drawn icon'
assert any(size.width()>=16 for size in dialog.pin_button.icon().availableSizes()),dialog.pin_button.icon().availableSizes()
assert '置顶' in dialog.pin_button.toolTip() and '置顶' in dialog.pin_button.accessibleName()
hint_before=dialog.pin_button.toolTip()
assert int(dialog.windowFlags()) & int(Qt.WindowType.WindowStaysOnTopHint)
seen_pins=[]
dialog.pin_changed.connect(lambda value: seen_pins.append(value))
before=dialog.geometry()
dialog.pin_button.click();app.processEvents();QTest.qWait(60)
assert not (int(dialog.windowFlags()) & int(Qt.WindowType.WindowStaysOnTopHint)),dialog.windowFlags()
assert dialog.isVisible(),'unpinning must not hide the card'
assert dialog.geometry()==before,(dialog.geometry(),before)
assert seen_pins==[False],seen_pins
dialog.pin_button.click();app.processEvents();QTest.qWait(60)
assert int(dialog.windowFlags()) & int(Qt.WindowType.WindowStaysOnTopHint)
assert seen_pins==[False,True],seen_pins

listen={'kind':'new','card_id':202,'mode':'listening','word':'differ','meaning':'v. 不同',
        'example':'','literature':'','options':[]}
listening=ReviewDialog(listen,'center',lambda *_a:None,cfg)
listening.show();QTest.qWait(80);app.processEvents();QTest.qWait(80)
assert listening.listen_button.objectName()=='speaker',listening.listen_button.objectName()
assert listening.listen_button.width()==32 and listening.listen_button.height()==32,listening.listen_button.size()
assert listening.listen_button.iconSize().width()==32,'the disc must be shown at the size it is drawn'
assert listening.listen_button.text()=='' and listening.listen_button.accessibleName()=='重新播放单词发音'
for button in dialog.findChildren(QPushButton):
    if button.objectName()=='speaker':
        # Each disc is as tall as the letters beside it, and always fills its button:
        # a push button defaults to a 16px icon, which used to halve the drawn disc.
        assert 20<=button.width()<=32,(button.objectName(),button.size())
        assert button.iconSize().width()==button.width(),(button.objectName(),button.size(),button.iconSize())
word_speaker=[b for b in dialog.findChildren(QPushButton)
              if b.objectName()=='speaker' and b.width()==rp.WORD_SPEAKER]
assert word_speaker,'the word row needs a disc as tall as the word letters'

# 6. A cloze asks for the headword: the boxes are the base form's letters, and the form the
#    sentence used is shown as a detail instead of being what the user has to type.
cloze={'kind':'due','card_id':301,'mode':'cloze','word':'pattern','meaning':'n. 模式',
       'example':'','literature':'','options':[],'phonetic':'/ˈpætn/','snapshot':{},
       'answer_form':'pattern','cloze_shown':'patterns',
       'cloze':'Their descriptions seemed to follow a set _______.','source_form':'pattern'}
cloze_dialog=ReviewDialog(cloze,'center',lambda *_a:None,cfg)
cloze_dialog.show();QTest.qWait(80);app.processEvents();QTest.qWait(80)
assert len(cloze_dialog.letter_boxes)==7,len(cloze_dialog.letter_boxes)
assert [c for _i,c in cloze_dialog.letter_positions]==list('pattern'),cloze_dialog.letter_positions
for box, char in zip(cloze_dialog.letter_boxes, 'pattern'): box.setText(char)
cloze_dialog.check_input();app.processEvents();QTest.qWait(80)
assert cloze_dialog.answer_shown,'the base form must be accepted as correct'
printed=''.join(label.text() for label in cloze_dialog.findChildren(QLabel) if label.isVisible())
assert 'patterns' in printed and '例句中的形式' in printed, printed[:400]
cloze_dialog.close();app.processEvents()

print('Qt: answers hang-align under their own letter column, prompts centre, speaker stays round, attribution is a foot chip')
