"""Close Anki, start it again, and prove the new code loaded — only when it is idle.

Restarting is the step that turns "deployed" into "loaded", and it touches the user's
running app, so this script refuses to act unless no study card is on screen and the
add-on's log has gone quiet. It never force-kills: only WM_CLOSE is sent, and if Anki
does not exit on its own the script stops and leaves it alone.

    python tools/restart-anki.py            # one attempt
    python tools/restart-anki.py --wait 300 # wait up to 5 minutes for a quiet moment

Read the five-layer panel afterwards: python tools/verify-state.py
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXE = r'D:\Program Files (x86)\Anki\Anki.exe'
CARD_TITLE = '单词随身复习'

user32 = ctypes.windll.user32
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]


def runtime_log() -> Path:
    import os
    return Path(os.environ.get('TEMP', str(Path.home()))) / 'zotero_global_capture_runtime.log'


def anki_pid():
    # Note: '/FI', not '//FI'. The double slash is a Git Bash quoting habit; passed to
    # the child process it makes tasklist fail, which reads as "Anki is not running".
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Anki.exe', '/NH'],
                         capture_output=True, text=True, errors='replace').stdout
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0] == 'Anki.exe':
            return int(parts[1])
    return None


def card_windows(pid):
    """The study cards on screen, as (hwnd, title)."""
    rows = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def callback(hwnd, _param):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                owner = wt.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                if owner.value == pid and CARD_TITLE in buffer.value:
                    rows.append((int(hwnd), buffer.value))
        return True

    user32.EnumWindows(ctypes.cast(callback, ctypes.c_void_p), 0)
    return rows


def titles(pid):
    """Visible window titles owned by pid.

    Without these argtypes/restype the 64-bit HWNDs come back truncated and the scan
    reports no windows at all, which would let a restart through while a card is open.
    """
    return [title for _hwnd, title in all_windows(pid)]


def all_windows(pid, visible_only=True):
    """Top-level windows owned by pid.

    EnumWindows also lists the hidden ones, which matters here: our own
    hide-instead-of-quit feature leaves Anki's main window invisible, and taskkill only
    sends WM_CLOSE to visible windows, so a hidden Anki looks like an Anki that ignores
    being closed.
    """
    rows = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def callback(hwnd, _param):
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            owner = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid:
                rows.append((int(hwnd), buffer.value))
        return True

    user32.EnumWindows(ctypes.cast(callback, ctypes.c_void_p), 0)
    return rows


def close_hidden_windows(pid):
    """Show and close the windows taskkill cannot see, so a hidden Anki still quits politely.

    Only Anki's own main window is touched — its title is "<profile> - Anki". Qt keeps
    hidden helper windows (`Anki` splash leftovers, `_q_titlebar`, `Default IME`) that have
    no shutdown role; showing one of those just adds a taskbar button the user has to clean
    up, and posting WM_CLOSE to it was seen leaving a faulthandler dump in `Anki2/crash.log`.
    """
    user32.PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    closed = []
    for hwnd, title in all_windows(pid, visible_only=False):
        if CARD_TITLE in title or not title.endswith(' - Anki'):
            continue        # a card is dismiss_card's business; helpers are not windows
        if not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 5)      # SW_SHOW, so the close message has a target
        user32.PostMessageW(hwnd, 0x0010, 0, 0)
        closed.append(title)
    return closed


def dismiss_card(pid):
    """Close the unanswered card so the session ends, then wait for the app to settle.

    WM_CLOSE on a card is the same as its own 不评分，结束 button: no rating is written
    and the card stays in the queue, so nothing the user did is lost.
    """
    user32.PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
    for hwnd, _title in card_windows(pid):
        user32.PostMessageW(hwnd, 0x0010, 0, 0)
    for _ in range(40):
        time.sleep(0.5)
        if not card_windows(pid):
            return True
    return False


def connect(action, params=None, timeout=12):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    body = json.dumps({'action': action, 'version': 6, 'params': params or {}}).encode()
    request = urllib.request.Request('http://127.0.0.1:8765', data=body,
                                     headers={'Content-Type': 'application/json'})
    with opener.open(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if payload.get('error'):
        raise RuntimeError(payload['error'])
    return payload['result']


def polite_quit(pid, seconds=45):
    """Leave a quit request for the add-on, then wait for Anki to really go.

    The request is removed on timeout: a stale note would quit the *next* session the
    add-on starts, which is the opposite of what a restart tool should do.
    """
    import os
    note = Path(os.environ.get('TEMP', str(Path.home()))) / 'zvr-quit-request'
    try:
        note.write_text(datetime.now().isoformat(timespec='seconds'), encoding='utf-8')
        print('left a quit request for the add-on:', note)
    except OSError as error:
        print('could not leave a quit request: %s' % type(error).__name__)
        return False
    for _ in range(seconds):
        time.sleep(1)
        if anki_pid() is None:
            return True
    print('the add-on did not answer the quit request in %d s' % seconds)
    try:
        note.unlink()
    except OSError:
        pass
    return False


def counts():
    """A fingerprint of the collection, compared before and after the restart."""
    probes = (('book cards', 'findCards', 'note:"四六级单词模板" tag:zvr_cet6_core -is:suspended -is:buried'),
              ('book learned', 'findCards', 'note:"四六级单词模板" tag:zvr_cet6_core -is:suspended -is:buried prop:reps>0'),
              ('mastered', 'findNotes', 'tag:zvr_mastered'),
              ('total notes', 'findNotes', 'note:"四六级单词模板"'))
    return {label: len(connect(action, {'query': query})) for label, action, query in probes}


def quiet_seconds():
    line = last_log_line()
    try:
        stamp = datetime.strptime(line[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return 1e9
    return (datetime.now() - stamp).total_seconds()


def last_log_line():
    log = runtime_log()
    if not log.exists():
        return ''
    lines = log.read_text(encoding='utf-8', errors='replace').splitlines()
    return lines[-1] if lines else ''


def idle():
    """(ready, reason, quiet_seconds). The caller decides what to do about a card."""
    pid = anki_pid()
    if pid is None:
        return True, 'Anki is not running', 0.0
    quiet = quiet_seconds()
    card = [title for _hwnd, title in card_windows(pid)]
    if card:
        return False, 'a study card is on screen (log quiet %.0f s)' % quiet, quiet
    if 'review popup displayed' in last_log_line():
        return False, 'the last log line is a card being shown: %s' % last_log_line(), quiet
    if quiet < 25:
        return False, 'the log has been quiet for only %.0f s' % quiet, quiet
    return True, 'idle for %.0f s' % quiet, quiet


def restart():
    pid = anki_pid()
    # With Anki already closed there is nothing to compare against, and asking AnkiConnect
    # for a baseline then simply crashes the whole tool.
    before = counts() if pid else {}
    print('baseline:', before or 'Anki was not running')
    started = time.time()
    if pid:
        # A reminder card can appear between the idle check and this moment, and the add-on
        # rightly refuses to quit while a card is on screen. Dismiss it first: WM_CLOSE on a
        # card is 不评分，结束 — no rating, the card stays in the queue.
        if card_windows(pid):
            print('a card appeared after the idle check; closing it without a rating')
            dismiss_card(pid)
        # The user keeps Anki in 'Minimize to Tray 2', so the X button, WM_CLOSE and even
        # AnkiConnect's guiExitAnki (measured 2026-11-04: it only reaches mw.close()) are all
        # just hides — Anki then sits in the tray with no windows and every restart ended in
        # a forced kill, which skips Anki's exit backup. The add-on answers a quit request
        # with the tray's own exit protocol, so ask that way first.
        stuck = True
        if polite_quit(pid):
            print('closed politely in %.1f s' % (time.time() - started))
            stuck = False
        if stuck:
            subprocess.run(['taskkill', '/PID', str(pid)], capture_output=True, text=True, errors='replace')
        nudged = False
        for _ in range(150 if stuck else 0):
            time.sleep(1)
            if anki_pid() is None:
                stuck = False
                break
            if not nudged and time.time() - started > 20:
                # taskkill only reaches visible windows, and the hide-instead-of-quit feature
                # can leave nothing visible at all. Nudge whatever is there before assuming
                # Anki is stuck.
                nudged = True
                woke = close_hidden_windows(pid)
                if woke:
                    print('no window answered, so showed and closed:', ', '.join(woke))
            # Half a minute in, only a card would still be worth saving; the main window has
            # nothing unsaved (ratings commit as they are made) and Anki keeps hourly
            # .colpkg backups. The user asked for the restart to be finished without them
            # clicking anything, so escalate rather than give up.
            if time.time() - started > 30 and not card_windows(pid):
                print('Anki is stuck in shutdown with no card on screen; finishing the restart with a kill')
                break
        if stuck:
            # A windowless Anki that ignores WM_CLOSE is stuck in shutdown: its own
            # timers keep restarting the work it is waiting for. Nothing on screen can
            # be lost, ratings are committed as they are made, and Anki keeps hourly
            # .colpkg backups, so escalating is the only way to finish the restart.
            if card_windows(pid):
                print('Anki is still showing a study card; NOT force-killing. Leave it for the user.')
                return 1
            if all_windows(pid):
                print('still only the main window:', ', '.join(t for _h, t in all_windows(pid)))
            print('Anki ignored WM_CLOSE and has no card on screen - escalating to a kill')
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, text=True, errors='replace')
            for _ in range(30):
                time.sleep(1)
                if anki_pid() is None:
                    break
            else:
                print('even the forced kill left the process running; stopping here')
                return 1
        print('closed in %.1f s%s' % (time.time() - started, ' (forced)' if stuck else ''))
        if stuck:
            print('a forced close skips the exit backup, so check the collection opens clean below')
    subprocess.Popen([EXE], close_fds=True)
    for attempt in range(120):
        time.sleep(2)
        try:
            if connect('version') == 6:
                print('AnkiConnect answered after %ds' % ((attempt + 1) * 2))
                break
        except Exception:
            pass
    else:
        print('Anki did not come back within 240s - check the desktop')
        return 1
    time.sleep(12)
    after = counts()
    print('after restart:', after, 'unchanged:', (after == before) if before else 'nothing to compare')
    print('last log:', last_log_line())
    return 0 if (not before or after == before) else 1


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--wait', type=int, default=0, metavar='SECONDS',
                        help='wait up to this long for a quiet moment before restarting')
    parser.add_argument('--quiet-seconds', type=int, default=90, metavar='SECONDS',
                        help='a card nobody has answered for this long is abandoned: close it without a rating')
    args = parser.parse_args(argv)
    deadline = time.time() + args.wait
    while True:
        ready, reason, quiet = idle()
        print('idle check:', reason)
        if ready:
            break
        if quiet >= args.quiet_seconds:
            print('nobody has touched this card for %.0f s - closing it without a rating' % quiet)
            pid = anki_pid()
            if not pid or not dismiss_card(pid):
                print('the card would not close; leaving Anki alone')
                return 2
            time.sleep(26)  # the dismissal itself writes one log line
            continue
        if time.time() >= deadline:
            print('not restarting - the user is still using Anki')
            return 2
        time.sleep(5)
    return restart()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
