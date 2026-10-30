"""Add missing community core words without changing existing cards or schedules."""
import html
import json
from pathlib import Path

from .review_logic import clean_text, unambiguous_lemma

DECK = '四六级核心词汇'


def data():
    return json.loads((Path(__file__).parent / 'lexicon' / 'cet_core.json').read_text(encoding='utf-8'))


def import_missing(api, cfg, lookup):
    core = data()
    profile = api('getActiveProfile', {})
    fields = api('modelFieldNames', {'modelName': cfg['model']})
    if cfg['front_field'] not in fields or cfg['back_field'] not in fields:
        raise ValueError('笔记类型缺少所选的单词或释义字段，请检查设置。')
    model = cfg['model'].replace('\\', '\\\\').replace('"', '\\"')
    ids = api('findNotes', {'query': 'note:"%s"' % model}) or []
    existing = set()
    for i in range(0, len(ids), 200):
        for note in api('notesInfo', {'notes': ids[i:i + 200]}) or []:
            raw = (note.get('fields') or {}).get(cfg['front_field'], {}).get('value', '')
            word = clean_text(raw).casefold()
            existing.add(word)
            existing.add(unambiguous_lemma(word).casefold())
    missing = [word for word in core['cet6'] if word not in existing]
    added, failed = 0, []
    deck_ready = False
    for word in missing:
        info = core['dictionary'].get(word)
        if not info:
            try:
                info = lookup(word)
            except Exception:
                info = None
        if not info or not info.get('meaning'):
            failed.append(word)
            continue
        if api('getActiveProfile', {}) != profile:
            raise RuntimeError('Anki 账户已切换，停止导入；此前新增 %d 个词。' % added)
        if not deck_ready:
            api('createDeck', {'deck': DECK})
            deck_ready = True
        values = {cfg['front_field']: html.escape(word), cfg['back_field']: html.escape(info['meaning']).replace('\n', '<br>')}
        if '音标' in fields and info.get('phonetic'):
            values['音标'] = html.escape(info['phonetic'])
        note = {'deckName': DECK, 'modelName': cfg['model'], 'fields': values,
                'options': {'allowDuplicate': False}, 'tags': ['zvr_cet6_core']}
        if word in core['cet4_overlap']:
            note['tags'].append('zvr_cet4_core')
        try:
            if api('addNote', {'note': note}):
                added += 1
            else:
                failed.append(word)
        except Exception:
            failed.append(word)
    return {'existing': len(core['cet6']) - len(missing), 'added': added, 'failed': failed}


def browse_query(cfg):
    field = cfg['front_field'].replace('\\', '\\\\').replace('"', '\\"')
    model = cfg['model'].replace('\\', '\\\\').replace('"', '\\"')
    return 'note:"%s" (%s)' % (model, ' or '.join('"%s:%s"' % (field, w) for w in data()['cet6']))
