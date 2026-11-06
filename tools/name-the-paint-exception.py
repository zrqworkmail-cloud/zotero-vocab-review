import io, os, sys, traceback
P = os.path.join(os.path.dirname(__file__), '..', 'tests', 'windows-badge-clearance.py')
src = io.open(os.path.abspath(P), encoding='utf-8').read()
env = {'__name__': '__main__', '__file__': os.path.abspath(P)}
exec(compile(src.split('def frame(')[0], env['__file__'], 'exec'), env)
d = env['frame']('loaf', 1, True) if False else None
print('harness loaded')
from zotero_global_capture import motion_view, candy_badge, card_motion
for name in ('card_motion', 'candy_badge', 'POP_TARGET'):
    print(name, 'in motion_view namespace:', hasattr(motion_view, name))
try:
    print('paint_extent:', candy_badge.paint_extent('Perfect', 1, max_width=400, scale=1.14))
except BaseException:
    traceback.print_exc()
try:
    print('badge_anchor:', card_motion.badge_anchor(630, 200, [(200, 240)]))
except BaseException:
    traceback.print_exc()
os._exit(0)
