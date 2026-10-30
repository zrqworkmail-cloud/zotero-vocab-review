"""Select and grade vocabulary cards through AnkiConnect."""

import html
import ast
import csv
import datetime
import difflib
import gzip
import json
import math
import random
import re
import time
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        elif tag in ('br', 'p', 'div', 'li'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1
        elif tag in ('p', 'div', 'li'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_text(value):
    parser = _Text()
    parser.feed(str(value or ''))
    text = html.unescape(''.join(parser.parts))
    text = re.sub(r'\[sound:[^]]+\]', '', text, flags=re.I)
    text = re.split(r'(?:Zotero 收录次数|全局划词收录次数|Global capture count)\s*[:：]', text, maxsplit=1, flags=re.I)[0]
    return re.sub(r'\s+', ' ', text).strip()


def normalize_meaning_lists(text):
    """Unwrap legacy string representations of lists without touching normal brackets."""
    lines = []
    for line in str(text or '').splitlines():
        item = line.strip()
        if item.startswith(('[\'','["')) and item.endswith(']') and len(item) <= 20000:
            try:
                values = ast.literal_eval(item)
                if isinstance(values, (list, tuple)) and all(isinstance(value, str) for value in values):
                    lines.extend(value.strip() for value in values if value.strip())
                    continue
            except (ValueError, SyntaxError, MemoryError, RecursionError):
                pass
        lines.append(line)
    return '\n'.join(lines)


def clean_detail(value, heading=''):
    parser = _Text()
    parser.feed(str(value or ''))
    text = html.unescape(''.join(parser.parts))
    text = re.sub(r'\[sound:[^]]+\]', '', text, flags=re.I)
    text = re.split(r'(?:Zotero 收录次数|全局划词收录次数|Global capture count)\s*[:：]', text, maxsplit=1, flags=re.I)[0]
    if heading:
        text = re.sub(r'^\s*' + re.escape(heading) + r'\s*[:：]\s*', '', text)
    if heading == '解释':
        text = normalize_meaning_lists(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return '\n'.join(line.strip() for line in text.strip().splitlines()).strip()


def spoken_examples(example, authority, mode):
    sources = {'example': [example], 'authority': [authority], 'all': [example, authority], 'first': [example, authority]}.get(mode, [])
    result = []
    for source in sources:
        for line in source.splitlines():
            if re.match(r'^\s*(?:出处|来源)\s*[:：]', line):
                continue
            line = re.sub(r'^\s*(?:文献例句|权威例句|例句)\s*[:：]\s*', '', line)
            line = re.split(r'——|[\u3400-\u9fff]', line, maxsplit=1)[0].strip(' \t“”"—–')
            if re.search(r'[A-Za-z]', line):
                result.append(line)
                if mode == 'first':
                    return result
    return result


def example_groups(text):
    groups = []
    for paragraph in re.split(r'\n\s*\n', str(text or '').strip()):
        current = []
        for line in paragraph.splitlines():
            line = line.strip()
            if not line:
                continue
            if current and (re.match(r'^[“"\']?[A-Za-z]', line) or re.match(r'^文献例句\s*[:：]', line)):
                groups.append('\n'.join(current))
                current = []
            current.append(re.sub(r'\s+[—–]\s*(?=[\u3400-\u9fff])', '\n', line))
        if current:
            groups.append('\n'.join(current))
    return groups


def literature_example_html(text):
    match = re.match(r'(?s)^\s*(.*?)\s*(——|\n\s*出处\s*[:：])\s*(.+?)\s*$', str(text or ''))
    if not match:
        return None
    quotation, marker, source = match.groups()
    if marker == '——' and not re.search(r'\(\d{4}\)', source):
        return None
    quotation = re.sub(r'^\s*文献例句\s*[:：]\s*', '', quotation)
    source_match = re.match(r'^(.*?\(\d{4}\)\s*[.。]\s*)(.*?)(\s*\(p{1,2}\.[^)]*\))?$', source)
    if source_match and source_match.group(2).strip():
        author, title, pages = source_match.groups()
        source_html = html.escape(author) + '<i>' + html.escape(title) + '</i>' + html.escape(pages or '')
    else:
        source_html = html.escape(source)
    label = '—— ' if marker == '——' else '出处：'
    return '<p style="margin:0; text-indent:28px;">' + html.escape(quotation, quote=False).replace('\n', '<br>') + '<br>' + label + source_html + '</p>'


def link_example_html(safe_html, target, known, style, color="#27344d"):
    known = {word.casefold() for word in known}
    target = str(target or '').casefold()
    pieces = re.split(r'(<[^>]*>|&(?:#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z]+);)', safe_html)
    for index, piece in enumerate(pieces):
        if piece.startswith(('<', '&')):
            continue
        def render(match):
            word = match.group(0)
            key = word.casefold()
            marked = '<b>%s</b>' % word if key == target or (key in known and style == 'bold') else (
                '<u>%s</u>' % word if key in known and style == 'underline' else word)
            return '<a href="zvr:%s" style="color:%s; text-decoration:none">%s</a>' % (word, color, marked)
        pieces[index] = re.sub(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", render, piece)
    return ''.join(pieces)


def format_meaning(text):
    pattern = r'(?<![A-Za-z])(?:adj|adv|conj|prep|pron|interj|aux|art|num|int|det|vt|vi|n|v)\.'
    formatted = re.sub(r'\s*(' + pattern + r')', lambda match: '\n' + match.group(1), normalize_meaning_lists(text), flags=re.I).strip()
    return re.sub(r'(' + pattern + r')(?=[\u3400-\u9fff])', r'\1  ', formatted, flags=re.I)


def meaning_table(text, part_width=30):
    rows = []
    for line in format_meaning(text).splitlines():
        match = re.match(r'^([A-Za-z]+\.)\s*(.*)$', line)
        if match:
            rows.append('<tr><td width="%d" valign="top">%s</td><td>%s</td></tr>' %
                        (part_width, html.escape(match.group(1)), html.escape(match.group(2))))
        else:
            rows.append('<tr><td colspan="2">%s</td></tr>' % html.escape(line))
    return '<table width="100%" cellspacing="0" cellpadding="0">' + ''.join(rows) + '</table>'


def root_detail_html(text):
    lines = [line.strip() for line in str(text or '').splitlines() if line.strip()]
    rows = []
    pending = None
    for line in lines:
        match = re.match(r'^(词根\s*[:：]|(?:adj|adv|n|v|vt|vi|prep|conj)\.)(?:\s*(.*))?$', line, re.I)
        if match:
            if pending:
                rows.append((pending, ''))
            pending = re.sub(r'\s+', '', match.group(1))
            if match.group(2):
                rows.append((pending, match.group(2)))
                pending = None
        else:
            rows.append((pending or '', line))
            pending = None
    if pending:
        rows.append((pending, ''))
    return '<table width="100%" cellspacing="0" cellpadding="0">' + ''.join(
        '<tr><td width="48" valign="top">%s</td><td>%s</td></tr>' % (html.escape(label), html.escape(value))
        for label, value in rows) + '</table>'


def answer_matches(expected, actual):
    normalize = lambda value: re.sub(r'\s+', ' ', str(value or '').strip()).casefold()
    return bool(normalize(expected)) and normalize(expected) == normalize(actual)


def suggested_ease(correct, hints, incorrect_letters, failed_checks=0):
    burden = incorrect_letters + 2 * hints + 2 * failed_checks
    if not correct or hints >= 2 or incorrect_letters >= 4 or failed_checks >= 2 or burden >= 5:
        return 1
    if hints or incorrect_letters >= 2 or failed_checks:
        return 2
    return 3


def spelling_hint(word, revealed=0):
    letters = sum(char.isalpha() for char in word)
    remaining = min(max(0, int(revealed)), max(0, letters - 1))
    result = []
    for char in word:
        if char.isalpha():
            result.append(char if remaining else '_')
            remaining = max(0, remaining - 1)
        else:
            result.append(char)
    return ''.join(result)


def next_hint_index(expected, entered, revealed):
    correct = [bool(value) and value.casefold() == char.casefold()
               for char, value in zip(expected, entered)]
    start = max((i + 1 for i, valid in enumerate(correct) if valid), default=0)
    available = [i for i in range(len(expected)) if not correct[i] and i not in revealed]
    return next((i for i in available if i >= start), next(iter(available), None))


@lru_cache(maxsize=1)
def _inflection_table():
    table = {}
    path = Path(__file__).parent / 'lexicon' / 'inflections.csv.gz'
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as source:
        for row in csv.reader(source):
            if len(row) >= 3:
                forms = table.setdefault(row[0].casefold(), set())
                for field in row[2:]:
                    forms.update(value.casefold() for value in field.split('/') if value)
    return table


@lru_cache(maxsize=1)
def _lemma_table():
    table = {}
    path = Path(__file__).parent / 'lexicon' / 'lemmas.csv.gz'
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as source:
        for row in csv.reader(source):
            if len(row) >= 3:
                table.setdefault(row[0].casefold(), set()).update(
                    value.casefold() for value in row[2].split('/') if value)
    return table


def unambiguous_lemma(word):
    if not re.fullmatch(r'[A-Za-z]+', str(word or '')):
        return word
    lemmas = _lemma_table().get(word.casefold(), set())
    if len(lemmas) == 1:
        lemma = next(iter(lemmas))
        return lemma.capitalize() if word.istitle() else lemma.upper() if word.isupper() else lemma
    return word


def cloze_form(sentence, word):
    if not re.fullmatch(r'[A-Za-z]+(?:[-\'][A-Za-z]+)*', word):
        return None
    forms = {word.casefold()} | _inflection_table().get(word.casefold(), set())
    for match in re.finditer(r"(?<![\w])[A-Za-z]+(?:[-'][A-Za-z]+)*(?![\w])", sentence):
        if match.group().casefold() in forms:
            return match.group()
    return None


def cloze_sentence(sentence, word):
    form = cloze_form(sentence, word)
    if not form:
        return None
    pattern = r'(?<![\w])' + re.escape(form) + r'(?![\w])'
    return re.sub(pattern, lambda match: spelling_hint(match.group(), 0), sentence, flags=re.I)


def masked_example(sentence, word):
    if not re.fullmatch(r'[A-Za-z]+', str(word or '')):
        return cloze_sentence(sentence, word)
    forms = {word.casefold()} | _inflection_table().get(word.casefold(), set())
    found = False
    def mask(match):
        nonlocal found
        if match.group().casefold() in forms:
            found = True
            return spelling_hint(match.group(), 0)
        return match.group()
    result = re.sub(r"(?<![\w])[A-Za-z]+(?:[-'][A-Za-z]+)*(?![\w])", mask, sentence)
    return result if found else None


def mask_answer_clues(text, word, source_form=''):
    """Hide the answer and its inflections in material shown before reveal."""
    forms = set()
    for value in (word, source_form):
        value = str(value or '').casefold()
        if not value:
            continue
        forms.add(value)
        lemma = unambiguous_lemma(value).casefold()
        forms.add(lemma)
        forms.update(_inflection_table().get(lemma, set()))
    if not forms:
        return text
    pattern = r'(?<![A-Za-z])(?:' + '|'.join(re.escape(v) for v in sorted(forms, key=len, reverse=True)) + r')(?![A-Za-z])'
    return re.sub(pattern, lambda m: spelling_hint(m.group(), 0), text, flags=re.I)


def letter_feedback(expected, actual):
    return [(char, i < len(expected) and char.casefold() == expected[i].casefold())
            for i, char in enumerate(actual)]


def should_style_card(deck, model, kind, cfg):
    return (bool(cfg.get('review_beautify', True)) and kind in ('reviewQuestion', 'reviewAnswer') and
            any(deck == name or deck.startswith(name + '::') for name in review_decks(cfg)) and
            model == cfg['model'])


BOOK_TAGS = {'cet6_core': 'zvr_cet6_core', 'cet6_full': 'zvr_cet6_full',
             'cet4_kyle': 'zvr_kyle_cet4', 'cet6_kyle': 'zvr_kyle_cet6'}


def _clean_list(value):
    return [str(item).strip() for item in value if str(item or '').strip()] if isinstance(value, list) else []


def scope_tags(cfg):
    """Tags that narrow the study scope. The old single-select book still resolves."""
    tags = _clean_list(cfg.get('review_scope_tags'))
    if tags:
        return tags
    legacy = BOOK_TAGS.get(cfg.get('review_book'))
    return [legacy] if legacy else []


def scope_decks(cfg):
    """Decks the scope covers. An empty list means every deck that carries the tags."""
    return _clean_list(cfg.get('review_scope_decks'))


def scope_is_all_decks(cfg):
    return not scope_decks(cfg)


def tags_clause(cfg):
    tags = scope_tags(cfg)
    if not tags:
        return ''
    escape = lambda value: str(value).replace('\\', '\\\\').replace('"', '\\"')
    # Anki treats several bare tag: terms as OR; AND has to be written out.
    joiner = ' AND ' if cfg.get('review_tags_all') else ' '
    return ' ' + joiner.join('tag:"%s"' % escape(tag) for tag in tags)


def scope_label(cfg, deck_names=None):
    """A human-readable name for what is being studied, shown on the card."""
    name = str(cfg.get('review_scope_name') or '').strip()
    if name:
        return name
    decks = scope_decks(cfg)
    if deck_names is not None:
        decks = [deck for deck in decks if deck in deck_names]
    tags = [tag[4:] if tag.startswith('zvr_') else tag for tag in scope_tags(cfg)]
    parts = []
    if decks:
        parts.append('、'.join(decks[:2]) + ('' if len(decks) <= 2 else ' 等 %d 个牌组' % len(decks)))
    if tags:
        parts.append('、'.join(tags[:2]) + ('' if len(tags) <= 2 else ' 等 %d 个标签' % len(tags)))
    # Empty when nothing was picked: a placeholder like 所选牌组 on every card is
    # noise, not information. Callers that need a label of their own decide it.
    return ' · '.join(parts)


def _search(cfg, all_decks=False):
    escape = lambda value: str(value).replace('\\', '\\\\').replace('"', '\\"')
    deck = '' if all_decks else 'deck:"%s" ' % escape(cfg['deck'])
    return '%snote:"%s"%s -is:suspended -is:buried' % (deck, escape(cfg['model']), tags_clause(cfg))


def _stats(api, deck):
    values = api('getDeckStats', {'decks': [deck]}) or {}
    result = next((entry for entry in values.values() if entry.get('name') == deck), None)
    if result is None:
        raise ValueError('没有找到复习牌组，请检查设置。')
    return result


def _field(card, name):
    return (card.get('fields') or {}).get(name, {}).get('value', '')


def _eligible(card, cfg):
    deck = card.get('deckName', '')
    return (card.get('modelName') == cfg['model'] and
            card.get('cardId') != cfg.get('_review_exclude_card') and
            card.get('cardId') not in cfg.get('_review_exclude_cards', ()) and
            (deck == cfg['deck'] or deck.startswith(cfg['deck'] + '::')) and
            bool(clean_text(_field(card, cfg['front_field']))) and
            bool(clean_text(_field(card, cfg['back_field']))))


@lru_cache(maxsize=1)
def core_vocabulary():
    data = json.loads((Path(__file__).parent / 'lexicon' / 'cet_core.json').read_text(encoding='utf-8'))
    return frozenset(data['cet6']), frozenset(data['cet4_overlap'])


def is_core_word(word):
    return unambiguous_lemma(word).casefold() in core_vocabulary()[0]


@lru_cache(maxsize=1)
def exam_vocabulary():
    data = json.loads((Path(__file__).parent / 'lexicon' / 'exam_membership.json').read_text(encoding='utf-8'))
    return frozenset(data['cet4']), frozenset(data['cet6'])


def exam_word_labels(word):
    key = unambiguous_lemma(str(word or '')).casefold()
    cet4, cet6 = exam_vocabulary()
    labels = []
    if key in cet4:
        labels.append('四级词表')
    if key in cet6:
        labels.append('六级词表')
    if key in core_vocabulary()[0]:
        labels.append('六级社区核心词')
    return labels


def _weight(card, cfg, captures=None):
    text = _field(card, cfg['back_field'])
    matches = re.findall(r'(?:Zotero 收录次数|全局划词收录次数|Global capture count)\s*[:：]\s*(\d+)', text, re.I)
    local_count = sum(int(value) for value in matches)
    word = clean_text(_field(card, cfg['front_field'])).casefold()
    base = min(2, 1 + max(local_count, (captures or {}).get(word, 0)))
    return base


def _captured_words(api, cfg):
    cache = cfg.get('_capture_lookup_cache')
    now = time.monotonic()
    if cache is not None and now - cache.get('captured_at', 0) < 15 and 'captures' in cache:
        return cache['captures']
    ids = api('findNotes', {'query': 'tag:anki_global_capture or tag:zotero_vocab_review'}) or []
    captures = {}
    for note in api('notesInfo', {'notes': ids}) if ids else []:
        fields = note.get('fields') or {}
        word = clean_text(fields.get(cfg['front_field'], {}).get('value', '')).casefold()
        if not word:
            continue
        text = fields.get(cfg['back_field'], {}).get('value', '')
        counts = re.findall(r'(?:Zotero 收录次数|全局划词收录次数|Global capture count)\s*[:：]\s*(\d+)', text, re.I)
        captures[word] = max(captures.get(word, 0), sum(map(int, counts)), 1)
    if cache is not None:
        cache.clear()
        cache.update(captured_at=now, captures=captures, matching={})
    return captures


def _cards(api, ids, cfg, limit=80):
    if not ids:
        return []
    return [item for item in (api('cardsInfo', {'cards': ids[:limit]}) or []) if _eligible(item, cfg)]


def next_check_delay(now, regular_deadline, smart):
    remaining = max(0, regular_deadline - now)
    return min(300, remaining) if smart else remaining


def validate_windows(windows):
    intervals = []
    for item in windows:
        if not item.get('enabled', True):
            continue
        try:
            start = datetime.time.fromisoformat(item['start'])
            end = datetime.time.fromisoformat(item['end'])
        except (KeyError, ValueError, TypeError):
            return False
        a, b = start.hour * 60 + start.minute, end.hour * 60 + end.minute
        if a >= b:
            return False
        intervals.append((a, b))
    intervals.sort()
    return bool(intervals) and all(intervals[i-1][1] <= intervals[i][0] for i in range(1, len(intervals)))


def window_wait(now, windows):
    """Seconds until the next enabled same-day window, or zero while inside one."""
    if not validate_windows(windows):
        return None
    minute = now.hour * 60 + now.minute + now.second / 60
    intervals = sorted((int(w['start'][:2]) * 60 + int(w['start'][3:5]),
                        int(w['end'][:2]) * 60 + int(w['end'][3:5]))
                       for w in windows if w.get('enabled', True))
    for start, end in intervals:
        if start <= minute < end:
            return 0
        if minute < start:
            return max(1, math.ceil((start - minute) * 60))
    return max(1, math.ceil((1440 - minute + intervals[0][0]) * 60))


def window_minutes(windows):
    if not validate_windows(windows):
        return 0
    return sum((int(w['end'][:2]) * 60 + int(w['end'][3:5])) -
               (int(w['start'][:2]) * 60 + int(w['start'][3:5]))
               for w in windows if w.get('enabled', True))


def remaining_window_minutes(now, windows):
    if not validate_windows(windows):
        return 0
    minute = now.hour * 60 + now.minute + now.second / 60
    return sum(max(0, int(w['end'][:2]) * 60 + int(w['end'][3:5]) -
                   max(minute, int(w['start'][:2]) * 60 + int(w['start'][3:5])))
               for w in windows if w.get('enabled', True))


def study_plan(today, deadline, remaining_new, due, daily_target, done, hours, interval, introduced=0):
    """Estimate today's workload; due cards remain governed by Anki."""
    days = None
    suggested_new = 0
    if deadline:
        days = (datetime.date.fromisoformat(deadline) - today).days + 1
        if days > 0:
            suggested_new = math.ceil((max(0, remaining_new) + max(0, introduced)) / days)
    goal = max(0, int(daily_target)) or (suggested_new + max(0, due) + max(0, done - introduced))
    slots = max(1, math.floor(max(0.25, hours) * 60 / max(1, interval)))
    remaining = max(0, goal - max(0, done))
    new_room = max(0, remaining - max(0, due))
    new_remaining = min(new_room, max(0, suggested_new - max(0, introduced))) if days and days > 0 else min(new_room, max(0, remaining_new))
    return {'days': days, 'new': suggested_new, 'new_remaining': new_remaining, 'due': max(0, due), 'goal': goal,
            'done': max(0, done), 'introduced': max(0, introduced), 'batch': min(10, remaining, max(3, math.ceil(remaining / slots))) if remaining else 0,
            'capacity_shortfall': max(0, remaining - slots * 10)}


def session_batch_size(cfg, plan=None, manual=False):
    if cfg.get('review_plan_mode') == 'daily':
        batch = max(0, min(10, int((plan or {}).get('batch', 0))))
        return batch or (1 if manual else 0)
    return max(1, min(10, int(cfg.get('review_batch_size', 3))))


def updated_session_target(completed, plan):
    return max(completed, min(10, max(0, int(plan.get('batch', 0)))))


def today_remaining(plan):
    return max(0, int(plan['goal']) - int(plan['done']))


def plan_limits_new(cfg):
    """Only the automatic plan may declare today's new words spent.

    A fixed group size is the user's own choice; the deadline-derived daily estimate
    must not silently stop a session after a single card.
    """
    return cfg.get('review_plan_mode') == 'daily'


def end_of_session_reason(plan, limits_new):
    """Say why nothing further can be shown instead of closing the card silently."""
    if limits_new and plan is not None and int(plan.get('new_remaining', 0)) <= 0:
        return ('本组结束：今天的新词计划已完成，剩下的都是到期复习词。' if plan.get('due')
                else '本组结束：今天的新词计划已完成，也没有到期复习词。')
    return '本组结束：已选题型下没有更多可弹出的卡片，可能是牌组当日新词额度已用完。'


def review_decks(cfg):
    scope = scope_decks(cfg)
    if scope:
        return scope
    selected = cfg.get('review_extra_decks')
    if not isinstance(selected, list):
        selected = [cfg.get('review_extra_deck', '')]
    result = [cfg.get('review_main_deck') or cfg['deck']]
    for value in selected:
        name = str(value or '').strip()
        if name and name not in result:
            result.append(name)
    return result


def scope_uses_all_decks(cfg):
    """Tags alone define the scope, so every deck carrying them is searched."""
    return scope_is_all_decks(cfg) and bool(scope_tags(cfg))


def collection_plan(api, cfg, now=None):
    now = now or datetime.datetime.now()
    decks = review_decks(cfg)
    found = {'new': set(), 'due': set(), 'done': set(), 'introduced': set()}
    for deck in ([None] if scope_uses_all_decks(cfg) else decks):
        base = _search(dict(cfg, deck=deck), all_decks=deck is None)
        for key, suffix in (('new', 'is:new'), ('due', 'is:due -is:new'), ('done', 'rated:1'), ('introduced', 'introduced:1')):
            found[key].update(api('findCards', {'query': base + ' ' + suffix}) or [])
    hours = (remaining_window_minutes(now, cfg.get('review_windows', [])) / 60
             if cfg.get('review_windows_enabled') else min(cfg.get('review_computer_hours', 8),
                 max(0, (24 * 60 - now.hour * 60 - now.minute - now.second / 60) / 60)))
    plan = study_plan(now.date(), cfg.get('review_deadline', ''), len(found['new']),
                      len(found['due']), cfg.get('review_daily_goal', 0), len(found['done']),
                      hours, cfg.get('review_interval_minutes', 30), len(found['introduced']))
    plan['new_done'] = len(found['introduced'])
    plan['new_goal'] = plan['new_done'] + plan['new_remaining']
    plan['review_done'] = len(found['done'] - found['introduced'])
    plan['review_remaining'] = len(found['due'] - found['introduced'])
    plan['review_goal'] = plan['review_done'] + plan['review_remaining']
    plan['remaining_new_total'] = len(found['new'])
    return plan


REVIEW_MODES = ('choice', 'reverse', 'typing', 'cloze', 'listening', 'judgment', 'speaking')


def selected_review_modes(cfg, legacy='mixed'):
    modes = cfg.get('review_modes')
    if isinstance(modes, list):
        return list(dict.fromkeys(mode for mode in modes if mode in REVIEW_MODES))
    value = cfg.get('review_mode', legacy)
    return ['choice', 'reverse', 'typing', 'cloze'] if value == 'mixed' else ([value] if value in REVIEW_MODES else ['typing'])


def _parts_of_speech(text):
    return set(re.findall(r'(?<![a-z])(adj|adv|vt|vi|n|v|prep|conj)\.', text.casefold()))


def _gloss_parts(text):
    text = re.sub(r'\([^)]*\)|（[^）]*）', '', format_meaning(text))
    return {part for part in re.findall(r'[\u3400-\u9fff]{2,}', text) if len(part) >= 2}


def _related_words(card):
    return {item.casefold() for item in re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", clean_detail(_field(card, '近义词')))}


def distractor_candidates(target, cards, cfg, mode, rng):
    word = unambiguous_lemma(clean_text(_field(target, cfg['front_field']))).casefold()
    meaning = clean_detail(_field(target, cfg['back_field']), '解释')
    pos, gloss = _parts_of_speech(meaning), _gloss_parts(meaning)
    synonyms = _related_words(target)
    known_forms = {word} | _inflection_table().get(word, set()) if re.fullmatch(r'[A-Za-z]+', word) else {word}
    seen = {meaning.casefold() if mode == 'choice' else word}
    prefixes = {meaning[:30].casefold() if mode == 'choice' else word[:30]}
    ranked = []
    for card in cards:
        candidate_word = unambiguous_lemma(clean_text(_field(card, cfg['front_field']))).casefold()
        candidate_meaning = clean_detail(_field(card, cfg['back_field']), '解释')
        value = candidate_meaning if mode == 'choice' else clean_text(_field(card, cfg['front_field']))
        if not candidate_word or not value or candidate_word in known_forms or candidate_word in synonyms or word in _related_words(card):
            continue
        key, prefix = value.casefold(), value[:30].casefold()
        if key in seen or prefix in prefixes:
            continue
        other_gloss = _gloss_parts(candidate_meaning)
        if any(a in b or b in a for a in gloss for b in other_gloss):
            continue
        other_pos = _parts_of_speech(candidate_meaning)
        pos_score = 2.0 if pos and other_pos and pos & other_pos else 0.0
        if mode == 'reverse':
            similarity = difflib.SequenceMatcher(None, word, candidate_word).ratio()
        else:
            similarity = difflib.SequenceMatcher(None, ''.join(sorted(gloss)), ''.join(sorted(other_gloss))).ratio() if gloss and other_gloss else 0
        score = pos_score + similarity - min(1.0, abs(len(value) - len(meaning if mode == 'choice' else word)) / 60)
        ranked.append((score, rng.random(), value, candidate_word, other_gloss, _related_words(card)))
        seen.add(key)
        prefixes.add(prefix)
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    chosen = []
    for candidate in ranked:
        _, _, value, candidate_word, other_gloss, related = candidate
        if any(candidate_word in previous[5] or previous[3] in related or
               any(a in b or b in a for a in other_gloss for b in previous[4]) for previous in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) == 3:
            break
    return [candidate[2] for candidate in chosen]


def prepare_question(api, cfg, mode='mixed', rng=random, due_only=False):
    profile = api('getActiveProfile', {})
    available = set(api('deckNames', {}) or [])
    if scope_uses_all_decks(cfg):
        decks = [deck for deck in sorted(available)
                 if api('findCards', {'query': _search(dict(cfg, deck=deck))})]
    else:
        decks = [deck for deck in review_decks(cfg) if deck == cfg['deck'] or deck in available]
    deck_cfgs = [dict(cfg, deck=deck) for deck in decks]
    stats_by_deck = [_stats(api, deck) for deck in decks]
    captures = _captured_words(api, cfg)
    card = None
    kind = None
    selected_cfg = None
    recent_fallback = None
    excluded_words = set(cfg.get('_review_exclude_words', ()))
    recent_words = set(cfg.get('_review_recent_words', ()))
    for label, suffix in (('due', 'is:due'), ('new', 'is:new')):
        if label == 'new' and due_only:
            break
        candidates = []
        for deck_cfg, stats in zip(deck_cfgs, stats_by_deck):
            allowed = (int(stats.get('learn_count', 0)) + int(stats.get('review_count', 0)) if label == 'due'
                       else int(stats.get('new_count', 0)))
            if not allowed:
                continue
            query = _search(deck_cfg) + ' ' + suffix
            ids = api('findCards', {'query': query}) or []
            tagged = set(api('findCards', {'query': query + ' (tag:anki_global_capture or tag:zotero_vocab_review)'}) or [])
            if captures and deck_cfg['deck'] != cfg['deck']:
                cache = cfg.get('_capture_lookup_cache')
                matches = cache.get('matching', {}).get(query) if cache is not None else None
                if matches is None:
                    words = rng.sample(list(captures), min(100, len(captures)))
                    field = cfg['front_field'].replace('\\', '\\\\').replace('"', '\\"')
                    actions = [{'action': 'findCards', 'params': {'query': query + ' "' + field + ':' + word.replace('\\', '\\\\').replace('"', '\\"') + '"'}} for word in words]
                    matches = {cid for matching in api('multi', {'actions': actions}) or [] for cid in (matching or [])}
                    if cache is not None:
                        cache.setdefault('matching', {})[query] = matches
                tagged.update(matches)
            preferred = [cid for cid in ids if cid in tagged]
            preferred_set = set(preferred)
            others = [cid for cid in ids if cid not in preferred_set]
            sample = rng.sample(preferred, min(80, len(preferred))) + rng.sample(others, min(80, len(others)))
            candidates.extend((item, deck_cfg) for item in _cards(api, sample, deck_cfg, limit=160))
        candidates = [(item, deck_cfg) for item, deck_cfg in candidates if
                      unambiguous_lemma(clean_text(_field(item, deck_cfg['front_field']))).casefold() not in excluded_words]
        if candidates and selected_review_modes(cfg, mode) == ['cloze']:
            candidates = [(item, deck_cfg) for item, deck_cfg in candidates if any(
                cloze_sentence(clean_detail(_field(item, name)), unambiguous_lemma(clean_text(_field(item, deck_cfg['front_field']))))
                for name in ('例句', '权威例句'))]
        if candidates:
            unique = {}
            for item, deck_cfg in candidates:
                previous = unique.get(item['cardId'])
                if previous is None or len(deck_cfg['deck']) > len(previous[1]['deck']):
                    unique[item['cardId']] = (item, deck_cfg)
            candidates = list(unique.values())
            fresh = [(item, deck_cfg) for item, deck_cfg in candidates if
                     unambiguous_lemma(clean_text(_field(item, deck_cfg['front_field']))).casefold() not in recent_words]
            if not fresh:
                if recent_fallback is None:
                    recent_fallback = (candidates, label)
                continue
            core = [(item, deck_cfg) for item, deck_cfg in fresh if cfg.get('review_core_enabled', False) and
                    is_core_word(clean_text(_field(item, deck_cfg['front_field'])))]
            eligible = core or fresh
            card, selected_cfg = rng.choices(eligible, weights=[_weight(item, deck_cfg, captures) for item, deck_cfg in eligible], k=1)[0]
            kind = label
            break
    if card is None and recent_fallback and not due_only:
        candidates, kind = recent_fallback
        card, selected_cfg = rng.choices(candidates, weights=[_weight(item, deck_cfg, captures) for item, deck_cfg in candidates], k=1)[0]
    if card is None:
        return None

    cfg = selected_cfg
    base = _search(cfg)
    source_form = clean_text(_field(card, cfg['front_field']))
    word = unambiguous_lemma(source_form)
    meaning = clean_detail(_field(card, cfg['back_field']), '解释')
    example = clean_detail(_field(card, '例句'), '例句')
    literature = clean_detail(_field(card, '权威例句'), '权威例句')
    sentence = next((value for value in (example, literature) if cloze_sentence(value, word)), '')
    modes = selected_review_modes(cfg, mode)
    modes = [candidate for candidate in modes if candidate != 'cloze' or sentence]
    if not modes and 'review_modes' not in cfg:
        modes = ['typing']
    options = []
    judgment_statement = ''
    judgment_correct = None
    while modes:
        mode = rng.choice(modes)
        modes.remove(mode)
        if mode not in ('choice', 'reverse', 'judgment'):
            break
        ids = api('findCards', {'query': base}) or []
        others = [cid for cid in ids if cid != card['cardId']]
        sampled = rng.sample(others, min(160, len(others)))
        if mode == 'reverse' and re.fullmatch(r'[A-Za-z]{4,30}', word):
            field = cfg['front_field'].replace('\\', '\\\\').replace('"', '\\"')
            prefix_query = base + ' "' + field + ':' + word[:3] + '*"'
            similar_ids = [cid for cid in (api('findCards', {'query': prefix_query}) or []) if cid != card['cardId']]
            sampled = rng.sample(similar_ids, min(60, len(similar_ids))) + sampled
        sampled = list(dict.fromkeys(sampled))
        candidates = _cards(api, sampled, cfg, limit=220)
        distractors = distractor_candidates(card, candidates, cfg, 'reverse' if mode == 'reverse' else 'choice', rng)
        if mode == 'choice':
            seen = {mask_answer_clues(meaning, word, source_form).casefold()}
            unique_distractors = []
            for candidate in distractors:
                visible = mask_answer_clues(candidate, word, source_form).casefold()
                if visible not in seen:
                    seen.add(visible)
                    unique_distractors.append(candidate)
            distractors = unique_distractors
        if mode == 'judgment' and distractors:
            judgment_correct = bool(rng.randrange(2))
            judgment_statement = meaning if judgment_correct else distractors[0]
            options = ['正确', '错误']
            break
        if mode != 'judgment' and len(distractors) >= 3:
            options = [meaning if mode == 'choice' else word] + distractors
            rng.shuffle(options)
            break
    else:
        if 'review_modes' in cfg:
            return None
        mode = 'typing'

    return {
        'profile': profile, 'card_id': card['cardId'], 'review_deck': cfg['deck'], 'kind': kind, 'mode': mode, 'word': word,
        'meaning': meaning, 'options': options, 'source_form': source_form,
        'judgment_statement': judgment_statement, 'judgment_correct': judgment_correct,
        'answer_form': cloze_form(sentence, word) if mode == 'cloze' else word,
        'phonetic': clean_text(_field(card, '音标')),
        'roots': clean_detail(_field(card, '词根')),
        'mnemonic': clean_detail(_field(card, '识记方法')),
        'synonyms': clean_detail(_field(card, '近义词')),
        'distinctions': clean_detail(_field(card, '词语辨析') or _field(card, '辨析')),
        'similar_words': clean_detail(_field(card, '形近词')),
        'antonyms': clean_detail(_field(card, '反义词')),
        'example': example,
        'literature': literature,
        'cloze': cloze_sentence(sentence, word) if sentence else '',
        'snapshot': {key: card.get(key) for key in ('queue', 'due', 'reps', 'mod')},
    }


def submit_review(api, cfg, question, ease, answer=None):
    if ease not in (1, 2, 3, 4):
        raise ValueError('无效的复习评分。')
    if api('getActiveProfile', {}) != question['profile']:
        raise ValueError('Anki 账户已切换，这张卡片不会被评分。')
    deck = question.get('review_deck', cfg['deck'])
    if not scope_uses_all_decks(cfg) and deck not in review_decks(cfg):
        raise ValueError('复习牌组已改变，请在下次提醒时复习。')
    cfg = dict(cfg, deck=deck)
    current = api('cardsInfo', {'cards': [question['card_id']]}) or []
    if not current or any(current[0].get(key) != value for key, value in question['snapshot'].items()):
        raise ValueError('这张卡片已发生变化，请在下次提醒时复习。')
    suffix = 'is:new' if question['kind'] == 'new' else 'is:due'
    query = _search(cfg) + ' cid:%s %s' % (question['card_id'], suffix)
    if question['card_id'] not in (api('findCards', {'query': query}) or []):
        raise ValueError('这张卡片已不在当前待复习队列中。')
    stats = _stats(api, cfg['deck'])
    remaining = (stats.get('new_count', 0) if question['kind'] == 'new' else
                 int(stats.get('learn_count', 0)) + int(stats.get('review_count', 0)))
    if int(remaining) <= 0:
        raise ValueError('这个牌组今天的复习额度已用完。')
    result = (answer(question, ease) if answer else
              api('answerCards', {'answers': [{'cardId': question['card_id'], 'ease': ease}]}))
    if result != [True]:
        raise ValueError('Anki 没有确认保存评分，请检查 Anki 后再试。')
