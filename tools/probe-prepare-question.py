"""Measure prepare_question against the live Anki collection, read-only.

The card that follows a rating is chosen by `prepare_question`. Reading a card used to take
dozens of AnkiConnect round trips, and the learner sees that time as a pause after pressing a
rating button. This probe counts the round trips and the wall time on the *live* collection,
so a change to the batching can be judged by the same number the learner feels.

    python tools/probe-prepare-question.py --runs 8
    python tools/probe-prepare-question.py --runs 8 --warm-captures
    python tools/probe-prepare-question.py --book cet6_full --mode mixed

Only AnkiConnect reads are allowed here (findCards/cardsInfo/getDeckStats/deckNames/
getActiveProfile/findNotes/notesInfo). A write action raises instead of silently changing the
learner's schedule.

The config is the add-on's own live meta.json; `_review_inflight_*`, `_review_group` and the
exclusions are set the way `_flip` sets them for the card after a rating.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import statistics
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / 'anki-global-addon' / 'zotero_global_capture' / 'review_logic.py'
READ_ACTIONS = {
    'getActiveProfile', 'deckNames', 'getDeckStats', 'findCards', 'cardsInfo',
    'findNotes', 'notesInfo', 'getTags', 'multi',
}


def load_logic():
    spec = importlib.util.spec_from_file_location('review_logic_probe', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_config(path: Path):
    data = json.loads(path.read_text(encoding='utf-8'))
    return dict(data.get('config') or data)


class Counter:
    """An AnkiConnect client that records how many HTTP requests and actions it paid for."""

    def __init__(self):
        self.calls = 0
        self.actions = 0
        self.history = []
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def raw(self, action, params):
        body = json.dumps({'action': action, 'version': 6, 'params': params or {}}).encode()
        request = urllib.request.Request('http://127.0.0.1:8765', data=body,
                                         headers={'Content-Type': 'application/json'})
        with self._opener.open(request, timeout=60) as response:
            return json.loads(response.read().decode('utf-8'))

    def __call__(self, action, params=None):
        if action not in READ_ACTIONS:
            raise AssertionError('probe is read-only, refusing %s' % action)
        started = time.monotonic()
        answer = self.raw(action, params or {})
        elapsed = time.monotonic() - started
        if answer.get('error'):
            raise RuntimeError('%s: %s' % (action, answer['error']))
        self.calls += 1
        self.actions += len(params['actions']) if action == 'multi' else 1
        self.history.append((action, elapsed, params or {}))
        return answer.get('result')

    def reset(self):
        self.calls = 0
        self.actions = 0
        self.history = []


def one_run(logic, api, base_cfg, mode, seed, warm_captures):
    cfg = dict(base_cfg)
    cfg['_capture_lookup_cache'] = warm_captures if warm_captures is not None else {}
    api.reset()
    started = time.monotonic()
    question = logic.prepare_question(api, cfg, mode, random.Random(seed))
    elapsed = time.monotonic() - started
    return elapsed, api.calls, api.actions, question, list(api.history)


def describe(rows):
    times = [row[0] for row in rows]
    calls = [row[1] for row in rows]
    actions = [row[2] for row in rows]
    print('runs: %d' % len(rows))
    print('round trips  median %.1f  min %d  max %d' % (statistics.median(calls), min(calls), max(calls)))
    print('actions      median %.1f  min %d  max %d' % (statistics.median(actions), min(actions), max(actions)))
    print('elapsed ms   median %.0f  min %.0f  max %.0f' % (
        statistics.median(times) * 1000, min(times) * 1000, max(times) * 1000))
    if len(times) >= 2:
        ordered = sorted(times)
        p90 = ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))]
        print('elapsed p90  %.0f ms' % (p90 * 1000))
    print('per-run      ' + ', '.join('%d calls/%d acts/%.0f ms' % (
        row[1], row[2], row[0] * 1000) for row in rows))
    if rows:
        counts = {}
        for name, _elapsed, _params in rows[-1][4]:
            counts[name] = counts.get(name, 0) + 1
        print('last run     ' + ', '.join('%s=%d' % item for item in sorted(counts.items())))
        print('--- last run, call by call ---')
        for name, elapsed, params in rows[-1][4]:
            detail = ''
            if name == 'multi':
                subs = {}
                for sub in params.get('actions') or []:
                    subs[sub.get('action')] = subs.get(sub.get('action'), 0) + 1
                detail = ' [' + ', '.join('%s x%d' % item for item in sorted(subs.items())) + ']'
            print('  %-16s %6.0f ms%s' % (name, elapsed * 1000, detail))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--runs', type=int, default=8)
    parser.add_argument('--seed', type=int, default=20261112)
    parser.add_argument('--book', default=None, help='override study_book')
    parser.add_argument('--mode', default='mixed')
    parser.add_argument('--due-inflight', action='store_true',
                        help='pretend the rated card was a due card instead of a new one')
    parser.add_argument('--group-size', type=int, default=10)
    parser.add_argument('--warm-captures', action='store_true',
                        help='reuse one capture cache for every run (what a session sees)')
    parser.add_argument('--config', default=str(Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
                                                 / 'Anki2' / 'addons21' / 'zotero_global_capture' / 'meta.json'))
    args = parser.parse_args(argv)

    logic = load_logic()
    api = Counter()
    config = live_config(Path(args.config))
    if args.book:
        config['study_book'] = args.book
    config.setdefault('review_batch_size', 10)

    # Anchor the measurement in the live queue instead of an invented card id: the exclusions
    # are the ones a real rating writes, so the same queries and the same candidate pools run.
    ids = api('findCards', {'query': logic._search(dict(config, deck=config['deck'])) + ' is:new'}) or []
    if not ids:
        ids = api('findCards', {'query': 'is:new'}) or []
    anchor = ids[0] if ids else None
    print('collection: %s' % api('getActiveProfile', {}))
    print('book: %s  deck names: %d  anchor card: %s' % (
        config.get('study_book'), len(api('deckNames', {}) or []), anchor))

    base = dict(config)
    base['_review_exclude_cards'] = {anchor} if anchor else set()
    base['_review_exclude_words'] = set()
    base['_review_recent_words'] = set()
    base['_review_group'] = (0, args.group_size)
    base['_review_inflight_new'] = 0 if args.due_inflight else 1
    base['_review_inflight_due'] = 1 if args.due_inflight else 0
    warm = {} if args.warm_captures else None

    rows = []
    for index in range(args.runs):
        row = one_run(logic, api, base, args.mode, args.seed + index, warm)
        rows.append(row)
        print('run %d: %.0f ms, %d round trips, %d actions%s' % (
            index + 1, row[0] * 1000, row[1], row[2],
            '' if row[3] else '  (no question)'))
    describe(rows)
    return 0


if __name__ == '__main__':
    sys.exit(main())
