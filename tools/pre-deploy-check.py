"""One gate before deploying the add-on: prove the rollback point is real.

The manual's deploy step has four facts that are easy to assert and hard to prove:
a backup exists, its hashes are intact, the running Anki loaded the files currently
installed, and the collection fingerprint is readable.  This tool checks those four
without writing, restarting, syncing, or opening the collection.

    python tools/pre-deploy-check.py --check    # read-only JSON; exit 0 only if clean
    python tools/pre-deploy-check.py --apply    # create the full rollback snapshot

`--check` never writes.  `--apply` writes exactly one new directory under
deployment-backups/ and a manifest.json inside it; it does not copy files into the
add-on directory and does not restart Anki.  Deployment stays a separate, explicit
step, so "checked" and "deployed" cannot be confused.

Exit codes: 0 = every blocking check passed, 1 = a blocking check failed,
2 = the check could not run at all (bad invocation or unexpected exception).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# Importing review_logic must not leave a __pycache__ behind: --check is read-only.
sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / 'anki-global-addon' / 'zotero_global_capture'
ADDON = 'zotero_global_capture'
LOG_NAME = 'zotero_global_capture_runtime.log'
START_MARKERS = ('desktop review controller initialized', 'hotkey registered')
TEXT_SUFFIXES = {'.py', '.json', '.txt', '.md', '.csv', '.vbs'}
# kyle_enrich.py is source-only on purpose: its exam-material licence is unresolved.
# kyle_books.py is only used by kyle_enrich.py and is excluded from both release archives.
INTENTIONALLY_ABSENT = {'kyle_enrich.py', 'kyle_books.py'}
BACKUP_PREFIX = 'pre-deploy-'


def appdata() -> Path:
    value = os.environ.get('APPDATA')
    return Path(value) if value else Path.home() / 'AppData' / 'Roaming'


def installed_dir() -> Path:
    return appdata() / 'Anki2' / 'addons21' / ADDON


def runtime_log() -> Path:
    temp = os.environ.get('TEMP')
    return Path(temp) / LOG_NAME if temp else Path.home() / 'AppData' / 'Local' / 'Temp' / LOG_NAME


def sha256(path: Path) -> str:
    """Stable hash across git's autocrlf checkout, but never rewrite binary data."""
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def short_hash(path: Path) -> str:
    return sha256(path)[:16]


def run(*cmd: str, timeout: int = 30) -> tuple[int, str]:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=timeout)
        return done.returncode, ((done.stdout or '') + (done.stderr or '')).strip()
    except Exception as error:  # a missing tool is a finding, not a crash
        return 127, '%s: %s' % (type(error).__name__, error)


# ------------------------------------------------------------------ inventories
def source_inventory() -> dict[str, Path]:
    """Every runtime source file, keyed by its path relative to the add-on root."""
    files: dict[str, Path] = {}
    for path in sorted(SRC.rglob('*.py')):
        rel = path.relative_to(SRC)
        if any(part in {'__pycache__', 'user_files'} or part.startswith(BACKUP_PREFIX)
               for part in rel.parts):
            continue
        files[rel.as_posix()] = path
    lexicon = SRC / 'lexicon'
    if lexicon.is_dir():
        for path in sorted(lexicon.rglob('*')):
            if path.is_file():
                files[path.relative_to(SRC).as_posix()] = path
    return files


def installed_inventory() -> dict[str, Path]:
    """The installed mirror of source_inventory(), excluding known source-only files."""
    source = source_inventory()
    return {rel: installed_dir() / rel for rel in source if (installed_dir() / rel).exists()}


def new_source_files(source=None, installed=None) -> list[str]:
    """Files that will be added by the next deployment, excluding source-only files.

    These are recorded in the --apply manifest because a rollback must remove them;
    they cannot be restored from a pre-deploy backup that never contained them.
    """
    source = source_inventory() if source is None else source
    installed = installed_inventory() if installed is None else installed
    return sorted(rel for rel in source if rel not in installed and rel not in INTENTIONALLY_ABSENT)


