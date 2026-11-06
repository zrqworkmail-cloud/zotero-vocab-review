"""Read-only: where each tier's badge lands on a real answer face, and how far it shrinks.

Prints the numbers the clearance rule chose, for the report and for AUDIT 9.49.
"""
import io, os, sys

HERE = os.path.dirname(__file__)
TEST = os.path.abspath(os.path.join(HERE, '..', 'tests', 'windows-badge-clearance.py'))
head = io.open(TEST, encoding='utf-8').read().split('def frame(')[0]
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), env)

app = env['app']
make = env['ReviewDialog']
cfg = dict(env['CFG'], review_motion_celebration=True)

from zotero_global_capture import card_motion, motion_view

for word in ('practicable', 'loaf'):
    dlg = make({'kind': 'due', 'card_id': 1, 'mode': 'typing', 'word': word,
                'meaning': env['MEANING'], 'example': 'It was a smile.',
                'literature': 'x', 'options': [], 'phonetic': 'pra'},
               'center', lambda *_a: None, cfg)
    dlg.show()
    dlg.resize(526, 630)
    app.processEvents()
    for box, pair in zip(dlg.letter_boxes, dlg.letter_positions):
        box.setText(pair[1])
    dlg.reveal(True)
    app.processEvents()
    print('== %s  card %d x %d' % (word, dlg.width(), dlg.height()))
    rows = dlg.celebration_rows()[1]
    spans = [(r.top(), r.bottom()) for r in rows]
    print('   protected %s' % (spans,))
    print('   free bands %s' % (card_motion.free_bands(dlg.celebration.height(), spans),))
    wide = dlg.celebration.width() * 0.78
    tall = dlg.celebration.height()
    for tier in (1, 2, 3, 4):
        y, fit = motion_view.badge_centre(tall, tier, wide, rows)
        reach = motion_view.badge_footprint(tier, wide)
        print('   tier %d: y=%3d reach=%5.0f fit=%.2f painted %d..%d'
              % (tier, y, reach, fit, y - reach * fit / 2, y + reach * fit / 2))
    dlg.deleteLater()
    app.processEvents()
sys.stdout.flush()
os._exit(0)
