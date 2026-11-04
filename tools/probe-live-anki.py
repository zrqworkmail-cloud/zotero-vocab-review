"""One-shot field probe: is the running Anki still able to answer, and what is left to study?

Read-only. Prints how long each call takes, because a reply that arrives only after
several seconds is a different fact from one that never arrives.
"""
import json
import time
import urllib.request

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(action, **params):
    body = json.dumps({'action': action, 'version': 6, 'params': params}).encode()
    request = urllib.request.Request('http://127.0.0.1:8765', data=body,
                                     headers={'Content-Type': 'application/json'})
    started = time.time()
    try:
        with OPENER.open(request, timeout=20) as response:
            payload = json.loads(response.read().decode())
    except Exception as error:
        return '%6.2fs  FAILED %s' % (time.time() - started, type(error).__name__), None
    took = time.time() - started
    if payload.get('error'):
        return '%6.2fs  ERROR %s' % (took, payload['error']), None
    return '%6.2fs' % took, payload.get('result')


for label, action, params in [
    ('version', 'version', {}),
    ('due anywhere', 'findCards', {'query': 'prop:due<=0', 'limit': 500}),
    ('due in book', 'findCards', {'query': 'prop:due<=0 tag:zvr_cet6_core', 'limit': 500}),
    # `prop:isNew` is not a thing in this Anki; the search verb for never-seen cards is `is:new`.
    ('new in book', 'findCards', {'query': 'is:new tag:zvr_cet6_core -is:suspended -is:buried',
                                  'limit': 500}),
    ('book cards', 'findCards', {'query': 'note:"四六级单词模板" tag:zvr_cet6_core '
                                          '-is:suspended -is:buried', 'limit': 10000}),
    ('mastered', 'findNotes', {'query': 'tag:zvr_mastered', 'limit': 10000}),
]:
    took, result = call(action, **params)
    if isinstance(result, list):
        result = '%d ids' % len(result)
    if label == 'deck names':
        continue
    print('%-14s %s  ->  %s' % (label, took, str(result)[:90]))
