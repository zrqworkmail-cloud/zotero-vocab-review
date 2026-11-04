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


QUIT_REQUEST_NAME = 'zvr-quit-request'


def quit_request_path(temp_dir):
    """Where a restart tool leaves a "please quit Anki properly" note for this add-on."""
    return Path(str(temp_dir)) / QUIT_REQUEST_NAME


def take_quit_request(path):
    """True once if a quit request is waiting, and the request file is consumed.

    A tray add-on turns every window close — including AnkiConnect's guiExitAnki, which is
    only mw.close() — into a hide, so an outside tool cannot ask Anki to exit at all. It can
    leave a note here, and this add-on answers it with the tray's own exit protocol.
    """
    try:
        if path.exists():
            path.unlink()
            return True
    except OSError:
        return False
    return False


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


POS_TAG = r'(?:adj|adv|conj|prep|pron|interj|aux|art|num|int|det|vt|vi|n|v)'
# 'vt&vi.' and 'n./v.' are one marker each. Matching only the bare tag made the second
# half look like the start of a new line, and the card printed a dangling 'vt&' above
# 'vi. 出产'. A run may be joined by & / 、 or by a dot between two tags.
POS_RUN = POS_TAG + r'(?:[\s&/、.]*' + POS_TAG + r')*\.'
POS_PATTERN = r'(?<![A-Za-z])' + POS_RUN
POS_LINE = r'^(' + POS_RUN + r')\s*(.*)$'


def format_meaning(text):
    pattern = POS_PATTERN
    formatted = re.sub(r'\s*(' + pattern + r')', lambda match: '\n' + match.group(1), normalize_meaning_lists(text), flags=re.I).strip()
    return re.sub(r'(' + pattern + r')(?=[\u3400-\u9fff])', r'\1  ', formatted, flags=re.I)


def meaning_markers(text):
    """The part-of-speech labels that open each meaning line, for the column width."""
    return [match[0] for match in re.findall(r'(?m)' + POS_LINE, format_meaning(text), flags=re.I)]


def meaning_table(text, part_width=30, indent=0, gap=8):
    """A two-column meaning block: part of speech right-aligned, meaning left-aligned.

    The empty `gap` cell is what makes the space between the two columns identical on every
    line — with the text butted up against the marker column, a short `n.` and a long
    `n & v.` gave the meaning a different starting distance.
    """
    # The leading spacer is what pulls the adj./n. block in under its 【解释】 heading;
    # Qt rich text honours a fixed-width empty cell and nothing else reliably.
    lead = '<td width="%d"></td>' % indent if indent else ''
    rows = []
    for line in format_meaning(text).splitlines():
        match = re.match(POS_LINE, line, flags=re.I)
        if match:
            rows.append('<tr>%s<td width="%d" align="right" valign="top">%s</td>'
                        '<td width="%d"></td><td valign="top">%s</td></tr>' %
                        (lead, part_width, html.escape(match.group(1)), gap,
                         html.escape(match.group(2).strip())))
        else:
            rows.append('<tr>%s<td colspan="3">%s</td></tr>' % (lead, html.escape(line.strip())))
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


# Question modes are not equally strong evidence. Producing the spelling is the hardest
# class, so a slip there counts more and a flawless run counts as "already known";
# recognising a meaning among four options is the weakest, so its slips are forgiven.
MODE_DIFFICULTY = {'typing': 3, 'cloze': 2, 'reverse': 2, 'listening': 1, 'speaking': 1,
                   'choice': 1, 'judgment': 1}
MODE_WEIGHT = {mode: {1: 0.8, 2: 1.2, 3: 1.5}[difficulty] for mode, difficulty in MODE_DIFFICULTY.items()}
# Answering one of these inside the window is what turns a right answer into "already
# known"; 判断题 is excluded because two options make a fast answer a coin flip.
MASTERED_WINDOW_SECONDS = 3.0
MASTERED_TIMED_MODES = frozenset(('choice', 'reverse', 'listening', 'speaking', 'cloze'))


