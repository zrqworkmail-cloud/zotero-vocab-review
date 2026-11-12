"""Salvage verified syllable divisions from the failed verification agent's transcript.

The agent (agent-ageneral-purpose-de7b52e260f811b9) died on an API error after
verifying part of the 37 words. Its tool results are still in the jsonl; this
script finds dotted headword tokens (con·sul·tan·cy etc.) whose plain letters
equal a target word, and prints the surrounding evidence so each division can
be attributed to a real page capture instead of the agent's prose alone.
"""
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
PATH = Path(r'C:\Users\Admin\.qoder\projects\C--Users-Admin-Documents-Qoder-2026-10-31-317372ba'
            r'\317372ba-b501-456f-ba0a-c29c4c5f0185\subagents\agent-ageneral-purpose-de7b52e260f811b9.jsonl')

DOT = '(?:\u00b7|\u2022|&#183;|&middot;|\\\\u00b7)\u200b?'
TOKEN = re.compile('[A-Za-z]+(?:' + DOT + '[A-Za-z]+)+')

blobs = []
for line in PATH.open(encoding='utf-8'):
    try:
        obj = json.loads(line)
    except Exception:
        continue
    # The full tool output lives in the top-level toolUseResult field; the
    # message.content tool_result part can be a truncated copy.
    if 'toolUseResult' in obj:
        blobs.append(json.dumps(obj['toolUseResult'], ensure_ascii=False))
    content = (obj.get('message') or {}).get('content')
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get('type') == 'tool_result':
                c = part.get('content')
                if isinstance(c, list):
                    c = ' '.join(p.get('text', '') for p in c if isinstance(p, dict))
                blobs.append(str(c))

targets = ['consultancy', 'corresponding', 'dishonour', 'disillusioned', 'endeavour',
           'honourable', 'hypotheses', 'inasmuch', 'interconnect', 'lifestyle',
           'microcomputer', 'normalization', 'nutritional', 'partially', 'pessimistic',
           'predominantly', 'previously', 'prioritize', 'projecting', 'realization',
           'relatively', 'reliability', 'seemingly', 'seminate', 'shipbuilding',
           'sightseeing', 'sorrowful', 'specifically', 'stillness', 'strangler',
           'strongly', 'sufficiently', 'systematically', 'technological', 'violation',
           'violently', 'workplace']
for word in targets:
    found = {}
    for blob in blobs:
        # In the JSON-dumped text a newline is the two characters \n; left as
        # is, its 'n' glues onto the next headword ('ncon·sul·tan·cy').
        blob = blob.replace('\\n', ' ').replace('\\t', ' ')
        for m in TOKEN.finditer(blob):
            tok = m.group(0)
            plain = re.sub(DOT, '', tok).lower()
            if plain == word:
                start = max(0, m.start() - 120)
                context = blob[start:m.end() + 120].replace('\n', ' ')
                url = re.search(r'URL: (https?://[^\\\s"]+)', blob)
                found.setdefault(re.sub(DOT, '', tok), (tok, context, url.group(1) if url else '?'))
    print('== %s ==' % word)
    if not found:
        print('  NO DOTTED TOKEN IN TOOL RESULTS')
    for plain, (tok, context, url) in list(found.items())[:2]:
        print('  token: %s   source: %s' % (tok, url))
    print()