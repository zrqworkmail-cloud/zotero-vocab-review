"""Where does the reveal fastfail (0xC0000409)? Reuse the badge check's own harness.

The preamble is exec'd straight from tests/windows-badge-clearance.py so nothing here can
drift from it; only the instrumented body is new. Records are flushed per line because a
fastfail kills the interpreter before any buffer could be written.
"""
import io, os, sys

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tests',
                                    'windows-badge-clearance.py'))
LOG = os.path.abspath(os.path.join(os.environ.get('TEMP', '.'), 'trace-reveal.log'))
fh = open(LOG, 'w', encoding='utf-8')
WATCHED = ('review_popup', 'card_motion', 'candy_badge', 'motion_view', 'morphology',
           'review_logic', 'input_mode')


def rec(msg):
    fh.write('%s\n' % msg)
    fh.flush()
    os.fsync(fh.fileno())


def tracer(frame, event, arg):
    name = os.path.basename(frame.f_code.co_filename or '')
    if not any(name.startswith(p) for p in WATCHED):
        return None
    if event == 'call':
        rec('CALL %s:%d %s' % (name, frame.f_lineno, frame.f_code.co_name))
    elif event == 'line':
        rec('LINE %s:%d' % (name, frame.f_lineno))
    return tracer


src = io.open(TEST, encoding='utf-8').read()
head = src.split('def frame(')[0]
g = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), g)
rec('--- harness exec ok')

celebrate = (len(sys.argv) < 2) or sys.argv[1] == 'on'
g['CFG']['review_motion_celebration'] = celebrate
dialog = g['ReviewDialog']({'kind': 'due', 'card_id': 1, 'mode': 'typing',
                            'word': 'practicable', 'meaning': g['MEANING'],
                            'example': 'It was a characteristic smile.',
                            'literature': '这是一条例句。', 'options': [],
                            'phonetic': 'præktɪkəb(ə)l'},
                           'center', lambda *_a: None, dict(g['CFG']))
app = g['app']
dialog.show()
dialog.resize(526, 630)
app.processEvents()
rec('--- shown (celebration=%s)' % celebrate)
for box, (_, expected) in zip(dialog.letter_boxes, dialog.letter_positions):
    box.setText(expected)
rec('--- boxes filled')
sys.settrace(tracer)
dialog.reveal(True)
sys.settrace(None)
rec('--- reveal returned')
app.processEvents()
rec('--- processEvents returned')
image = dialog.grab().toImage()
rec('--- grabbed %dx%d' % (image.width(), image.height()))
os._exit(0)