def letter_weight(index):
    """How much the letter at `index` is worth when a hint gives it away.

    The user's rule: 前面的字母比后面的字母权重要高. The first letter of an English word
    narrows the field of candidates far more than the next-to-last, so the value falls off
    as 1/(i+1) — cheap to compute, and it makes "one letter out of a 14-letter word" and
    "one letter out of a 5-letter word" mean different things, which a plain count cannot.
    """
    return 1.0 / (index + 1)


def hint_share(revealed, letters):
    """The position-weighted fraction of the word that letter hints already gave away."""
    if letters <= 0 or not revealed:
        return 0.0
    total = sum(letter_weight(index) for index in range(letters))
    given = sum(letter_weight(index) for index in revealed if 0 <= index < letters)
    return given / total


# Bands chosen so that one early letter of a long word is still a good recall (Good), the
# first letter of a short word is a real give-away (Hard), and a late letter barely counts.
HINT_SHARE_BANDS = ((0.20, 4), (0.40, 3), (0.70, 2))


def ease_from_hint_share(share):
    for limit, ease in HINT_SHARE_BANDS:
        if share <= limit:
            return ease
    return 1


# 一次发音提示几乎等于没提示：用户点名它应当仍然建议 Easy。
AUDIO_HINT_EASE = {0: 4, 1: 4, 2: 3}


def ease_from_audio_hints(uses):
    return AUDIO_HINT_EASE.get(max(0, int(uses)), 2)


def suggested_ease(correct, hints=0, incorrect_letters=0, failed_checks=0, mode=None,
                   audio_hints=0, revealed=(), letters=0, other_hints=0):
    """The grade the card should recommend, from what the learner actually needed.

    Two calling styles on purpose: a spelling card now reports its hints by kind (发音 /
    字母位置 / 释义与例句), which lets a single listen stay Easy and prices a revealed letter
    by where it sits in the word. Callers that only know a press count keep the old
    blanket rule — any hint meant Hard — so nothing else in the app changes today.
    """
    weight = MODE_WEIGHT.get(mode, 1.0)
    if not correct:
        return 1
    detailed = bool(audio_hints or other_hints or revealed or letters)
    if detailed:
        burden = (incorrect_letters + 2 * failed_checks) * weight
        if incorrect_letters >= 4 or failed_checks >= 2 or burden >= 5:
            return 1
    else:
        burden = (incorrect_letters + 2 * hints + 2 * failed_checks) * weight
        if hints >= 2 or incorrect_letters >= 4 or failed_checks >= 2 or burden >= 5:
            return 1
    caps = [4]
    if detailed:
        caps.append(ease_from_audio_hints(audio_hints))
        caps.append(ease_from_hint_share(hint_share(revealed, letters)))
        if other_hints:
            # 释义和例句直接把答案的方向递过去了，仍按原来的 Hard 处理。
            caps.append(2)
    elif hints:
        caps.append(2)
    if incorrect_letters >= 2 or failed_checks:
        caps.append(2)
    elif incorrect_letters == 1:
        caps.append(3)
    return min(caps)


def suggests_mastering(mode, correct, hints=0, incorrect_letters=0, failed_checks=0, seconds=None):
    """When an answer is proof the word is already known, not just recalled this time.

    Producing the spelling of the base form is its own evidence, so it needs no clock.
    Picking the right meaning out of options is only convincing when it was instant, so
    those modes have to answer inside the window. Judgment cards are left out entirely:
    with two options a fast right answer is a coin flip that got lucky.
    """
    if not correct or hints or incorrect_letters or failed_checks:
        return False
    if mode == 'judgment':
        return False
    if mode == 'typing':
        return True
    if mode in MASTERED_TIMED_MODES:
        return seconds is not None and seconds <= MASTERED_WINDOW_SECONDS
    return False


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
    # The blank is as long as the headword, not as long as the form the sentence happens to
    # use: a sentence that says "patterns" still asks the learner to type "pattern".
    blank = spelling_hint(word, 0)
    return re.sub(pattern, lambda match: blank, sentence, flags=re.I)


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
    if not (cfg.get('review_beautify', True) and kind in ('reviewQuestion', 'reviewAnswer')):
        return False
    if model != cfg['model']:
        return False
    # Every book is a view over the same note type, so once a book has been resolved
    # only its decks get restyled; before that, styling by model is the honest guess
    # rather than leaving the native card unstyled.
    decks = review_decks(cfg)
    return not decks or any(deck == name or deck.startswith(name + '::') for name in decks)


