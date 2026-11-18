"""Report the five separate facts that get conflated after a change.

    source     what the branch says
    tests      whether the suites pass here
    deployed   whether the installed add-on files match the branch
    loaded     whether the running Anki started *after* those files were written
    on-screen  whether the desktop is even available to look at

Read-only throughout: it never writes, restarts, syncs, or opens the collection.
While Anki is running, `collection.anki2` is read through AnkiConnect instead,
because a plain SQLite read misses the write-ahead log and returns a stale view.

    python tools/verify-state.py            # five-layer panel
    python tools/verify-state.py --tests    # also run the suites (slow)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / 'anki-global-addon' / 'zotero_global_capture'
LOG_NAME = 'zotero_global_capture_runtime.log'
START_MARKERS = ('desktop review controller initialized', 'hotkey registered')

# Source-only modules are deliberately absent from the package; runtime files are
# produced by Anki or the user. Neither side is evidence of a code drift.
SOURCE_ONLY = {'kyle_enrich.py', 'kyle_books.py'}
RUNTIME_ONLY = {'meta.json', 'config.json', 'difficulty.json'}


def appdata() -> Path:
    return Path(os.environ['APPDATA'])


def installed_dir() -> Path:
    return appdata() / 'Anki2' / 'addons21' / 'zotero_global_capture'


def runtime_log() -> Path:
    return Path(os.environ.get('TEMP', str(appdata()))) / LOG_NAME


def sha256(path: Path) -> str:
    # Line endings are not a semantic difference for Python, and git's autocrlf
    # checkout can rewrite them under a file that was deployed with cp.
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()[:16]


def _generated_backup(relative: Path) -> bool:
    """Install-dir backups are evidence of an edit, not of package drift.

    The deployment scripts leave ``*.bak-<time>`` / ``*.before-<reason>`` copies and
    whole ``pre-deploy-<time>/`` snapshots next to the live files.  Counting those as
    EXTRA made the panel noisy enough to hide a real extra module, and made the
    loaded-layer timestamp compare against a backup rather than shipped code.
    """
    if any(part.startswith('pre-deploy-') for part in relative.parts):
        return True
    name = relative.name
    return any(token in name for token in ('.bak-', '.bak', '.before-', '.before',
                                           '.orig', '.rej'))


def _packaged_files(root: Path) -> list[Path]:
    """Every file whose content belongs to the add-on, including subpackages.

    The old deployed check only used ``root.glob('*.py')``.  That silently ignored
    ``domain/`` and ``lexicon/`` after the first modularisation, so a missing or
    stale subpackage could still be reported as green.  Keep this list in the same
    shape as the installer: source-only modules and generated files are excluded.
    """
    result = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part == '__pycache__' for part in relative.parts):
            continue
        if _generated_backup(relative):
            continue
        if path.suffix == '.pyc' or relative.parts[0] == 'user_files':
            continue
        if relative.name in SOURCE_ONLY or relative.name in RUNTIME_ONLY:
            continue
        result.append(relative)
    return sorted(result, key=lambda item: item.as_posix())


def run(*cmd: str) -> str:
    try:
        # The tools here emit UTF-8 (node's ℹ, Python's 中文 test names); decoding with
        # the Windows console code page turns that into replacement characters.
        done = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=30)
        return (done.stdout or '') + (done.stderr or '')
    except Exception as error:  # a missing tool is a finding, not a crash
        return '%s: %s' % (type(error).__name__, error)


# ---------------------------------------------------------------- source layer
def layer_source() -> list:
    branch = run('git', '-C', str(REPO), 'rev-parse', '--abbrev-ref', 'HEAD').strip()
    head = run('git', '-C', str(REPO), 'log', '-1', '--oneline').strip()
    dirty = [line for line in run('git', '-C', str(REPO), 'status', '--porcelain').splitlines() if line.strip()]
    out = ['branch %s' % branch, 'HEAD    %s' % head]
    out.append('%d uncommitted paths' % len(dirty) if dirty else 'tree clean')
    for line in dirty[:8]:
        out.append('  ' + line)
    if len(dirty) > 8:
        out.append('  ... and %d more' % (len(dirty) - 8))
    return out


# ------------------------------------------------------------- deployed layer
def layer_deployed() -> list:
    target = installed_dir()
    if not target.is_dir():
        return ['NOT INSTALLED: %s does not exist' % target]
    source_files = _packaged_files(SRC)
    lines, drifted, absent = [], [], []
    for relative in source_files:
        other = target / relative
        name = relative.as_posix()
        if not other.exists():
            absent.append(name)
        elif sha256(SRC / relative) != sha256(other):
            drifted.append(name)
    source_names = {item.as_posix() for item in source_files}
    extra = sorted(item.as_posix() for item in _packaged_files(target)
                   if item.as_posix() not in source_names)
    lines.append('%d of %d files match the install dir' %
                 (len(source_files) - len(drifted) - len(absent), len(source_files)))
    for name in drifted:
        lines.append('  DRIFT  %s (branch and installed differ)' % name)
    for name in absent:
        lines.append('  ABSENT %s (never deployed)' % name)
    for name in extra:
        lines.append('  EXTRA  %s (installed only)' % name)
    newest = max(((target / item).stat().st_mtime for item in _packaged_files(target)), default=0)
    if newest:
        lines.append('  newest installed file: %s' % datetime.fromtimestamp(newest).strftime('%Y-%m-%d %H:%M:%S'))
    return lines


# --------------------------------------------------------------- loaded layer
def anki_running() -> bool:
    return 'Anki.exe' in run('tasklist', '/FI', 'IMAGENAME eq Anki.exe', '/NH')


def anki_connect(action: str, params=None):
    """AnkiConnect is plain HTTP on loopback; the machine's proxy must be bypassed."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    body = json.dumps({'action': action, 'version': 6, 'params': params or {}}).encode('utf-8')
    request = urllib.request.Request('http://127.0.0.1:8765', data=body,
                                     headers={'Content-Type': 'application/json'})
    with opener.open(request, timeout=10) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if payload.get('error'):
        raise RuntimeError(payload['error'])
    return payload['result']


