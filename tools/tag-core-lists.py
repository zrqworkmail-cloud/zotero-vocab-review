"""Tag the bundled core lists onto notes that already exist.

Additive only: it appends one tag per note and never edits a field, a deck, or a
review record, so undoing it is `removeTags` with the same journal. It mirrors
cet6_books.setup_books, which is the path that already applied 4803 tags, including
the per-word single-note pick and the profile guard.

    python tag_core_lists.py            # dry run, prints what would change
    python tag_core_lists.py --apply    # writes
"""
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

LEXICON = (Path(__file__).resolve().parents[1]
           / 'anki-global-addon' / 'zotero_global_capture' / 'lexicon' / 'cet_core.json')
JOURNAL = Path(__file__).with_name('core-tag-journal.json')
FIELD = '正面'
MODEL = '四六级单词模板'
TARGETS = {
    'zvr_cet6_core': 'cet6',
    'zvr_cet4_core': 'cet4_overlap',
}


def call(action, params=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    body = json.dumps({'action': action, 'version': 6, 'params': params or {}}).encode('utf-8')
    request = urllib.request.Request('http://127.0.0.1:8765', data=body,
                                     headers={'Content-Type': 'application/json'})
    with opener.open(request, timeout=120) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if payload.get('error'):
        raise RuntimeError('%s: %s' % (action, payload['error']))
    return payload['result']


def notes_for(words):
    """word -> the single oldest note carrying it, so a duplicated word is not tagged twice."""
    found = {}
    for start in range(0, len(words), 60):
        batch = words[start:start + 60]
        query = 'note:"%s" ' % MODEL + ' OR '.join('%s:"%s"' % (FIELD, word) for word in batch)
        ids = call('findNotes', {'query': query})
        for chunk in range(0, len(ids), 200):
            for note in call('notesInfo', {'notes': ids[chunk:chunk + 200]}):
                word = str(list(note['fields'].values())[0]['value']).strip().lower()
                if word in set(batch):
                    current = found.get(word)
                    if current is None or note['noteId'] < current['nid']:
                        found[word] = {'nid': note['noteId'], 'tags': note.get('tags', [])}
    return found


def main():
    apply = '--apply' in sys.argv
    profile = call('getActiveProfile')
    print('profile: %s — mode: %s' % (profile, 'APPLY' if apply else 'dry run'))
    data = json.loads(LEXICON.read_text(encoding='utf-8'))
    plan, journal = {}, {'profile': profile, 'at': datetime.now().isoformat(timespec='seconds'), 'added': {}}

    for tag, key in TARGETS.items():
        words = sorted({str(word).strip().lower() for word in data[key] if str(word).strip()})
        found = notes_for(words)
        to_tag = sorted(note['nid'] for word, note in found.items() if tag not in note['tags'])
        already = len(found) - len(to_tag)
        plan[tag] = to_tag
        journal['added'][tag] = to_tag
        print('%-16s list %3d words | %3d notes found | %3d already tagged | %3d to add | %d words missing'
              % (tag, len(words), len(found), already, len(to_tag), len(words) - len(found)))

    if not apply:
        print('\ndry run only; pass --apply to write. Nothing changed.')
        return
    for tag, ids in plan.items():
        for start in range(0, len(ids), 200):
            if call('getActiveProfile') != profile:
                raise SystemExit('profile changed mid-run; stopping. See %s' % JOURNAL)
            call('addTags', {'notes': ids[start:start + 200], 'tags': tag})
        print('tagged %d notes with %s' % (len(ids), tag))
    JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=1), encoding='utf-8')
    print('journal written to %s' % JOURNAL)
    for tag in TARGETS:
        print('  verify %-16s -> %d notes now' % (tag, len(call('findNotes', {'query': 'tag:%s' % tag}))))


if __name__ == '__main__':
    main()
