"""Run a Qt check with every statement of ours logged to disk, so a silent fastfail leaves
a last line instead of nothing.

    python tools/trace-to-file.py tests/windows-hint-row.py
"""
import io, os, runpy, sys

WATCHED = ('review_popup',)
target = sys.argv[1]
LOG = os.path.join(os.environ.get('TEMP', '.'), 'trace-last.log')
handle = open(LOG, 'w', encoding='utf-8')


def rec(msg):
    handle.write(msg + '\n')
    handle.flush()
    os.fsync(handle.fileno())


def tracer(frame, event, arg):
    name = os.path.basename(frame.f_code.co_filename or '')
    if not any(name.startswith(p) for p in WATCHED):
        return None
    if event == 'call':
        rec('CALL %s:%d %s' % (name, frame.f_lineno, frame.f_code.co_name))
    elif event == 'line':
        rec('LINE %s:%d' % (name, frame.f_lineno))
    return tracer


rec('--- start %s' % target)
sys.argv = [target]
try:
    sys.settrace(tracer)
    runpy.run_path(target, run_name='__main__')
except SystemExit as exit_error:
    rec('--- SystemExit %r' % exit_error.code)
except BaseException:
    import traceback
    rec('--- exception\n' + traceback.format_exc())
finally:
    sys.settrace(None)
    rec('--- end')
os._exit(0)
