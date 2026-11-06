"""Run a Qt check with faulthandler and markers, to see how it really dies."""
import faulthandler
import runpy
import sys

faulthandler.enable(file=sys.stderr, all_threads=True)
print('runner: starting', file=sys.stderr, flush=True)
try:
    runpy.run_path(sys.argv[1], run_name='__main__')
except SystemExit as code:
    print('runner: SystemExit', code.code, file=sys.stderr, flush=True)
    raise
except BaseException as error:
    print('runner: exception', type(error).__name__, str(error)[:200], file=sys.stderr, flush=True)
    raise
print('runner: finished clean', file=sys.stderr, flush=True)
