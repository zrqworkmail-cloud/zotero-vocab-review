"""Fill blank vocabulary fields from the locally supplied KyleBing data."""
import html
import json
from pathlib import Path
from . import kyle_books, morphology
from .review_logic import clean_detail, clean_text


def source_entries(directory):
    result = {}
    for filename in ('四级-完整.jsonl', '六级-完整.jsonl'):
        with (Path(directory) / filename).open(encoding='utf-8') as stream:
            for line in stream:
                item = json.loads(line)
                word = item['headWord'].strip()
                result.setdefault(word.casefold(), []).append(item['content']['word']['content'])
    return result


def additions(word, contents, fields):
    """Return candidates only; callers decide whether existing fields are blank."""
    encode = lambda text: html.escape(str(text)).replace('\n', '<br>')
    values = {}
    for content in contents:
        if not values.get('音标'):
            value = content.get('ukphone') or content.get('usphone') or content.get('phone')
            if value: values['音标'] = encode(value)
        if not values.get('近义词'):
            synos = content.get('syno', {}).get('synos', [])
            words = list(dict.fromkeys(w['w'] for s in synos for w in s.get('hwds', []) if w.get('w')))
            if words: values['近义词'] = encode(', '.join(words))
        if not values.get('例句'):
            examples = content.get('sentence', {}).get('sentences', [])
            lines = [encode(s.get('sContent', '')) + ('<br>' + encode(s['sCn']) if s.get('sCn') else '') for s in examples if s.get('sContent')]
            if lines: values['例句'] = '<br><br>'.join(lines)
        if not values.get('权威例句'):
            lines = []
            for s in content.get('realExamSentence', {}).get('sentences', []):
                info = s.get('sourceInfo') or {}
                if not s.get('sContent') or not info.get('year') or not info.get('level'):
                    continue
                source = ' '.join(str(info.get(k, '')).strip() for k in ('level', 'year', 'paper', 'type')).strip()
                lines.append(encode(s['sContent']) + '<br>来源：' + encode(source))
            if lines: values['权威例句'] = '<br><br>'.join(lines)
    root = morphology.breakdown(word)
    if root: values['词根'] = encode(root)
    return {k:v for k,v in values.items() if k in fields and v}


def planned_updates(notes, sources, front_field, imported_ids=(), back_field='解释'):
    imported_ids = set(imported_ids)
    updates = []
    for note in notes:
        fields = note.get('fields', {})
        word = clean_text(fields.get(front_field, {}).get('value', '')).strip()
        contents = sources.get(word.casefold())
        if not contents: continue
        candidates = additions(word, contents, fields)
        values = {k:v for k,v in candidates.items() if not clean_text(fields[k].get('value', '')).strip()}
        if note['noteId'] in imported_ids and back_field in fields:
            current = fields[back_field].get('value', '')
            original = kyle_books.new_fields({'word': word, 'content': contents[0]},
                                             {'front_field': front_field, 'back_field': back_field}, fields)
            if original and clean_detail(current) == clean_detail(original.get(back_field, '')):
                existing = {line.strip().casefold() for line in clean_detail(current).splitlines() if line.strip()}
                extra = []
                for content in contents:
                    for item in content.get('trans', []):
                        meaning = str(item.get('tranCn', '')).strip()
                        pos = str(item.get('pos', '')).strip()
                        line = (pos + '. ' if pos else '') + meaning
                        if meaning and line.casefold() not in existing:
                            extra.append(html.escape(line))
                            existing.add(line.casefold())
                if extra:
                    values[back_field] = current + '<br>' + '<br>'.join(extra)
        if values:
            updates.append({'id': note['noteId'], 'fields': values,
                            'before': {k:fields[k].get('value', '') for k in values}})
    return updates
