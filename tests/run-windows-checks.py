"""Run every Windows/Qt offscreen UI check in this folder and report one summary.

The tests/windows-*.py scripts need the PyQt6 build that ships with the local Anki
install, so they cannot run in GitHub's ubuntu CI. Without this entry point they
rot silently (one of them had been importing a class that no longer exists).

Usage:  python tests/run-windows-checks.py [name-substring ...]
Exit code is non-zero when any check fails.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv):
    scripts = sorted(p for p in HERE.glob('windows-*.py'))
    if argv:
        scripts = [p for p in scripts if any(term in p.name for term in argv)]
    if not scripts:
        print('no matching windows-*.py checks')
        return 1
    failures = []
    for script in scripts:
        try:
            result = subprocess.run([sys.executable, str(script)], cwd=str(HERE.parent),
                                    capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=300)
        except subprocess.TimeoutExpired:
            failures.append((script.name, 'timed out after 300s'))
            print('FAIL  %-34s timed out' % script.name)
            continue
        tail = (result.stdout or result.stderr or '').strip().splitlines()
        last = tail[-1] if tail else ''
        if result.returncode == 0:
            print('PASS  %-34s %s' % (script.name, last))
        else:
            failures.append((script.name, last or 'exit %d' % result.returncode))
            print('FAIL  %-34s exit %d' % (script.name, result.returncode))
            for line in tail[-8:]:
                print('        %s' % line)
    print('\n%d/%d checks passed' % (len(scripts) - len(failures), len(scripts)))
    for name, detail in failures:
        print('  %s: %s' % (name, detail))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main(sys.argv[1:]))
