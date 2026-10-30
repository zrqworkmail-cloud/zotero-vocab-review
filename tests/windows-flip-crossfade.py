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

# FlipTransition (the old crossfade widget) was removed from review_popup, which made
# this check import a name that no longer exists. reveal() now rebuilds the card in
# place with painting suppressed, so the check keeps covering the same guarantee: the
# question face and the answer face are reconciled in a single repaint, without moving
# or resizing the window, in both themes.
for theme in ('dark','light'):
 cfg={'review_auto_word':False,'review_auto_example':False,'review_auto_example_mode':'off',
      'review_hint_audio':False,'review_theme':theme,'review_position':'center'}
 question={'kind':'due','card_id':101,'mode':'typing','word':'maintenance','meaning':'维护，保养',
           'example':'The company needs to maintain the equipment.','literature':'','options':[]}
 dialog=ReviewDialog(question,'center',lambda *_a:None,cfg)
 dialog.show();QTest.qWait(80);app.processEvents();QTest.qWait(80)
 before=dialog.geometry()
 suppressed=[]
 original=dialog.setUpdatesEnabled
 def watch(enabled):
  suppressed.append(bool(enabled))
  return original(enabled)
 dialog.setUpdatesEnabled=watch
 try:
  for box,char in zip(dialog.letter_boxes,question['word']): box.setText(char)
  dialog.reveal(True)
  app.processEvents()
 finally:
  del dialog.setUpdatesEnabled
 assert suppressed and suppressed[0] is False and suppressed[-1] is True,(theme,suppressed)
 assert dialog.geometry()==before,(theme,dialog.geometry(),before)
 assert dialog.isVisible() and dialog.answer_shown,(theme,dialog.isVisible(),dialog.answer_shown)
 assert not dialog._flipping
 assert not dialog.prompt_label.isVisible() and not dialog.question_block.isVisible()
 assert not dialog.letter_scroll.isVisible()
 assert dialog.answer_word.text()==question['word'] and dialog.answer_word.isVisible()
 assert dialog.answer_scroll.isVisible() and dialog.grade_widget.isVisible()
 assert dialog.grade_buttons[2].isEnabled() and dialog.later.text()=='不评分，结束'
 assert '建议' in dialog.status.text(),dialog.status.text()
 shot=dialog.grab().toImage()
 assert shot.pixelColor(shot.width()//2,shot.height()//2).alpha()>0
 dialog.close();app.processEvents()

# Revealing a second time must be a no-op, not a second rebuild.
dialog=ReviewDialog({'kind':'new','card_id':102,'mode':'choice','word':'cat','meaning':'猫',
                     'example':'','literature':'','options':['猫','狗','鸟','鱼']},'center',
                    lambda *_a:None,{'review_auto_word':False,'review_theme':'dark'})
dialog.show();QTest.qWait(80);app.processEvents()
dialog.reveal(True)
geometry=dialog.geometry()
calls=[]
original=dialog.setUpdatesEnabled
dialog.setUpdatesEnabled=lambda enabled:(calls.append(bool(enabled)),original(enabled))
dialog.reveal(False)
del dialog.setUpdatesEnabled
assert calls==[],calls
assert dialog.geometry()==geometry,(dialog.geometry(),geometry)
dialog.close()
print('Qt: in-place reveal repaints once, keeps geometry, and stays idempotent in both themes')
