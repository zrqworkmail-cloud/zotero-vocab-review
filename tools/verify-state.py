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


def run(*cmd: str) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=30)
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
    source_files = sorted(SRC.glob('*.py'))
    lines, drifted, absent = [], [], []
    for path in source_files:
        other = target / path.name
        if not other.exists():
            absent.append(path.name)
        elif sha256(path) != sha256(other):
            drifted.append(path.name)
    extra = sorted(p.name for p in target.glob('*.py') if p.name not in {p.name for p in source_files})
    lines.append('%d of %d files match the install dir' % (len(source_files) - len(drifted) - len(absent), len(source_files)))
    for name in drifted:
        lines.append('  DRIFT  %s (branch and installed differ)' % name)
    for name in absent:
        lines.append('  ABSENT %s (never deployed)' % name)
    for name in extra:
        lines.append('  EXTRA  %s (installed only)' % name)
    newest = max((p.stat().st_mtime for p in target.glob('*.py')), default=0)
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
    newest = max((datetime.fromtimestamp(p.stat().st_mtime) for p in target.glob('*.py')), default=None)
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
def layer_config() -> list:
    meta = installed_dir() / 'meta.json'
    if not meta.exists():
        return ['no meta.json']
    config = json.loads(meta.read_text(encoding='utf-8')).get('config', {})
    lines = []
    scope = [key for key in ('review_scope_decks', 'review_scope_tags', 'review_tags_all', 'review_scope_name')
             if key in config]
    lines.append('scope keys saved: %s' % (', '.join(scope) if scope else
                                           'none — using the legacy deck/book path'))
    if config.get('review_book'):
        lines.append('  legacy review_book=%r still set (read as its tag, rewritten on next save)' % config['review_book'])

    decks = None
    try:
        decks = set(anki_connect('deckNames'))
    except Exception:
        pass
    if decks is None:
        lines.append('  deck existence: not checked (AnkiConnect unavailable)')
        return lines
    wanted = list(config.get('review_scope_decks') or [])
    if not wanted:
        wanted = [config.get('review_main_deck') or config.get('deck')] + list(config.get('review_extra_decks') or [])
    missing = sorted({name for name in wanted if name and name not in decks})
    if missing:
        lines.append('  *** %d configured deck(s) do not exist in this account: %s' % (len(missing), '、'.join(missing)))
        lines.append('  *** half the daily plan is counting an empty scope; open Settings and clear them')
    else:
        lines.append('  every configured deck exists in the account')
    try:
        known = set(anki_connect('getTags'))
    except Exception:
        known = set()
    tags = [tag for tag in re.findall(r'zvr_\w+', json.dumps(config)) if known and tag not in known]
    if tags:
        lines.append('  *** tags referenced but absent from the collection: %s' % '、'.join(sorted(set(tags))))
    return lines


# ----------------------------------------------------------- on-screen layer
def layer_onscreen() -> list:
    out = run('tasklist', '/FI', 'IMAGENAME eq LogonUI.exe', '/NH') + run('tasklist', '/FI', 'IMAGENAME eq LockApp.exe', '/NH')
    if 'LogonUI.exe' in out or 'LockApp.exe' in out:
        return ['SESSION LOCKED — screenshots come back black and SendInput goes nowhere.',
                'Nothing on the real interface can be accepted until the screen is unlocked.']
    return ['desktop appears unlocked; on-screen acceptance is possible but has not been done by this script']


# ------------------------------------------------------------------ test layer
def layer_tests() -> list:
    lines = []
    unit = run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py')
    lines.append('unittest: ' + (unit.strip().splitlines()[-1] if unit.strip() else 'no output'))
    node = run('node', '--test', 'tests/plugin.test.cjs')
    summary = [line for line in node.splitlines() if line.startswith('# ')]
    lines.append('node: ' + (' '.join(s.replace('# ', '') for s in summary) if summary else 'no summary'))
    qt = run(sys.executable, 'tests/run-windows-checks.py')
    lines.append('Qt checks: ' + (qt.strip().splitlines()[-1] if qt.strip() else 'no output'))
    return lines


def main() -> int:
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
