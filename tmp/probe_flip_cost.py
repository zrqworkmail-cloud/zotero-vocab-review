"""Read-only: time one flip's worth of reads (plan + prepare + progress) against live Anki.

Mirrors DesktopReviewController._next_result in fixed mode with a deadline: one fresh cfg,
collection_plan -> prepare_question -> book_progress. Nothing is answered or written.
Run from the worktree root:  python tmp/probe_flip_cost.py
"""
import collections
import importlib.util
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'review_logic_probe', ROOT / 'anki-global-addon' / 'zotero_global_capture' / 'review_logic.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

ADDON = Path('C:/Users/Admin/AppData/Roaming/Anki2/addons21/zotero_global_capture')


def api(action, params=None, timeout=15):
    body = json.dumps({'action': action, 'version': 6, 'params': params or {}}).encode()
    request = urllib.request.Request('http://127.0.0.1:8765', body,
                                     {'Content-Type': 'application/json'}, method='POST')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        value = json.loads(response.read().decode('utf-8'))
    if value.get('error'):
        raise RuntimeError(value['error'])
    return value.get('result')


def main():
    cfg = dict(json.loads((ADDON / 'meta.json').read_text(encoding='utf-8')).get('config', {}))
    cfg.update(json.loads((ADDON / 'config.json').read_text(encoding='utf-8')))
    cfg['_capture_lookup_cache'] = {}
    calls = []

    def counted(action, params=None):
        calls.append(action)
        return api(action, params)

    marks = []
    t0 = time.monotonic()
    plan = logic.collection_plan(counted, cfg)
    marks.append(('collection_plan', time.monotonic() - t0, len(calls)))
    t1 = time.monotonic()
    question = logic.prepare_question(counted, cfg, cfg.get('review_mode', 'mixed'))
    marks.append(('prepare_question', time.monotonic() - t1, len(calls)))
    t2 = time.monotonic()
    view = logic.entry_view(cfg, (question or {}).get('_selection_index')) or cfg
    progress = logic.book_progress(counted, view)
    marks.append(('book_progress', time.monotonic() - t2, len(calls)))

    previous = 0
    for name, seconds, total in marks:
        print('%-18s %6.0f ms   (%d calls, +%d)' % (name, seconds * 1000, total, total - previous))
        previous = total
    print('%-18s %6.0f ms   (%d round trips)' % ('TOTAL', sum(m[1] for m in marks) * 1000, len(calls)))
    print('actions:', dict(collections.Counter(calls)))
    print('plan: new_remaining=%s due=%s goal=%s available=%s/%s' % (
        plan.get('new_remaining'), plan.get('due'), plan.get('goal'),
        plan.get('available_new'), plan.get('available_due')))
    print('progress (learned/total):', progress)
    print('question:', (question or {}).get('word'), (question or {}).get('mode'), (question or {}).get('kind'))


if __name__ == '__main__':
    main()