"""Import locally supplied KyleBing books without replacing existing notes."""
import json
from pathlib import Path

from .domain.models import NoteDraft
from .review_logic import clean_text
from .vocabulary import add_notes, note_values

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


def new_draft(entry, cfg, fields):
    content = entry['content']
    meaning = '\n'.join((str(t.get('pos', '')).strip() + '. ' if t.get('pos') else '') + str(t.get('tranCn', '')).strip()
                        for t in content.get('trans', []) if t.get('tranCn'))
    if not meaning:
        return None
    optional = {}
    if '音标' in fields:
        optional['音标'] = content.get('ukphone') or content.get('usphone') or content.get('phone') or ''
    if '例句' in fields:
        examples = content.get('sentence', {}).get('sentences', [])
        optional['例句'] = '\n'.join(
            str(s.get('sContent', '')) + ('\n' + str(s['sCn']) if s.get('sCn') else '')
            for s in examples if s.get('sContent'))
    if '近义词' in fields:
        synos = content.get('syno', {}).get('synos', [])
        optional['近义词'] = ', '.join(dict.fromkeys(
            w['w'] for s in synos for w in s.get('hwds', []) if w.get('w')))
    return NoteDraft(front=entry['word'], back=meaning, fields=optional,
                     tags=tuple(sorted(entry.get('tags', ()))),
                     deck='四六级词汇（KyleBing补充）', model=cfg.get('model', ''),
                     source='kyle')


def new_fields(entry, cfg, fields):
    """Compatibility wrapper for callers that still need the escaped field map."""
    draft = new_draft(entry, cfg, fields)
    return note_values(draft, cfg, fields) if draft is not None else None


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
    drafts = []
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
            draft = new_draft(entry, cfg, fields)
            if draft is None:
                result['failed'].append(entry['word'])
                continue
            drafts.append(draft)
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
        if drafts:
            check()
            api('createDeck', {'deck': '四六级词汇（KyleBing补充）'})
        for i in range(0, len(drafts), 50):
            check()
            batch = drafts[i:i + 50]
            ids = add_notes(api, batch, cfg, fields)
            if not isinstance(ids, list) or len(ids) != len(batch):
                raise RuntimeError('Anki 未返回完整导入结果，请检查后重试。')
            log.write(json.dumps({'action': 'addNotes', 'ids': [x for x in ids if x]}, ensure_ascii=False) + '\n'); log.flush()
            for draft, nid in zip(batch, ids):
                if nid:
                    result['added'] += 1
                else:
                    result['failed'].append(draft.front)
    return result
