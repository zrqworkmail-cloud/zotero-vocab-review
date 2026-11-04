"""Why does the dashboard say 今日建议新词 0? Print every input the planner uses.

Read-only: findCards / getDeckStats / deckNames only. The plan is computed by the shipped
`review_logic.collection_plan`, so this answers with the same arithmetic the panel uses.
"""
import importlib.util
import json
import os
import sys
import urllib.request

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'anki-global-addon', 'zotero_global_capture')
sys.path.insert(0, SRC)
spec = importlib.util.spec_from_file_location('review_logic_probe', os.path.join(SRC, 'review_logic.py'))
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(action, params=None):
    body = json.dumps({'action': action, 'version': 6, 'params': params or {}}).encode()
    request = urllib.request.Request('http://127.0.0.1:8765', data=body,
                                     headers={'Content-Type': 'application/json'})
    with OPENER.open(request, timeout=25) as response:
        payload = json.loads(response.read().decode())
    if payload.get('error'):
        raise RuntimeError(payload['error'])
    return payload['result']


meta = json.load(open(os.path.join(os.environ['APPDATA'], 'Anki2', 'addons21',
                                   'zotero_global_capture', 'meta.json'), encoding='utf-8'))
cfg = dict(meta['config'])
cfg['_book_decks_key'] = None

book = logic.study_book(cfg)
print('book            :', book.get('id'), book.get('name'))
print('deck setting    :', repr(cfg.get('deck')), ' model:', repr(cfg.get('model')))
print('deadline        :', cfg.get('review_deadline'), ' daily_goal:', cfg.get('review_daily_goal'),
      ' plan_mode:', cfg.get('review_plan_mode'), ' interval:', cfg.get('review_interval_minutes'))
print('windows enabled :', cfg.get('review_windows_enabled'))
decks = logic.resolve_book_decks(api, cfg)
print('decks in scope  :', decks)
for deck in decks:
    base = logic._search(dict(cfg, deck=deck))
    counts = {key: len(api('findCards', {'query': base + ' ' + suffix}) or [])
              for key, suffix in (('new', 'is:new'), ('due', 'is:due -is:new'),
                                  ('done', 'rated:1'), ('introduced', 'introduced:1'))}
    try:
        stats = logic._stats(api, deck)
        print('  %-28s %s  deckStats new/learn/review=%s/%s/%s' % (
            deck, counts, stats.get('new_count'), stats.get('learn_count'), stats.get('review_count')))
    except Exception as error:
        print('  %-28s %s  deckStats failed: %s' % (deck, counts, type(error).__name__))

plan = logic.collection_plan(api, cfg)
print()
for key in sorted(plan):
    print('  %-22s %s' % (key, plan[key]))
print()
print('book_availability (new, due) =', logic.book_availability(api, cfg))
print('suggested_new - introduced   =', plan['new'] - plan['introduced'])