def installed_code_files() -> list[Path]:
    root = installed_dir()
    if not root.is_dir():
        return []
    files = []
    for path in root.rglob('*.py'):
        rel = path.relative_to(root)
        if any(part in {'__pycache__', 'user_files'} or part.startswith(BACKUP_PREFIX)
               for part in rel.parts):
            continue
        if '.bak-' in path.name or path.name.startswith('.'):
            continue
        files.append(path)
    return sorted(files)


def newest_installed_mtime() -> tuple[float, str]:
    newest = (0.0, '')
    root = installed_dir()
    if not root.is_dir():
        return newest
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if '__pycache__' in rel.parts or any(part.startswith(BACKUP_PREFIX) for part in rel.parts):
            continue
        if '.bak-' in path.name:
            continue
        stamp = path.stat().st_mtime
        if stamp > newest[0]:
            newest = (stamp, rel.as_posix())
    return newest


# ---------------------------------------------------------------------- source
def check_source() -> dict:
    _, branch = run('git', '-C', str(REPO), 'rev-parse', '--abbrev-ref', 'HEAD')
    _, head = run('git', '-C', str(REPO), 'log', '-1', '--oneline')
    _, porcelain = run('git', '-C', str(REPO), 'status', '--porcelain')
    dirty = [line for line in porcelain.splitlines() if line.strip()]
    return {
        'branch': branch,
        'head': head,
        'dirty_count': len(dirty),
        'dirty_paths': dirty[:20],
        'ok': bool(branch and head),
    }


# -------------------------------------------------------------------- deployed
def check_deployed() -> dict:
    source = source_inventory()
    matched, mismatched, absent, excluded = [], [], [], []
    for rel, src in source.items():
        if rel in INTENTIONALLY_ABSENT:
            excluded.append(rel)
            continue
        dst = installed_dir() / rel
        if not dst.exists():
            absent.append(rel)
        elif sha256(src) != sha256(dst):
            mismatched.append({'path': rel, 'source': short_hash(src), 'installed': short_hash(dst)})
        else:
            matched.append(rel)

    source_py = {p.name for p in SRC.glob('*.py')}
    extra = []
    root = installed_dir()
    if root.is_dir():
        for path in sorted(root.glob('*.py')):
            if path.name in source_py or '.bak-' in path.name or path.name.startswith('.'):
                continue
            extra.append(path.name)

    return {
        'installed_dir': str(installed_dir()),
        'source_files': len(source),
        'matched': len(matched),
        'mismatched': mismatched,
        'absent': absent,
        'intentionally_absent': excluded,
        'extra_installed': extra,
        'ok': not mismatched and not absent,
    }


# ---------------------------------------------------------------------- backup
def backup_dirs() -> list[Path]:
    roots = [REPO / 'deployment-backups', installed_dir()]
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if path.is_dir() and path.name.startswith(BACKUP_PREFIX):
                found.append(path)
    return found


def backup_time(path: Path) -> datetime:
    try:
        return datetime.strptime(path.name[len(BACKUP_PREFIX):], '%Y%m%d-%H%M%S')
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime)


def latest_backup() -> Path | None:
    candidates = backup_dirs()
    if not candidates:
        return None
    return max(candidates, key=lambda path: (backup_time(path), path.stat().st_mtime))


