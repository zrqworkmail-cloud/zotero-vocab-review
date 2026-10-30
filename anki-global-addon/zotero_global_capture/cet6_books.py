"""CET-6 book membership reuses existing notes and preserves their schedules."""
import html
import json
from pathlib import Path

from .review_logic import clean_text, unambiguous_lemma

ROOT = Path(__file__).parent / 'lexicon'
FULL_TAG = 'zvr_cet6_full'
CORE_TAG = 'zvr_cet6_core'


def books():
    full = json.loads((ROOT / 'cet6_full.json').read_text(encoding='utf-8'))['words']
    core = json.loads((ROOT / 'cet_core.json').read_text(encoding='utf-8'))
    return full, core


def setup_books(api, cfg, lookup=None):
    full, core = books()
    profile = api('getActiveProfile', {})
    fields = api('modelFieldNames', {'modelName': cfg['model']})
    if cfg['front_field'] not in fields or cfg['back_field'] not in fields:
        raise ValueError('笔记类型缺少所选的单词或释义字段。')
    escaped = cfg['model'].replace('\\', '\\\\').replace('"', '\\"')
    ids = api('findNotes', {'query': 'note:"%s"' % escaped}) or []
    existing = {}
    exact = {}
    for i in range(0, len(ids), 200):
        for note in api('notesInfo', {'notes': ids[i:i + 200]}) or []:
            raw = clean_text((note.get('fields') or {}).get(cfg['front_field'], {}).get('value', '')).casefold()
            if raw:
                exact.setdefault(raw, []).append(note)
                existing.setdefault(raw, []).append(note)
                lemma = unambiguous_lemma(raw).casefold()
                if lemma != raw:
                    existing.setdefault(lemma, []).append(note)
    full_rows = {word.casefold(): (word, phonetic, meaning) for word, phonetic, meaning in full if meaning}
    core_words = set(core['cet6'])
    full_words = set(full_rows) | core_words
    targets = {FULL_TAG: full_words, CORE_TAG: core_words}
    counts = {'existing_full': 0, 'existing_core': 0, 'added': 0, 'added_note_ids': [], 'failed': []}

    def check_profile():
        if api('getActiveProfile', {}) != profile:
            raise RuntimeError('Anki 账户已切换，词书整理已停止。')

    for tag, words in targets.items():
        note_ids = set()
        for word in words:
            matches = exact.get(word) or existing.get(word, [])
            if matches:
                counts['existing_full' if tag == FULL_TAG else 'existing_core'] += 1
                note = min(matches, key=lambda item: item['noteId'])
                if tag not in note.get('tags', []):
                    note_ids.add(note['noteId'])
        ids_to_tag = sorted(note_ids)
        for i in range(0, len(ids_to_tag), 200):
            check_profile()
            api('addTags', {'notes': ids_to_tag[i:i + 200], 'tags': tag})

    missing = full_words - set(existing)
    new_notes = []
    for word in sorted(missing):
        row = full_rows.get(word)
        info = core.get('dictionary', {}).get(word, {})
        if row:
            display, phonetic, meaning = row
        else:
            display, phonetic, meaning = word, info.get('phonetic', ''), info.get('meaning', '')
            if not meaning and lookup:
                try:
                    info = lookup(word)
                    phonetic, meaning = info.get('phonetic', ''), info.get('meaning', '')
                except Exception:
                    pass
        if not meaning:
            counts['failed'].append(word)
            continue
        values = {cfg['front_field']: html.escape(display), cfg['back_field']: html.escape(meaning).replace('\n', '<br>')}
        if '音标' in fields and phonetic:
            values['音标'] = html.escape(phonetic)
        tags = [FULL_TAG] + ([CORE_TAG] if word in core_words else [])
        new_notes.append({'deckName': '六级词汇（补充）', 'modelName': cfg['model'], 'fields': values,
                          'options': {'allowDuplicate': False}, 'tags': tags})
    if new_notes:
        check_profile()
        api('createDeck', {'deck': '六级词汇（补充）'})
    for i in range(0, len(new_notes), 50):
        check_profile()
        batch = new_notes[i:i + 50]
        results = api('addNotes', {'notes': batch})
        if not isinstance(results, list) or len(results) != len(batch):
            raise RuntimeError('Anki 未返回完整导入结果；可再次整理以补齐。')
        for note, result in zip(batch, results):
            if result:
                counts['added'] += 1
                counts['added_note_ids'].append(result)
            else:
                counts['failed'].append(note['fields'][cfg['front_field']])
    return counts
