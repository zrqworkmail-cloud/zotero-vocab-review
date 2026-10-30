"""Import locally supplied KyleBing books without replacing existing notes."""
import html
import json
from pathlib import Path

from .review_logic import clean_text

BOOKS = {'cet4_kyle': ('四级-完整.jsonl', 'zvr_kyle_cet4'),
         'cet6_kyle': ('六级-完整.jsonl', 'zvr_kyle_cet6')}


def read_books(directory):
    entries = {}
    for filename, tag in BOOKS.values():
        with (Path(directory) / filename).open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                word = row['headWord'].strip()
                key = word.casefold()
                if not key:
                    continue
                content = row['content']['word']['content']
                entry = entries.setdefault(key, {'word': word, 'content': content, 'tags': set()})
                entry['tags'].add(tag)
    return entries


def new_fields(entry, cfg, fields):
    content = entry['content']
    meaning = '\n'.join((str(t.get('pos', '')).strip() + '. ' if t.get('pos') else '') + str(t.get('tranCn', '')).strip()
                        for t in content.get('trans', []) if t.get('tranCn'))
    if not meaning:
        return None
    encode = lambda x: html.escape(str(x)).replace('\n', '<br>')
    values = {cfg['front_field']: encode(entry['word']), cfg['back_field']: encode(meaning)}
    if '音标' in fields:
        values['音标'] = encode(content.get('ukphone') or content.get('usphone') or content.get('phone') or '')
    if '例句' in fields:
        examples = content.get('sentence', {}).get('sentences', [])
        values['例句'] = '<br>'.join(encode(s.get('sContent', '')) + ('<br>' + encode(s['sCn']) if s.get('sCn') else '')
                                    for s in examples if s.get('sContent'))
    if '近义词' in fields:
        synos = content.get('syno', {}).get('synos', [])
        values['近义词'] = encode(', '.join(dict.fromkeys(w['w'] for s in synos for w in s.get('hwds', []) if w.get('w'))))
    return values


def import_books(api, cfg, directory, journal):
    entries = read_books(directory)
    profile = api('getActiveProfile', {})
    fields = api('modelFieldNames', {'modelName': cfg['model']})
    if cfg['front_field'] not in fields or cfg['back_field'] not in fields:
        raise ValueError('笔记类型缺少单词或释义字段。')
    escaped = cfg['model'].replace('\\', '\\\\').replace('"', '\\"')
    ids = api('findNotes', {'query': 'note:"%s"' % escaped}) or []
    existing = {}
    for i in range(0, len(ids), 200):
        for note in api('notesInfo', {'notes': ids[i:i + 200]}) or []:
            key = clean_text((note.get('fields') or {}).get(cfg['front_field'], {}).get('value', '')).strip().casefold()
            if key:
                existing.setdefault(key, []).append(note)
    to_tag = {tag: [] for _, tag in BOOKS.values()}
    new = []
    result = {'unique': len(entries), 'reused': 0, 'added': 0, 'failed': [], 'tagged': {tag: 0 for tag in to_tag}}
    def check():
        if api('getActiveProfile', {}) != profile:
            raise RuntimeError('Anki 账户已切换，导入已停止。')
    for key, entry in entries.items():
        if key in existing:
            note = min(existing[key], key=lambda item: item['noteId'])
            result['reused'] += 1
            for tag in entry['tags']:
                if tag not in note.get('tags', []):
                    to_tag[tag].append(note)
        else:
            values = new_fields(entry, cfg, fields)
            if values is None:
                result['failed'].append(entry['word'])
                continue
            new.append({'deckName': '四六级词汇（KyleBing补充）', 'modelName': cfg['model'], 'fields': values,
                        'options': {'allowDuplicate': False}, 'tags': sorted(entry['tags'])})
    journal = Path(journal)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open('a', encoding='utf-8') as log:
        for tag, notes in to_tag.items():
            for i in range(0, len(notes), 200):
                check()
                batch = notes[i:i + 200]
                log.write(json.dumps({'action': 'addTags', 'tag': tag, 'notes': [{'id': n['noteId'], 'tags': n.get('tags', [])} for n in batch]}, ensure_ascii=False) + '\n'); log.flush()
                api('addTags', {'notes': [n['noteId'] for n in batch], 'tags': tag})
                result['tagged'][tag] += len(batch)
        if new:
            check()
            api('createDeck', {'deck': '四六级词汇（KyleBing补充）'})
        for i in range(0, len(new), 50):
            check()
            batch = new[i:i + 50]
            ids = api('addNotes', {'notes': batch})
            if not isinstance(ids, list) or len(ids) != len(batch):
                raise RuntimeError('Anki 未返回完整导入结果，请检查后重试。')
            log.write(json.dumps({'action': 'addNotes', 'ids': [x for x in ids if x]}, ensure_ascii=False) + '\n'); log.flush()
            for note, nid in zip(batch, ids):
                if nid:
                    result['added'] += 1
                else:
                    result['failed'].append(note['fields'][cfg['front_field']])
    return result