def backup_manifest(path: Path) -> dict | None:
    manifest = path / 'manifest.json'
    if not manifest.exists():
        return None
    try:
        return json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def check_backup() -> tuple[dict, dict]:
    """Return (backup facts, rollback readiness); never mutate either directory."""
    path = latest_backup()
    installed = installed_inventory()
    if path is None:
        return ({'path': None, 'ok': False, 'reason': 'no pre-deploy-* directory found'},
                {'ready': False, 'reason': 'no backup to restore from', 'missing_from_backup': sorted(installed)})

    manifest = backup_manifest(path)
    backup_files = [p for p in path.rglob('*') if p.is_file() and p.name != 'manifest.json']
    manifest_errors = []
    if manifest is None:
        manifest_errors.append('manifest.json is missing or unreadable')
    else:
        seen = set()
        for entry in manifest.get('files', []):
            rel = str(entry.get('path') or '')
            seen.add(rel)
            target = path / rel
            if not target.exists():
                manifest_errors.append('manifest entry missing: %s' % rel)
            elif int(entry.get('size', -1)) != target.stat().st_size:
                manifest_errors.append('size differs: %s' % rel)
            elif entry.get('sha256') and entry['sha256'] != sha256(target):
                manifest_errors.append('hash differs: %s' % rel)
        on_disk = {p.relative_to(path).as_posix() for p in backup_files}
        for rel in sorted(on_disk - seen):
            manifest_errors.append('file not listed in manifest: %s' % rel)

    covered = [rel for rel in installed if (path / rel).exists()]
    new_files = sorted({str(rel) for rel in (manifest or {}).get('new_files', [])})
    missing = sorted(set(installed) - set(covered) - set(new_files))
    complete = not missing and bool(installed)
    covered_hash = [rel for rel in covered if sha256(path / rel) == sha256(installed[rel])]
    age_hours = (datetime.now() - backup_time(path)).total_seconds() / 3600.0

    backup = {
        'path': str(path),
        'created_at': backup_time(path).isoformat(timespec='seconds'),
        'age_hours': round(age_hours, 2),
        'files': len(backup_files),
        'manifest': 'manifest.json' if manifest is not None else None,
        'manifest_errors': manifest_errors,
        'complete': complete,
        'installed_files': len(installed),
        'covered_files': len(covered),
        'covered_hash_matches': len(covered_hash),
        'new_files': new_files,
        'missing_from_backup': missing[:40],
        'ok': bool(manifest is not None and not manifest_errors and complete),
    }
    rollback = {
        'ready': backup['ok'],
        'backup': str(path),
        'covered_files': len(covered),
        'installed_files': len(installed),
        'new_files': new_files,
        'missing_from_backup': missing[:40],
        'manifest_sha256': short_hash(path / 'manifest.json') if (path / 'manifest.json').exists() else None,
        'steps': [
            'stop Anki (tray quit protocol; never force-kill while a card is open)',
            'remove files added by this deployment: %s' % (', '.join(new_files) if new_files else '(none)'),
            'restore this backup directory over %s' % installed_dir(),
            'verify every restored file hash against manifest.json',
            'start Anki and run tools/verify-state.py (deployed + loaded layers)',
            'compare collection counts with the baseline; stop on any change',
        ],
    }
    return backup, rollback


def find_baseline_counts() -> dict | None:
    """The newest managed backup that recorded a count fingerprint."""
    for path in sorted(backup_dirs(), key=lambda p: (backup_time(p), p.stat().st_mtime), reverse=True):
        manifest = backup_manifest(path)
        if manifest and isinstance(manifest.get('baseline_counts'), dict):
            return {'backup': str(path), 'counts': manifest['baseline_counts']}
    return None


# ----------------------------------------------------------------------- live
def anki_running() -> bool:
    code, output = run('tasklist', '/FI', 'IMAGENAME eq Anki.exe', '/NH')
    return code == 0 and 'Anki.exe' in output