# A 词书 is one named view over the collection — the only thing the user picks.
#
# Scope is a tag rather than a deck on purpose: 六级核心 ⊂ 六级全表, and a card can
# only live in one deck, so nested lists cannot be decks. Tags also mean one card
# keeps one review history no matter which book is showing it. 文献单词 is the
# exception: it is a source, not a word list, and its cards really are in one deck.
STUDY_BOOKS = (
    {'id': 'cet6_core', 'name': '六级核心', 'tag': 'zvr_cet6_core'},
    {'id': 'cet6_full', 'name': '六级全表', 'tag': 'zvr_cet6_full'},
    {'id': 'cet4_core', 'name': '四级核心', 'tag': 'zvr_cet4_core'},
    {'id': 'cet4_full', 'name': '四级全表', 'tag': 'zvr_kyle_cet4'},
    {'id': 'cet6_kyle', 'name': '六级词表（KyleBing）', 'tag': 'zvr_kyle_cet6'},
    {'id': 'literature', 'name': '文献单词', 'deck': '文献单词'},
)
BOOK_BY_ID = {book['id']: book for book in STUDY_BOOKS}
# Old configs point at retired 词书 ids and tag names. Every legacy value has to land
# on the book that means the same cards — mapping 六级词表 onto 六级全表 would quietly
# swap one word list for another, which is worse than showing a redundant entry.
BOOK_MIGRATION = {'cet6_core': 'cet6_core', 'cet6_full': 'cet6_full', 'cet4_kyle': 'cet4_full',
                  'cet6_kyle': 'cet6_kyle', 'zvr_cet6_core': 'cet6_core', 'zvr_cet6_full': 'cet6_full',
                  'zvr_cet4_core': 'cet4_core', 'zvr_kyle_cet4': 'cet4_full', 'zvr_kyle_cet6': 'cet6_kyle',
                  '文献单词': 'literature'}


def _escape(value):
    return str(value).replace('\\', '\\\\').replace('"', '\\"')


def study_books(cfg=None):
    """The catalogue in force.

    Overridable from config so a book can be added without editing the source — the
    whole complaint about the old 词书 dropdown was that its list was baked in.
    """
    return list((cfg or {}).get('study_books') or STUDY_BOOKS)


def study_book_id(cfg):
    """The chosen book, or None when nothing valid has been picked yet.

    Every route into a book id is checked against the catalogue in force: a legacy
    value that names a book this config does not offer must resolve to nothing rather
    than to a dangling id, which would silently study nothing.
    """
    known = {book['id'] for book in study_books(cfg)}
    value = str(cfg.get('study_book') or '').strip()
    if value in known:
        return value
    candidates = [str(item).strip() for item in (cfg.get('review_scope_tags') or [])
                  if isinstance(cfg.get('review_scope_tags'), list)]
    candidates += [str(cfg.get('review_book') or '').strip()]
    for candidate in candidates:
        mapped = BOOK_MIGRATION.get(candidate)
        if mapped in known:
            return mapped
    return None


def study_book(cfg):
    wanted = study_book_id(cfg)
    return next((book for book in study_books(cfg) if book['id'] == wanted), None)


def book_clause(book):
    if not book:
        return ''
    return ' tag:"%s"' % _escape(book['tag']) if book.get('tag') else ' deck:"%s"' % _escape(book['deck'])


def book_label(cfg):
    book = study_book(cfg)
    return book['name'] if book else ''