def layer_loaded() -> list:
    lines = ['Anki process: %s' % ('running' if anki_running() else 'not running')]
    if not anki_running():
        return lines
    try:
        lines.append('AnkiConnect: version %s' % anki_connect('version'))
    except Exception as error:
        lines.append('AnkiConnect: unreachable (%s) — add-on may have failed to import' % type(error).__name__)
        return lines

    log = runtime_log()
    if not log.exists():
        lines.append('runtime log: missing, cannot tell when the add-on last started')
        return lines
    stamps = []
    for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if match and any(marker in line for marker in START_MARKERS):
            stamps.append(datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S'))
    target = installed_dir()
    newest = max((datetime.fromtimestamp((target / item).stat().st_mtime)
                  for item in _packaged_files(target)), default=None)
    if not stamps:
        lines.append('add-on start: no startup line in the log yet')
    elif newest is None:
        lines.append('add-on start: %s (installed files unreadable)' % stamps[-1])
    elif stamps[-1] < newest:
        lines.append('  *** NOT LOADED: installed files written %s, add-on last started %s' %
                     (newest.strftime('%H:%M:%S'), stamps[-1].strftime('%H:%M:%S')))
        lines.append('  *** Anki must be restarted before the deployed code takes effect')
    else:
        lines.append('add-on start: %s — later than every installed file, so the running code is the deployed code'
                     % stamps[-1].strftime('%Y-%m-%d %H:%M:%S'))
    return lines


# --------------------------------------------------------------- config layer
def load_logic():
    spec = importlib.util.spec_from_file_location('verify_review_logic', SRC / 'review_logic.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def layer_config() -> list:
    meta = installed_dir() / 'meta.json'
    if not meta.exists():
        return ['no meta.json']
    config = json.loads(meta.read_text(encoding='utf-8')).get('config', {})
    try:
        logic = load_logic()
    except Exception as error:
        return ['cannot read the book model: %s: %s' % (type(error).__name__, error)]
    lines = []
    saved = str(config.get('study_book') or '').strip()
    book = logic.study_book(config)
    if book:
        origin = 'study_book' if saved == book['id'] else 'legacy keys, rewritten on next save'
        lines.append('book: %s (%s) via %s' % (book['name'], book['id'], origin))
    else:
        lines.append('*** no book selected — the toolbar and settings will say 未选词书')
    legacy = [key for key in ('review_scope_decks', 'review_scope_tags', 'review_tags_all',
                              'review_scope_name', 'review_book')
              if config.get(key) not in (None, '', [], {}, False)]
    if legacy:
        lines.append('  legacy scope keys still saved: %s (ignored once study_book is set)' % ', '.join(legacy))

    try:
        decks = set(anki_connect('deckNames'))
    except Exception:
        lines.append('  deck/tag existence: not checked (AnkiConnect unavailable)')
        return lines
    capture = str(config.get('deck') or '')
    if capture:
        lines.append('  capture deck %s: %s' % (capture, 'present' if capture in decks else '*** missing'))
    if not book:
        return lines
    if book.get('deck'):
        lines.append('  book deck %s: %s' % (book['deck'], 'present' if book['deck'] in decks else '*** missing'))
    try:
        tags = set(anki_connect('getTags'))
    except Exception:
        lines.append('  book tag: not checked (getTags unavailable)')
        return lines
    if book.get('tag'):
        lines.append('  book tag %s: %s' % (book['tag'], 'present' if book['tag'] in tags else '*** absent from the collection'))
    return lines


# ----------------------------------------------------------- on-screen layer
def desktop_is_visible() -> tuple:
    """BitBlt a few patches of the real screen and see whether anything is drawn.

    The old check looked for LogonUI/LockApp in tasklist, which is a false positive:
    LogonUI keeps running after the session is unlocked, so the panel claimed the screen
    was locked while the user was in the middle of reviewing cards. A locked session
    answers with pure black, so the pixels themselves are the honest signal.
    """
    import ctypes

    gdi32, user32 = ctypes.windll.gdi32, ctypes.windll.user32
    handle = ctypes.c_void_p
    for function in (user32.GetDC, gdi32.CreateCompatibleDC,
                     gdi32.CreateCompatibleBitmap, gdi32.SelectObject):
        function.restype = handle
    for function in (gdi32.BitBlt, gdi32.GetDIBits, gdi32.DeleteObject, gdi32.DeleteDC, user32.ReleaseDC):
        function.restype = ctypes.c_int
    gdi32.BitBlt.argtypes = [handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             handle, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    gdi32.GetDIBits.argtypes = [handle, handle, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_uint]
    gdi32.CreateCompatibleDC.argtypes = [handle]
    gdi32.CreateCompatibleBitmap.argtypes = [handle, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.argtypes = [handle, handle]
    gdi32.DeleteObject.argtypes = [handle]
    gdi32.DeleteDC.argtypes = [handle]
    user32.GetDC.argtypes = [handle]
    user32.ReleaseDC.argtypes = [handle, handle]
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int

    class BitmapInfoHeader(ctypes.Structure):
        _fields_ = [('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_int32), ('biHeight', ctypes.c_int32),
                    ('biPlanes', ctypes.c_uint16), ('biBitCount', ctypes.c_uint16),
                    ('biCompression', ctypes.c_uint32), ('biSizeImage', ctypes.c_uint32),
                    ('biXPelsPerMeter', ctypes.c_int32), ('biYPelsPerMeter', ctypes.c_int32),
                    ('biClrUsed', ctypes.c_uint32), ('biClrImportant', ctypes.c_uint32)]

    side = 120
    screen = user32.GetDC(None)
    if not screen:
        return False, 'no desktop DC'
    width, height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    spots = [(width // 2, height // 2), (width // 4, height // 4), (width // 2, height - side - 8)]
    lit = 0
    try:
        for left, top in spots:
            memory = gdi32.CreateCompatibleDC(screen)
            bitmap = gdi32.CreateCompatibleBitmap(screen, side, side)
            if not memory or not bitmap:
                return False, 'no compatible bitmap'
            try:
                gdi32.SelectObject(memory, bitmap)
                if not gdi32.BitBlt(memory, 0, 0, side, side, screen, left, top, 0x00CC0020):
                    return False, 'BitBlt failed'
                buffer = ctypes.create_string_buffer(side * side * 4)
                info = BitmapInfoHeader(biSize=ctypes.sizeof(BitmapInfoHeader), biWidth=side,
                                        biHeight=-side, biPlanes=1, biBitCount=32)
                if not gdi32.GetDIBits(memory, bitmap, 0, side, buffer, ctypes.byref(info), 0):
                    return False, 'GetDIBits failed'
                raw = buffer.raw
                lit += sum(1 for index in range(0, len(raw), 4) if raw[index:index + 3] != b'\x00\x00\x00')
            finally:
                gdi32.DeleteObject(bitmap)
                gdi32.DeleteDC(memory)
    finally:
        user32.ReleaseDC(None, screen)
    return lit > 100, '%d lit pixels of %d sampled' % (lit, side * side * len(spots))


def layer_onscreen() -> list:
    live, detail = desktop_is_visible()
    if not live:
        return ['SCREEN NOT VISIBLE (%s) — screenshots come back black and SendInput goes nowhere.' % detail,
                'Nothing on the real interface can be accepted until the screen is unlocked.']
    return ['desktop is visible (%s); on-screen acceptance is possible but has not been done by this script' % detail]


# ------------------------------------------------------------------ test layer
def layer_tests() -> list:
    lines = []
    unit = run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py')
    ran = re.search(r'^Ran (\d+) tests?', unit, re.M)
    verdict = 'OK' if re.search(r'^OK$', unit, re.M) else ('FAILED' if 'FAILED' in unit else 'no verdict')
    lines.append('unittest: %s tests, %s' % (ran.group(1) if ran else '?', verdict))
    node = run('node', '--test', 'tests/plugin.test.cjs')
    counts = {}
    for line in node.splitlines():
        match = re.match(r'^(?:#|ℹ)\s*(tests|pass|fail|skipped)\s+(\d+)', line.strip())
        if match:
            counts[match.group(1)] = match.group(2)
    lines.append('node: ' + (' '.join('%s %s' % (key, counts[key]) for key in ('tests', 'pass', 'fail', 'skipped')
                                     if key in counts) if counts else 'no summary'))
    qt = run(sys.executable, 'tests/run-windows-checks.py')
    lines.append('Qt checks: ' + (qt.strip().splitlines()[-1] if qt.strip() else 'no output'))
    return lines


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--tests', action='store_true', help='also run the three suites (slow)')
    args = parser.parse_args()

    layers = [('source', layer_source), ('deployed', layer_deployed), ('loaded', layer_loaded),
              ('config', layer_config), ('on-screen', layer_onscreen)]
    if args.tests:
        layers.insert(1, ('tests', layer_tests))
    for title, collect in layers:
        print('\n== %s ==' % title)
        for line in collect():
            print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
