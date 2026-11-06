"""What Anki itself says about one word's history, through AnkiConnect only.

`getCard` is not an action this AnkiConnect build answers for, and the collection file stays
locked while Anki is saving ratings, but the search grammar exposes the same column:
`prop:reps=n` filters on how many times a card has ever been answered. So the probe walks the
reps buckets for one word and reports where it lands -- that is the difference between "never
studied" and "seen exactly once, yesterday evening" -- then counts the whole due pile the
same way.

Read-only: findCards, getIntervals, areDue, suspended, getEaseFactors. No writes.
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(action, **params):
    body = json.dumps({'action': action, 'version': 6, 'params': params}).encode()
    request = urllib.request.Request('http://127.0.0.1:8765', data=body,
                                     headers={'Content-Type': 'application/json'})
    with OPENER.open(request, timeout=25) as response:
        payload = json.loads(response.read().decode())
    if payload.get('error'):
        raise SystemExit('%s failed: %s' % (action, payload['error']))
    return payload['result']


def ids_of(query):
    return call('findCards', query=query, limit=20000)


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else 'jeopardize'
    book = sys.argv[2] if len(sys.argv) > 2 else 'tag:zvr_cet6_full'
    # The word lives in whatever field the plug-in is configured to read (正面 on this
    # machine), so asking Anki is the only way to keep this probe honest after a rename.
    import os
    cfg = json.load(open(os.path.expandvars(
        r'%APPDATA%\Anki2\addons21\zotero_global_capture\meta.json'), encoding='utf-8'))
    cfg = cfg.get('config', cfg)
    field = cfg.get('front_field', '正面')
    print('front field from the deployed config: %r  deck: %r' % (field, cfg.get('deck')))
    base = '"%s:%s" %s' % (field, word, book)
    found = ids_of(base)
    print('%s -> %d card(s) in the book: %s' % (word, len(found), found))
    if not found:
        print('  (no exact %s match; the word may only appear inside another note)' % field)
        return
    print('  intervals   %s' % call('getIntervals', cards=found))
    print('  areDue      %s' % call('areDue', cards=found))
    print('  suspended   %s' % [call('suspended', card=int(card_id)) for card_id in found])
    print('  ease        %s' % call('getEaseFactors', cards=found))
    for reps in range(0, 6):
        if ids_of('%s prop:reps=%d' % (base, reps)):
            print('  reps=%d  <- this card has been answered %d time(s)' % (reps, reps))
    print('  is:new=%d  is:due=%d  is:learn=%d' % (
        len(ids_of('%s is:new' % base)), len(ids_of('%s is:due' % base)),
        len(ids_of('%s is:learn' % base))))

    due = ids_of('%s is:due -is:suspended' % book)
    never = ids_of('%s is:due -is:suspended prop:reps=0' % book)
    once = ids_of('%s is:due -is:suspended prop:reps=1' % book)
    twice = ids_of('%s is:due -is:suspended prop:reps=2' % book)
    print('\nbook due pile: %d cards' % len(due))
    print('  reps=0 never answered : %d' % len(never))
    print('  reps=1 seen once      : %d' % len(once))
    print('  reps=2 seen twice     : %d' % len(twice))
    print('  reps>=3               : %d' % (len(due) - len(never) - len(once) - len(twice)))


main()