def anki_connect(action: str, params: dict | None = None, timeout: int = 10):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    body = json.dumps({'action': action, 'version': 6, 'params': params or {}}).encode('utf-8')
    request = urllib.request.Request('http://127.0.0.1:8765', data=body,
                                     headers={'Content-Type': 'application/json'})
    with opener.open(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if payload.get('error'):
        raise RuntimeError(payload['error'])
    return payload['result']


def installed_config() -> dict:
    meta = installed_dir() / 'meta.json'
    try:
        return (json.loads(meta.read_text(encoding='utf-8')).get('config') or {})
    except (OSError, ValueError):
        return {}


def load_review_logic():
    spec = importlib.util.spec_from_file_location('predeploy_review_logic', SRC / 'review_logic.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_scope() -> tuple[str, str, str]:
    cfg = installed_config()
    model = cfg.get('model') or '四六级单词模板'
    try:
        logic = load_review_logic()
        clause = logic.selection_clause(logic.current_entries(cfg))
        label = logic.selection_summary(cfg) or '整库'
        return clause, label, model
    except Exception:
        return '', '整库（词书未解析）', model


def check_counts() -> dict:
    if not anki_running():
        return {'ok': False, 'reason': 'Anki is not running', 'counts': None, 'fingerprint': None}
    try:
        anki_connect('version')
    except Exception as error:
        return {'ok': False, 'reason': 'AnkiConnect unreachable: %s' % type(error).__name__,
                'counts': None, 'fingerprint': None}

    try:
        clause, label, model = live_scope()
        base = 'note:"%s"%s -is:suspended -is:buried' % (model, clause)
        probes = (
            ('book cards', 'findCards', base),
            ('book learned', 'findCards', base + ' prop:reps>0'),
            ('mastered', 'findNotes', 'tag:zvr_mastered'),
            ('total notes', 'findNotes', 'note:"%s"' % model),
        )
        counts = {name: len(anki_connect(action, {'query': query})) for name, action, query in probes}
    except Exception as error:
        return {'ok': False, 'reason': 'count probe failed: %s: %s' % (type(error).__name__, error),
                'counts': None, 'fingerprint': None}

    fingerprint = hashlib.sha256(
        json.dumps(counts, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
    baseline = find_baseline_counts()
    changed = None
    if baseline is not None:
        changed = {key: {'baseline': baseline['counts'].get(key), 'current': value}
                   for key, value in counts.items() if baseline['counts'].get(key) != value}
    return {
        'ok': True,
        'scope': label,
        'counts': counts,
        'fingerprint': fingerprint,
        'baseline': baseline,
        'changed': changed,
    }


def check_loaded() -> dict:
    running = anki_running()
    result = {
        'anki_running': running,
        'ankiconnect': None,
        'addon_start': None,
        'newest_installed': None,
        'newest_installed_path': None,
        'loaded': False,
        'reason': '',
    }
    if not running:
        result['reason'] = 'Anki is not running; loaded layer cannot be verified'
        return result

    try:
        result['ankiconnect'] = anki_connect('version')
    except Exception as error:
        result['reason'] = 'AnkiConnect unreachable: %s' % type(error).__name__
        return result

    log = runtime_log()
    if not log.exists():
        result['reason'] = 'runtime log missing: %s' % log
        return result
    stamps = []
    for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if match and any(marker in line for marker in START_MARKERS):
            stamps.append(datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S'))
    newest_stamp, newest_path = newest_installed_mtime()
    result['newest_installed'] = (datetime.fromtimestamp(newest_stamp).isoformat(timespec='seconds')
                                  if newest_stamp else None)
    result['newest_installed_path'] = newest_path or None
    if not stamps:
        result['reason'] = 'no add-on startup line in the log'
        return result

    result['addon_start'] = stamps[-1].isoformat(timespec='seconds')
    if not newest_stamp:
        result['reason'] = 'installed files unreadable'
        return result
    if stamps[-1].timestamp() + 1 < newest_stamp:
        result['reason'] = ('installed files written %s, add-on last started %s; restart Anki'
                            % (datetime.fromtimestamp(newest_stamp).strftime('%H:%M:%S'),
                               stamps[-1].strftime('%H:%M:%S')))
        return result

    result['loaded'] = True
    result['reason'] = 'add-on started after every installed file'
    return result


# ---------------------------------------------------------------------- apply
def create_backup() -> dict:
    root = installed_dir()
    if not root.is_dir():
        raise SystemExit('installed add-on directory not found: %s' % root)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target = REPO / 'deployment-backups' / (BACKUP_PREFIX + stamp)
    suffix = 1
    while target.exists():
        suffix += 1
        target = REPO / 'deployment-backups' / ('%s%s-%d' % (BACKUP_PREFIX, stamp, suffix))
    target.mkdir(parents=True)

    files = []
    for src in installed_code_files():
        rel = src.relative_to(root)
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        files.append({'path': rel.as_posix(), 'size': dst.stat().st_size, 'sha256': sha256(dst)})
    for name in ('config.json', 'meta.json'):
        src = root / name
        if src.exists():
            dst = target / name
            shutil.copy2(src, dst)
            files.append({'path': name, 'size': dst.stat().st_size, 'sha256': sha256(dst)})
    lexicon = root / 'lexicon'
    if lexicon.is_dir():
        for src in sorted(lexicon.rglob('*')):
            if not src.is_file():
                continue
            rel = src.relative_to(root)
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            files.append({'path': rel.as_posix(), 'size': dst.stat().st_size, 'sha256': sha256(dst)})

    _, head = run('git', '-C', str(REPO), 'log', '-1', '--oneline')
    counts = check_counts()
    new_files = new_source_files()
    manifest = {
        'schema': 1,
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'repo_head': head,
        'source': str(root),
        'excluded': ['__pycache__', '*.bak-*', 'pre-deploy-*', 'user_files'],
        'new_files': new_files,
        'files': files,
        'baseline_counts': counts.get('counts'),
        'baseline_fingerprint': counts.get('fingerprint'),
        'baseline_scope': counts.get('scope'),
    }
    manifest_path = target / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return {
        'mode': 'apply',
        'backup': str(target),
        'files': len(files),
        'manifest': str(manifest_path),
        'manifest_sha256': short_hash(manifest_path),
        'baseline_counts': counts.get('counts'),
        'baseline_fingerprint': counts.get('fingerprint'),
        'ok': True,
    }


# ----------------------------------------------------------------------- main
def check() -> tuple[dict, int]:
    source = check_source()
    deployed = check_deployed()
    backup, rollback = check_backup()
    loaded = check_loaded()
    counts = check_counts()

    problems: list[str] = []
    warnings: list[str] = []

    if not source['ok']:
        problems.append('source layer could not be read (git branch/HEAD missing)')
    if source['dirty_count']:
        warnings.append('%d uncommitted path(s); deploy only what you intend' % source['dirty_count'])
    if not deployed['ok']:
        if deployed['mismatched']:
            problems.append('%d deployed file(s) differ from source' % len(deployed['mismatched']))
        if deployed['absent']:
            problems.append('%d source file(s) absent from the install dir: %s'
                            % (len(deployed['absent']), ', '.join(deployed['absent'])))
    if not backup['ok']:
        if backup['path'] is None:
            problems.append('no rollback backup found')
        elif not backup['complete']:
            problems.append('latest rollback backup is incomplete (%d/%d installed files)'
                            % (backup['covered_files'], backup['installed_files']))
        if backup['manifest_errors']:
            problems.append('backup manifest has %d error(s)' % len(backup['manifest_errors']))
    if not loaded['loaded']:
        problems.append('loaded layer not proven: %s' % loaded['reason'])
    if not counts['ok']:
        problems.append('count fingerprint unavailable: %s' % counts.get('reason'))
    elif counts.get('changed'):
        problems.append('collection counts changed against baseline: %s'
                        % json.dumps(counts['changed'], ensure_ascii=False))
    elif counts.get('baseline') is None:
        warnings.append('no baseline counts in a managed backup; --apply will record one')

    ok = not problems
    payload = {
        'mode': 'check',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'repo': str(REPO),
        'ok': ok,
        'exit_code': 0 if ok else 1,
        'layers': {
            'source': source,
            'deployed': deployed,
            'backup': backup,
            'loaded': loaded,
            'counts': counts,
            'rollback': rollback,
        },
        'problems': problems,
        'warnings': warnings,
    }
    return payload, 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='read-only JSON gate; exit 0 only if clean')
    group.add_argument('--apply', action='store_true', help='create a full rollback snapshot and manifest')
    args = parser.parse_args(argv)

    if args.apply:
        try:
            payload = create_backup()
        except SystemExit:
            raise
        except Exception as error:
            payload = {'mode': 'apply', 'ok': False, 'error': '%s: %s' % (type(error).__name__, error)}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    try:
        payload, code = check()
    except Exception as error:
        payload = {'mode': 'check', 'ok': False, 'exit_code': 2,
                   'error': '%s: %s' % (type(error).__name__, error)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