def resolve_book_decks(api, cfg):
    """Which decks the chosen book actually spans.

    Anki counts the daily new-card limit per deck, so questions are still drawn deck
    by deck; this maps the book onto the decks that currently hold it. Cached on cfg
    because several callers need it within one session.
    """
    book = study_book(cfg)
    if not book:
        return []
    if cfg.get('_book_decks_key') == book['id'] and isinstance(cfg.get('_book_decks'), list):
        return cfg['_book_decks']
    if book.get('deck'):
        decks = [book['deck']] if book['deck'] in set(api('deckNames', {}) or []) else []
    else:
        available = sorted(api('deckNames', {}) or [])
        decks = [deck for deck in available
                 if api('findCards', {'query': 'deck:"%s" note:"%s"%s -is:suspended -is:buried'
                                            % (_escape(deck), _escape(cfg['model']), book_clause(book))})]
    cfg['_book_decks'] = decks
    cfg['_book_decks_key'] = book['id']
    return decks


def book_progress(api, cfg):
    """(learned, total) for the book. 'learned' means the card has been answered at
    least once — the wording the user picked, and deliberately not 'mature'."""
    book = study_book(cfg)
    if not book:
        return (0, 0)
    base = 'note:"%s"%s -is:suspended -is:buried' % (_escape(cfg['model']), book_clause(book))
    total = len(api('findCards', {'query': base}) or [])
    # Anki's prop search takes no colon: prop:reps>0. prop:reps:>0 is a parse error,
    # which is how this count silently failed before it was measured against Anki.
    learned = len(api('findCards', {'query': base + ' prop:reps>0'}) or [])
    return (learned, total)


def book_availability(api, cfg):
    """(new, due) cards this book can actually show now.

    A book can hold thousands of new cards and still have nothing to hand over,
    because Anki counts the daily new limit per deck and stops releasing cards once
    the deck's quota is spent. collection_plan suggests a deadline pace; this answers
    the narrower "can the button start a session right now" question.
    """
    new_now = due_now = 0
    for deck in resolve_book_decks(api, cfg):
        stats = _stats(api, deck)
        base = _search(dict(cfg, deck=deck))
        new_now += min(int(stats.get('new_count', 0)),
                       len(api('findCards', {'query': base + ' is:new'}) or []))
        due_now += min(int(stats.get('learn_count', 0)) + int(stats.get('review_count', 0)),
                       len(api('findCards', {'query': base + ' is:due'}) or []))
    return new_now, due_now


def _search(cfg, all_decks=False):
    book = study_book(cfg)
    deck = '' if all_decks else 'deck:"%s" ' % _escape(cfg['deck'])
    clause = '' if book and book.get('deck') and cfg['deck'] == book['deck'] else book_clause(book)
    return '%snote:"%s"%s -is:suspended -is:buried' % (deck, _escape(cfg['model']), clause)


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
        # The same words the 词书 menu calls 六级核心; a third name on the card only made
        # the reader wonder whether it was a different list.
        labels.append('六级核心')
    return labels


# Where each card pill comes from. The card prints one pill per list, so the provenance
# is per pill as well: a joined sentence named two sources for three labels and left the
# reader to work out which was which.
BOOK_LABEL_SOURCES = {
    '四级词表': 'ECDICT 四六级词表',
    '六级词表': 'ECDICT 四六级词表',
    '六级核心': 'CET-6 Top 500 社区整理',
}


def exam_word_sources(labels):
    """The sources behind a row of pill labels, in order, without repeats."""
    seen = []
    for label in labels or []:
        source = BOOK_LABEL_SOURCES.get(label)
        if source and source not in seen:
            seen.append(source)
    return seen


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


