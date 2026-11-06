"""Which part of the celebration paints the interpreter to death? Same harness, one knob.

The reveal itself returns fine; app.processEvents() then fastfails (0xC0000409), so the
suspect is a paint path. Each mode disables exactly one of the new pieces, so the first
mode that survives names the culprit:

    plain     nothing disabled
    nopaint   the overlay's paintEvent does nothing
    nooverlay the overlay widget is hidden before reveal
    nobadge   candy_badge.draw returns immediately (glyphs never painted)
    noglow    motion_view skips the glow/sunburst layers
    noanim    the overlay never starts its animation
"""
import io, os, sys

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tests',
                                    'windows-badge-clearance.py'))
MODE = sys.argv[1] if len(sys.argv) > 1 else 'plain'
src = io.open(TEST, encoding='utf-8').read()
g = {'__name__': '__main__', '__file__': TEST}
exec(compile(src.split('def frame(')[0], TEST, 'exec'), g)
app, ReviewDialog = g['app'], g['ReviewDialog']
from zotero_global_capture import candy_badge, motion_view

if MODE == 'nopaint':
    motion_view.CelebrationOverlay.paintEvent = lambda self, *_a: None
if MODE == 'nooverlay':
    _old_init = motion_view.CelebrationOverlay.__init__

    def _quiet_init(self, *a, **kw):
        _old_init(self, *a, **kw)
        self.setAttribute(g['Qt'].WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide = lambda *_a: None
    motion_view.CelebrationOverlay._skip = True
if MODE == 'nobadge':
    candy_badge.draw = lambda *a, **kw: None
if MODE == 'noglow':
    motion_view.CelebrationOverlay._paint_glow = lambda self, *a, **kw: None
if MODE == 'noanim':
    motion_view.CelebrationOverlay._start = lambda self, *a, **kw: None

dialog = ReviewDialog({'kind': 'due', 'card_id': 1, 'mode': 'typing', 'word': 'practicable',
                       'meaning': g['MEANING'], 'example': 'It was a characteristic smile.',
                       'literature': '这是一条例句。', 'options': [],
                       'phonetic': 'præktɪkəb(ə)l'},
                      'center', lambda *_a: None, dict(g['CFG'], review_motion_celebration=True))
dialog.show()
dialog.resize(526, 630)
app.processEvents()
for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
    box.setText(expected)
if MODE == 'nooverlay':
    dialog.celebration.hide()
dialog.reveal(True)
app.processEvents()
print('mode=%-10s survived reveal + events' % MODE)
sys.stdout.flush()
os._exit(0)