def background_instead_of_quit(tray_present, forcing_quit):
    """Whether a close of the main window is really a shutdown at all.

    A tray add-on ('Minimize to Tray 2') rewrites `mw.closeEvent` and sets
    `QApplication.setQuitOnLastWindowClosed(False)`, so the X button means "keep running in
    the background" — which is exactly what this plug-in needs for its popups to continue.
    Only its own exit flag (`closeEventFromAction`) or our 退出 Anki makes it a shutdown,
    and winding the timers down on the other case is what silently stopped all cards for an
    hour on 2026-11-04.
    """
    return bool(tray_present and not forcing_quit)


def hide_instead_of_quit(card_open, enabled, forcing_quit):
    """Closing Anki's main window hides it only while a study card is on screen.

    With no card up, the close button has to keep quitting Anki, or the user is left
    with a hidden process they cannot close.
    """
    return bool(enabled and card_open and not forcing_quit)


def sync_due(now, last_attempt, minutes, idle):
    """Background sync runs on quiet moments only, so it never lands mid-card."""
    if not idle:
        return False
    if last_attempt is None:
        return True
    return (now - last_attempt) >= datetime.timedelta(minutes=max(1, int(minutes)))


def install_sync_error_guard(sync_module, state, on_error):
    """Swap a sync module's modal error handler for a silent recorder, and hand back a restore.

    Anki reports every sync failure with a modal dialog. That is right for the sync button
    and wrong for an idle background sync, so the replacement writes the message into
    `state['error']`, tells `on_error` once — the caller pauses the timer there — and puts
    Anki's own handler back so the user's sync button keeps behaving normally.
    """
    original = getattr(sync_module, 'handle_sync_error', None)
    if not callable(original) or getattr(original, 'zvr_silenced', False):
        return lambda: None

    def silent(_mw, error):
        state['error'] = '%s: %s' % (type(error).__name__, error)
        restore()
        on_error(state['error'])

    def restore():
        if getattr(sync_module, 'handle_sync_error', None) is silent:
            sync_module.handle_sync_error = original

    silent.zvr_silenced = True
    sync_module.handle_sync_error = silent
    return restore


def apply_auto_sync_preference(profile, enabled, remembered):
    """Switch Anki's sync-on-open-and-close off while background sync is on, and back after.

    `profile['autoSync']` is the same key Anki's own preferences dialog writes, so this
    is a change the user could make by hand. We record what we found rather than assume
    it was on, so turning the feature off gives back exactly their own setting.
    """
    if profile is None:
        return remembered
    current = bool(profile.get('autoSync', True))
    if enabled:
        if remembered is None:
            remembered = current
        if current:
            profile['autoSync'] = False
        return remembered
    if remembered is not None:
        profile['autoSync'] = bool(remembered)
    return None


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


def study_plan(today, deadline, remaining_new, due, daily_target, done, hours, interval, introduced=0,
               available=None):
    """Estimate today's workload; due cards remain governed by Anki.

    `available` is what Anki will actually put in front of the user today — (new, due) as
    capped by the deck's own daily limits. The shortfall is measured against that, not
    against a group size, because a group is now whatever the user says it is.
    """
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
    serveable = remaining if available is None else max(0, int(available[0])) + max(0, int(available[1]))
    return {'days': days, 'new': suggested_new, 'new_remaining': new_remaining, 'due': max(0, due), 'goal': goal,
            'done': max(0, done), 'introduced': max(0, introduced),
            'batch': min(remaining, max(3, math.ceil(remaining / slots))) if remaining else 0,
            'capacity_shortfall': max(0, remaining - serveable)}


def session_batch_size(cfg, plan=None, manual=False):
    """How many cards make up one group.

    In fixed mode the number is the user's and nothing caps it: a group of 200 is allowed,
    and the session simply stops when the book or the day's allowance runs out, with the
    reason shown. The automatic plan sizes a group from the day's remaining work rather
    than from a hard ten, which used to turn a 104-card day into eleven separate clicks.
    """
    if cfg.get('review_plan_mode') == 'daily':
        batch = max(0, int((plan or {}).get('batch', 0)))
        return batch or (1 if manual else 0)
    return max(1, int(cfg.get('review_batch_size', 3)))


def updated_session_target(completed, plan):
    return max(completed, max(0, int(plan.get('batch', 0))))


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
    """The decks the chosen book spans. Empty until a book is picked or resolved —
    there is no longer a free-standing deck list in the settings."""
    decks = cfg.get('_book_decks')
    if isinstance(decks, list):
        return decks
    book = study_book(cfg)
    return [book['deck']] if book and book.get('deck') else []


def collection_plan(api, cfg, now=None):
    now = now or datetime.datetime.now()
    decks = resolve_book_decks(api, cfg)
    found = {'new': set(), 'due': set(), 'done': set(), 'introduced': set()}
    for deck in decks:
        base = _search(dict(cfg, deck=deck))
        for key, suffix in (('new', 'is:new'), ('due', 'is:due -is:new'), ('done', 'rated:1'), ('introduced', 'introduced:1')):
            found[key].update(api('findCards', {'query': base + ' ' + suffix}) or [])
    hours = (remaining_window_minutes(now, cfg.get('review_windows', [])) / 60
             if cfg.get('review_windows_enabled') else min(cfg.get('review_computer_hours', 8),
                 max(0, (24 * 60 - now.hour * 60 - now.minute - now.second / 60) / 60)))
    # What Anki will actually serve today, capped by each deck's own daily limits: this is
    # the ceiling a group size cannot get past. Callers that only speak findCards (the
    # in-process dashboard) cannot answer deck stats, and then simply make no claim about
    # today's ceiling rather than failing the whole plan.
    try:
        available = book_availability(api, cfg)
    except Exception:
        available = None
    plan = study_plan(now.date(), cfg.get('review_deadline', ''), len(found['new']),
                      len(found['due']), cfg.get('review_daily_goal', 0), len(found['done']),
                      hours, cfg.get('review_interval_minutes', 30), len(found['introduced']), available)
    if available is not None:
        plan['available_new'], plan['available_due'] = int(available[0]), int(available[1])
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
    decks = [deck for deck in resolve_book_decks(api, cfg) if deck in available]
    if not decks:
        raise ValueError('这个词书下没有可弹出的卡片，换一个词书试试。')
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
            # A rating that is still being written has already consumed its slot in
            # Anki's daily count; the next card must be chosen as if it had landed.
            allowed -= int(deck_cfg.get('_review_inflight_due' if label == 'due' else '_review_inflight_new', 0))
            if allowed <= 0:
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
        'answer_form': word,
        'cloze_shown': cloze_form(sentence, word) if mode == 'cloze' else '',
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


MASTERED_TAG = 'zvr_mastered'
# Anki's own four buttons, by ease. The card prints them as `A. Again` … `D. Easy`, and the
# look-back names a card the user already rated with the same words.
EASE_NAMES = {1: 'Again', 2: 'Hard', 3: 'Good', 4: 'Easy'}


def mark_mastered(api, cfg, question):
    """Take a word out of study without grading it.

    Suspend is the lever Anki itself honours, and every card query here already
    excludes suspended cards, so the word stops appearing at once and stays fully
    reversible. The tag is what makes the decision findable later: everything marked
    here can be recovered with one browser search instead of a guess.
    """
    card_id = question['card_id']
    notes = [item.get('note') for item in (api('cardsInfo', {'cards': [card_id]}) or []) if item.get('note')]
    api('suspend', {'cards': [card_id]})
    if notes:
        api('addTags', {'notes': notes, 'tags': MASTERED_TAG})
    return notes[0] if notes else None


def submit_review(api, cfg, question, ease, answer=None):
    if ease not in (1, 2, 3, 4):
        raise ValueError('无效的复习评分。')
    if api('getActiveProfile', {}) != question['profile']:
        raise ValueError('Anki 账户已切换，这张卡片不会被评分。')
    deck = question.get('review_deck', cfg['deck'])
    decks = review_decks(cfg)
    if decks and deck not in decks:
        raise ValueError('词书或牌组已改变，这张卡不在当前词书里，请在下次提醒时复习。')
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
