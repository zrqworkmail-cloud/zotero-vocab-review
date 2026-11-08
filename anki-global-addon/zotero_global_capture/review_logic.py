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
# class, so a slip there counts more and a flawless run earns the strongest rating;
# recognising a meaning among four options is the weakest, so its slips are forgiven.
MODE_DIFFICULTY = {'typing': 3, 'cloze': 2, 'reverse': 2, 'listening': 1, 'speaking': 1,
                   'choice': 1, 'judgment': 1}
MODE_WEIGHT = {mode: {1: 0.8, 2: 1.2, 3: 1.5}[difficulty] for mode, difficulty in MODE_DIFFICULTY.items()}


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


def grading_log_line(suggested, chosen, mode='', components=None, forced=False):
    """One line per rating: what the card recommended against what the learner pressed.

    The weights behind 建议评分 were chosen, not fitted, and the only honest way to find out
    whether they are too harsh is to count how often they are overridden. `mode` and the hint
    counts travel with the line because an override rate means nothing without knowing which
    card type it happened on and how much cueing that card took. `forced` marks the ratings
    that were never a choice — a wrong answer is Again whatever button was near.

    Read back by `tools/analyze-grading-agreement.py`; the key names are its contract.
    """
    fields = [('suggested', EASE_NAMES.get(suggested, '-') if suggested else '-'),
              ('chosen', EASE_NAMES.get(chosen, '-')),
              ('mode', mode or '-')]
    if components:
        fields.append(('audio', int(components.get('audio_hints') or 0)))
        fields.append(('other', int(components.get('other_hints') or 0)))
        fields.append(('letters', len(components.get('revealed') or ())))
        fields.append(('boxes', int(components.get('letters') or 0)))
    if forced:
        fields.append(('forced', 'again'))
    return 'review graded: %s' % ' '.join('%s=%s' % pair for pair in fields)


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


# suggests_mastering lived here until 2026-11-07, when the user retired the E/已掌握
# button: every answer is graded A–D again, and a flawless spelling simply earns Easy.
# mark_mastered below stays for the cards already tagged zvr_mastered.

ANSWER_KEY_HINT = 'A–D 改评 · Shift+F 看题 · P 回看'


def show_examples(cfg, mode):
    """Whether the answer face may lay out 例句 cards.

    The learner asked for this switch on 2026-11-06: the examples are the tallest part of the
    answer and the part he reads least. Two things are deliberately outside the switch, and
    both would surprise him if they were inside it:

    * 例句填空 — the question *is* an example sentence, so switching examples off there would
      switch the card off;
    * the 例句 hint button — asking for an example stays his choice, and it prices itself as a
      hint, so it cannot be reached by accident.
    """
    if mode == 'cloze':
        return True
    return bool(cfg.get('review_show_example', True))


def answer_report(hint_text, incorrect_letters=0, failed_checks=0, rating='Good',
                  seconds=None, show_seconds=False):
    """Return (line, tooltip) for the answer face's status row.

    The row used to carry the whole accounting and wrapped to two lines: 「发音提示 2 次，
    字母提示 1/12（按位置已给出 5%），错误字母 6 次，检查失败 0 次；建议"Again"，回车继续，
    也可按 A–E 自行评分；按 F 看回题目，按 P 回看上一张。」 The learner asked for less of it
    on 2026-11-05 and chose the two-layer shape: **one short line for the decision, the
    evidence one hover away** — so nothing about how a suggestion was priced is lost, it
    just stops eating the card's height.

    Two rules the tests pin, because both were decided rather than assumed:

    * **A zero is never printed.** "检查失败 0 次" is noise; it says nothing about this card
      and it is the item that made the line grow on every flawless answer. 「无提示」 is not
      a zero — it is the reason a flawless spelling is offered Mastered, so it stays.
    * **The clock appears only where it is evidence.** Spelling is priced by hints, not by
      speed; every other mode needs the seconds, because a 9.2 秒 answer is exactly why E
      was not offered.
    """
    line = '建议 %s（回车/空格）· %s' % (rating, ANSWER_KEY_HINT)
    parts = [hint_text] if hint_text else []
    if incorrect_letters:
        parts.append('错误字母 %d 次' % incorrect_letters)
    if failed_checks:
        parts.append('检查失败 %d 次' % failed_checks)
    if show_seconds and seconds is not None:
        parts.append('用时 %.1f 秒' % seconds)
    return line, '，'.join(part for part in parts if part)


def pulse_bright(step, period=2):
    """Which half of the focused-box blink this tick is.

    The frame brightens and dims rather than switching off, so there is no half-period in
    which the card looks like nothing has focus -- which matters now that the text caret is
    gone from the letter boxes (learner 2026-11-06).
    """
    return int(step) % max(1, int(period)) == 0


@lru_cache(maxsize=1)
def _mnemonics():
    """word -> 记忆法, from the shipped KyleBing table (`lexicon/mnemonics.tsv`).

    The table is generated by `tools/build-mnemonics-lexicon.py` from a BSD-3-Clause dataset
    that already carries a root decomposition per word (`re(相反) + bell(战争) + ion → 反叛`),
    because inventing etymologies at scale is how a learning app teaches wrong things. It
    covers 2615 of the 5211 notes in 《六级全表》 (counted over the whole book) — the rest show
    no 识记方法 block at all rather than a made-up one.
    """
    path = Path(__file__).parent / 'lexicon' / 'mnemonics.tsv'
    table = {}
    if not path.exists():
        return table
    for line in path.read_text(encoding='utf-8').splitlines():
        parts = line.split('\t')
        if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
            table.setdefault(parts[0].strip().casefold(), parts[1].strip())
    return table


def mnemonic_for(word):
    return _mnemonics().get(str(word or '').strip().casefold(), '')


def question_mnemonic(card, word):
    """The 识记方法 for a note: its own field first, then the shipped table.

    The field comes first so anything the learner wrote by hand is never overwritten by the
    data file; the table is the fallback because the 四六级单词模板 has no 识记方法 field at
    all, which left the card's 【识记方法】 block dead code until now.
    """
    return clean_detail(_field(card, '识记方法')) or mnemonic_for(word)

def letter_hint_label(given, total):
    """Text for the letter-hint control: `字母 2/9` says what one more tap is worth.

    The count used to live only in the tooltip and in the answer face's evidence line, so on
    the question face the button promised a hint without saying how much of the word was
    already given away (user 2026-11-06 asked for the row to be redesigned).
    """
    return '字母 %d/%d' % (max(0, int(given)), max(0, int(total)))


def phonetic_available(question):
    """Is there a transcription this card could show?

    Measured on the live collection 2026-11-06: 111 of 120 sampled 六级全表 notes carry a
    音标 field. The other ~8 % get no 音标 control at all rather than a button that does
    nothing — the same rule the rest of the card follows for empty items.
    """
    return bool(str((question or {}).get('phonetic') or '').strip())


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
    if book.get('tag'):
        return ' tag:"%s"' % _escape(book['tag'])
    if book.get('deck'):
        return ' deck:"%s"' % _escape(book['deck'])
    # A catalogue entry always carries one of the two. A dict that carries neither — a half
    # migrated entry, a hand built test book — means "no scope", and must not raise its way
    # through whichever caller happens to ask (2026-11-06: the picker did, KeyError 'deck').
    return ''


def book_label(cfg):
    book = study_book(cfg)
    return book['name'] if book else ''


def book_tag_counts(api, cfg, book):
    """Which tags really appear on this book's cards, and how many cards each covers.

    The 词组 picker lists these instead of the whole tag vocabulary, because a checkbox for a
    tag that never touches the book is a button that does nothing. One `getTags` plus a single
    batched `multi` of searches — measured at 0.36 s for 30 tags against 5211 cards, which is
    why this is safe to run when a row is expanded rather than for every row up front.

    Counts are per tag and deliberately not mutually exclusive: a card usually carries the
    book tag, a word-list tag and sometimes 已掌握. The picker treats the checked tags as a
    union, so the numbers are labels, not a partition, and they must never be summed.
    """
    clause = book_clause(book)
    if not clause:
        return []
    try:
        tags = [tag for tag in (api('getTags', {}) or [])]
    except Exception:
        return []
    if not tags:
        return []
    actions = [{'action': 'findCards',
                'params': {'query': '%s tag:"%s"' % (clause, _escape(tag))}} for tag in tags]
    try:
        answers = api('multi', {'actions': actions}) or []
    except Exception:
        return []
    counts = []
    for tag, ids in zip(tags, answers):
        # Measured against the running AnkiConnect: `multi` hands back each action's plain
        # result, so an item is the list of card ids. Unpacking it as a [result, error] pair
        # is worse than wrong — a tag with exactly two cards looks like a pair, and the count
        # then comes out of len(int) (2026-11-06, caught before the picker was wired).
        total = len(ids) if isinstance(ids, list) else 0
        if total:
            counts.append((tag, total))
    counts.sort(key=lambda item: (-item[1], item[0]))
    return counts


def book_untagged_count(api, book, tags):
    """How many of the book's cards carry no tag but the book's own.

    The picker lists this as （无标签）and it is a first-class choice, not a leftover: on a book
    built from a word list most cards are untagged, and without this row "只勾两个标签" would
    silently hide them. One search, with every listed tag excluded.
    """
    clause = book_clause(book) if book else ''
    if not clause:
        return 0
    for tag in tags or []:
        clause += ' -tag:"%s"' % _escape(tag)
    try:
        return len(api('findCards', {'query': clause}) or [])
    except Exception:
        return 0


def selection_entries(cfg):
    """The ordered 词组 selections in force, each validated against the catalogue.

    `tags: []` means "the whole book", not "nothing" — the only reading that lets one entry
    say both. A legacy single `study_book` becomes one entry with no tag subset, so nobody
    who never opened the new control changes what they study.

    Entries that name a book this catalogue does not offer are dropped, not guessed at: a
    dangling id would look selected and study nothing, which is the shape of the bug recorded
    in §9.12.
    """
    books = {book['id']: book for book in study_books(cfg)}
    raw = (cfg or {}).get('study_selection')
    entries = []
    if isinstance(raw, list):
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            book_id = str(item.get('book') or '').strip()
            if book_id not in books or book_id in seen:
                continue
            seen.add(book_id)
            tags = [str(tag).strip() for tag in (item.get('tags') or []) if str(tag).strip()]
            entries.append({'book': books[book_id], 'tags': tags})
    if entries:
        return entries
    legacy = study_book_id(cfg)
    if legacy:
        return [{'book': books[legacy], 'tags': []}]
    return []


def entry_clause(entry):
    """One entry's search fragment: its book, narrowed to the union of the chosen tags.

    Union, not intersection — checking a second tag must never make the pool smaller, which
    is what an intersection would do and what the learner would read as a bug.
    """
    base = book_clause(entry.get('book'))
    tags = entry.get('tags') or []
    if not tags:
        return base
    joined = ' OR '.join('tag:"%s"' % _escape(tag) for tag in tags)
    subset = '(%s)' % joined
    if not base.strip():
        return ' %s' % subset
    return ' %s AND %s' % (base.strip(), subset)


def selection_clause(entries):
    """The whole selection as one fragment, for queries that span every chosen 词组.

    Each entry that carries its own AND is parenthesised. Without that the result reads
    `tag:A OR tag:B AND (tag:x)` and is only correct because Anki happens to bind AND
    tighter than OR — a precedence coincidence, not a design.
    """
    parts = []
    for entry in entries:
        part = entry_clause(entry).strip()
        if not part:
            continue
        parts.append('(%s)' % part if ' AND ' in part else part)
    if not parts:
        return ''
    if len(parts) == 1:
        return ' %s' % parts[0]
    return ' (%s)' % ' OR '.join(parts)


def entry_view(cfg, index):
    """A cfg pinned to one selection entry, so every single-book function keeps working.

    The view is a plain dict copy carrying `_selection_index`; `_search()` is the one place
    that reads it, which is what keeps the change from spreading through the module.
    """
    entries = selection_entries(cfg)
    if not 0 <= index < len(entries):
        return None
    view = dict(cfg)
    view['_selection_index'] = index
    view['study_book'] = entries[index]['book']['id']
    return view


def current_entries(cfg):
    """The entries this cfg should search over: one when pinned, all otherwise."""
    entries = selection_entries(cfg)
    index = (cfg or {}).get('_selection_index')
    if index is None:
        return entries
    return [entries[index]] if 0 <= index < len(entries) else []


def selection_labels(cfg):
    return [entry['book']['name'] for entry in selection_entries(cfg)]


def selection_summary(cfg):
    """'六级核心、六级全表' for the end-of-session sentence, or the single book name."""
    labels = selection_labels(cfg)
    return '、'.join(labels) if labels else '这本词书'


def _clause_for(cfg):
    """The book/tag fragment for this cfg — the whole selection, or one entry when pinned."""
    entries = current_entries(cfg)
    if len(entries) == 1:
        return entry_clause(entries[0])
    return selection_clause(entries)


def _book_decks_for(api, cfg, book):
    """The decks one book spans. Not cached on its own: `resolve_book_decks` caches the
    union for the whole selection, and a per-book dict on cfg leaked from one call to the
    next (it survived a changed deck list and, in the tests, a changed cfg)."""
    if book.get('deck'):
        decks = [book['deck']] if book['deck'] in set(api('deckNames', {}) or []) else []
    else:
        available = sorted(api('deckNames', {}) or [])
        clause = book_clause(book)
        decks = [deck for deck in available
                 if api('findCards', {'query': 'deck:"%s" note:"%s"%s -is:suspended -is:buried'
                                            % (_escape(deck), _escape(cfg['model']), clause)})]
    return decks


def resolve_book_decks(api, cfg):
    """Which decks the selection actually spans.

    Anki counts the daily new-card limit per deck, so questions are still drawn deck by deck;
    this maps the selection onto the decks that currently hold it. Cached on cfg per book id
    because several callers need it within one session, and a pinned view returns only its
    own entry's decks.
    """
    entries = current_entries(cfg)
    key = _selection_cache_key(entries)
    if not entries:
        return []
    if cfg.get('_book_decks_key') == key and isinstance(cfg.get('_book_decks'), list):
        return cfg['_book_decks']
    decks = []
    for entry in entries:
        for deck in _book_decks_for(api, cfg, entry['book']):
            if deck not in decks:
                decks.append(deck)
    cfg['_book_decks'] = decks
    cfg['_book_decks_key'] = key
    return decks


def _selection_cache_key(entries):
    """One entry with no tag subset keys as its plain book id, so a preseeded
    `_book_decks_key='cet'` still means what it meant before this feature."""
    parts = []
    for entry in entries:
        tags = entry.get('tags') or []
        parts.append(entry['book']['id'] + (':' + '|'.join(tags) if tags else ''))
    return ','.join(parts)


def book_suspended(api, cfg):
    """How many cards the learner parked, counted inside the current selection.

    Asked for only at end-of-session, because "已学完" otherwise reads as "there is nothing
    left" while 247 cards sit in his 挂起 list (measured on 《六级全表》, 2026-11-06). Suspended
    is his scheduling state: this counts it, and never touches it.
    """
    try:
        return len(api('findCards', {'query': 'is:suspended' + _clause_for(cfg)}) or [])
    except Exception:
        return 0


def due_outside_book(api, cfg):
    """Due cards in the whole collection that this selection does not cover.

    Read-only, and only asked for at end-of-session, where the sentence needs it to tell the
    learner whether "nothing left" means the collection or just their chosen 词组.
    """
    try:
        everywhere = set(api('findCards', {'query': 'is:due'}) or [])
    except Exception:
        return 0
    clause = _clause_for(cfg)
    if not clause:
        return len(everywhere)
    try:
        inside = set(api('findCards', {'query': 'is:due' + clause}) or [])
    except Exception:
        return len(everywhere)
    return max(0, len(everywhere) - len(inside))


def book_progress(api, cfg):
    """(learned, total) for the selection — or for one entry when the cfg is pinned.

    'learned' means the card has been answered at least once — the wording the user picked,
    and deliberately not 'mature'.
    """
    clause = _clause_for(cfg)
    if not clause and not current_entries(cfg):
        return (0, 0)
    base = 'note:"%s"%s -is:suspended -is:buried' % (_escape(cfg['model']), clause)
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
    """The query that means "cards from this selection", inside one deck.

    The book/tag fragment is dropped only when it is provably redundant — a single entry
    that is a whole deck, and that deck is the one being searched. Keeping the fragment in
    every other case is what makes a multi-词组 selection read correctly instead of quietly
    matching the whole deck.
    """
    deck = '' if all_decks else 'deck:"%s" ' % _escape(cfg['deck'])
    entries = current_entries(cfg)
    if (len(entries) == 1 and not entries[0]['tags'] and entries[0]['book'].get('deck')
            and cfg['deck'] == entries[0]['book']['deck']):
        clause = ''
    elif entries:
        clause = _clause_for(cfg)
    else:
        # No selection at all: fall back to the single-book reading so an unconfigured
        # account behaves exactly as it did before this feature.
        book = study_book(cfg)
        redundant = book and book.get('deck') and cfg['deck'] == book['deck']
        clause = '' if redundant else book_clause(book)
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


def deck_limits(api, cfg, decks=None):
    """Each deck's own daily ceilings, next to what was actually served today.

    Two different numbers have been claiming to be "today's limit": the plan's arithmetic and
    Anki's `new/day`. Measured on 2026-11-06 the shared config says 50 while one deck had
    already introduced 139 new cards that day, because this plug-in picks cards with
    `findCards` and grades them with `answerCards` — it never asks the reviewer's queue for
    permission, so the cap does not bind it. Reporting both numbers side by side is the point;
    nothing here changes a deck setting.
    """
    names = decks if decks is not None else resolve_book_decks(api, cfg)
    limits = []
    for deck in names:
        try:
            config = api('getDeckConfig', {'deck': deck}) or {}
        except Exception:
            config = {}
        new = config.get('new') or {}
        rev = config.get('rev') or {}
        clause = 'deck:"%s"' % str(deck).replace('\\', '\\\\').replace('"', '\\"')
        try:
            answers = api('multi', {'actions': [
                {'action': 'findCards', 'params': {'query': '%s introduced:1' % clause}},
                {'action': 'findCards', 'params': {'query': '%s is:new' % clause}},
                {'action': 'findCards', 'params': {'query': '%s is:due' % clause}}]}) or []
        except Exception:
            answers = []
        counts = [len(item or []) if isinstance(item, list) else 0 for item in answers]
        while len(counts) < 3:
            counts.append(0)
        limits.append({'deck': deck, 'name': config.get('name') or deck,
                       'new_per_day': int(new.get('perDay') or 0),
                       'rev_per_day': int(rev.get('perDay') or 0),
                       'delays': new.get('delays') or [],
                       # The promise the retention table is measured against; it lives in the
                       # deck config (`desiredRetention`, measured 2026-11-06), not in Anki's
                       # Python-side deck dict, which is why the report reads it from here.
                       'desired_retention': config.get('desiredRetention'),
                       'introduced_today': counts[0], 'new_left': counts[1], 'due': counts[2]})
    return limits


def render_deck_limits(limits):
    """One line per deck: what Anki says the ceiling is, and what actually happened today."""
    lines = []
    for item in limits:
        overshoot = ('（今日已引入 %d > 额度 %d：插件取卡不经调度器队列，额度拦不住）'
                     % (item['introduced_today'], item['new_per_day'])
                     if item['new_per_day'] and item['introduced_today'] > item['new_per_day'] else '')
        lines.append('%s：new/day %d，今日已引入 %d%s；在架新词 %d，到期 %d' % (
            item['deck'], item['new_per_day'], item['introduced_today'], overshoot,
            item['new_left'], item['due']))
    return '\n'.join(lines)


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


def end_of_session_reason(plan, limits_new, book_label='', elsewhere_due=0, mode_labels=(),
                          suspended=0):
    """Say why nothing further can be shown, with the reason that is actually true.

    This used to have one specific branch and a catch-all that guessed two causes in one
    sentence ("已选题型下没有…，可能是牌组当日新词额度已用完"). On 2026-11-05 the learner hit
    the catch-all for a reason it did not describe: 《六级核心》 had 0 new and 0 due left in it
    while the deck still held 468 new cards outside the book — neither the question types nor
    the daily allowance was the cause, and both guesses were wrong. Same disease as the
    "建议学习新词 0" panel: a computed zero dressed in vague words makes the user invent the
    reason.

    Each branch now names the number that produced it, and offers the next thing to do.
    """
    label = book_label or '这本词书'
    if plan is None:
        return '本组结束：没有读到计划数据，无法判断原因。'
    remaining_new = int(plan.get('remaining_new_total', 0) or 0)
    due = int(plan.get('due', 0) or 0)
    available_new = int(plan.get('available_new', 0) or 0)
    new_spent = limits_new and int(plan.get('new_remaining', 0) or 0) <= 0
    if new_spent and remaining_new > 0:
        return ('本组结束：牌组今天的新词额度已用完，%s 里还剩 %d 张新词，明天继续。'
                % (label, remaining_new))
    if new_spent:
        return ('本组结束：今天的新词计划已完成，剩下的都是到期复习词。' if due
                else '本组结束：今天的新词计划已完成，也没有到期复习词。')
    if remaining_new <= 0 and due <= 0:
        elsewhere = ('合集里另有 %d 张到期卡不在所选词组内。' % elsewhere_due if elsewhere_due
                     else '合集里也没有其他到期卡。')
        # 「已学完」was the branch that lied by omission: on 2026-11-06 the book had 247 cards
        # parked in 挂起, and the sentence offered only "勾一本词组". A zero stays silent.
        parked = ('另有 %d 张被你挂起。' % suspended if suspended else '')
        return ('本组结束：%s 已学完——没有未学的新词，今天也没有到期复习。%s%s想继续，'
                '在设置里再勾一本词组即可。' % (label, elsewhere, parked))
    if remaining_new > 0 and available_new <= 0:
        return ('本组结束：%s 里还有 %d 张新词，但牌组今天不再发放新词，明天会继续。'
                % (label, remaining_new))
    modes = '、'.join(mode_labels) or '已选题型'
    return ('本组结束：%s 里还有内容，但已选题型（%s）下没有可出的词。换题型或勾选更多题型即可。'
            % (label, modes))


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
# One place spells the question types out; the settings checkboxes and the end-of-session
# sentence used to carry their own copies, which is how a renamed type could appear under two
# different names in the same app.
MODE_LABELS = {'choice': '英文选中文', 'reverse': '中文选英文', 'typing': '释义拼写',
               'cloze': '例句填空', 'listening': '听音拼写', 'judgment': '单词释义判断',
               'speaking': '口语回忆（自主评分）'}
MODE_ORDER = REVIEW_MODES


def selected_mode_labels(cfg):
    """The chosen question types, spelled the way the settings page spells them."""
    return [MODE_LABELS[mode] for mode in selected_review_modes(cfg) if mode in MODE_LABELS]


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
    """Draw the next question from the selection, in order.

    The outer loop lives here, as a wrapper, rather than inside `_question_from`: the body
    already had a queue loop whose `due_only` short-circuit is easy to get wrong (it needed
    `continue`, not `break`), and nesting a third loop inside it is where that bug would come
    back. Entries are tried in list order and the first one that can produce a card wins, so
    a finished 词组 hands over to the next without any stored cursor to go stale.
    """
    if cfg.get('_selection_index') is not None:
        return _question_from(api, cfg, mode, rng, due_only)
    entries = selection_entries(cfg)
    if not entries:
        return _question_from(api, cfg, mode, rng, due_only)
    failures = []
    for index in range(len(entries)):
        try:
            question = _question_from(api, entry_view(cfg, index), mode, rng, due_only)
        except ValueError as error:
            failures.append(str(error))
            continue
        if question:
            question['_selection_index'] = index
            return question
    if len(failures) == len(entries):
        # Every entry is unusable, not merely empty: say so the way one book used to.
        raise ValueError(failures[0])
    return None


DUE_SHARE = 0.2
# How many of every group come from the due queue (learner 2026-11-06: 每组混排固定比例的旧词).
# The reason this exists is the 250 cards measured live in `state:learning`: Anki's learning
# steps are meant to come back the same day, and the 2026-11-05 rule "new words first, reviews
# after today's quota" pushed them behind ~37 groups of new cards, which silently turns a
# 10-minute step into tomorrow. A fixed share keeps the learner's intent -- new words still
# dominate -- without starving the steps.


def due_slots_for(group_size, due_available):
    """Old cards in this group: the share, floored, never more than actually exist."""
    if group_size <= 0 or due_available <= 0:
        return 0
    return min(int(group_size * DUE_SHARE), int(due_available))


def queue_order(group_position, group_size, due_available, new_available, due_only=False):
    """Which queue the card at `group_position` should come from.

    Due first while the group's old-word slots last, new after that; a queue that is empty
    simply yields to the other one, and `due_only` never touches new cards at all.
    """
    if due_only:
        return 'due'
    if new_available <= 0:
        return 'due'
    if group_position < due_slots_for(group_size, due_available):
        return 'due'
    return 'new'


def study_state_label(kind, learning):
    """What the card's eyebrow says about where this card really sits in the schedule.

    `到期复习` used to cover every card that was not new. On this machine that was wrong for
    252 of the 253 due cards in 《六级全表》: they are still inside Anki's first learning steps,
    words seen once and answered Again yesterday. Calling those 到期复习 reads as "you studied
    this long ago", so the label follows the queue instead — 刚学过 for the intro steps,
    到期复习 once the card has graduated.
    """
    if kind == 'new':
        return '新词'
    return '刚学过' if learning else '到期复习'


# The three labels are one word each on the card, and the difference between them is not
# visible there, so the tooltip spells out what each claims about Anki's own schedule.
STUDY_STATE_NOTES = {
    '新词': '第一次遇到，Anki 还没给它排过间隔',
    '刚学过': '还在学习步长里：之前见过，答错过，Anki 让你再来一遍',
    '到期复习': '已经毕业，按 Anki 算出的间隔到期',
}


def card_is_learning(api, card_id):
    """Ask the scheduler, not our own bookkeeping: is this card still in its intro steps?

    `is:learn -is:review` is Anki's own wording for a card that has never graduated, which is
    the one thing that separates yesterday's failures from real reviews. A failed lookup
    answers False: the label is decoration, and losing the card over it would be worse.
    """
    try:
        return bool(api('findCards', {'query': 'cid:%s is:learn -is:review' % card_id}))
    except Exception:
        return False


def _question_from(api, cfg, mode, rng, due_only):
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
    # New words first, due reviews after: the learner's rule on 2026-11-05 — 「如果有到期的
    # 单词应该在我学习完当天的六级词汇之后，安排进行学习进度里」. The daily total in the plan
    # is unchanged; only which queue is emptied first.
    # `continue`, not `break`: with the old due-first order, `due_only` skipped the new queue
    # by breaking out of the loop, which was safe because new came last. Swap the order and
    # that same break would silently stop every due card.
    # Which queue this slot belongs to. The loop below still tries the other queue as a
    # fallback, so a due slot whose card turned out unusable does not waste the group slot.
    suffixes = {'new': 'is:new', 'due': 'is:due -is:new'}
    position, size = (cfg.get('_review_group') or (0, 0))[:2]
    due_available = sum(max(0, int(stats.get('learn_count', 0)) + int(stats.get('review_count', 0))
                            - int(deck_cfg.get('_review_inflight_due', 0)))
                        for stats, deck_cfg in zip(stats_by_deck, deck_cfgs))
    new_available = sum(max(0, int(stats.get('new_count', 0))
                            - int(deck_cfg.get('_review_inflight_new', 0)))
                        for stats, deck_cfg in zip(stats_by_deck, deck_cfgs))
    first = queue_order(position, size, due_available, new_available, due_only)
    for label in (first, 'new' if first == 'due' else 'due'):
        if label == 'new' and due_only:
            continue
        suffix = suffixes[label]
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
        # The eyebrow needs to know whether this due card ever graduated, and the scheduler,
        # not our own counters, is the only thing that can say so.
        'learning': kind != 'new' and card_is_learning(api, card['cardId']),
        'meaning': meaning, 'options': options, 'source_form': source_form,
        'judgment_statement': judgment_statement, 'judgment_correct': judgment_correct,
        'answer_form': word,
        'cloze_shown': cloze_form(sentence, word) if mode == 'cloze' else '',
        'phonetic': clean_text(_field(card, '音标')),
        'roots': clean_detail(_field(card, '词根')),
        'mnemonic': question_mnemonic(card, word),
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


MASTERED_SUSPEND = 'suspend'
MASTERED_RATE = 'rate'
# Easy is Anki's own long-interval rating; the growth factor behind it belongs to the deck
# config, which is exactly why the plug-in does not pick an interval here.
RATE_EASE_FOR_MASTERED = 4


def mastered_action(cfg):
    """What 「已掌握」 does: park the card out of the schedule, or answer it with Easy.

    Suspending is the opposite of what spaced repetition claims — it declares the word will
    never be tested again. The rate mode hands the same decision to the scheduler instead, so
    the word stays in the system, just far away. Default is suspend, because the cards already
    suspended are the user's scheduling state and no switch may move them behind his back.
    """
    return MASTERED_RATE if str((cfg or {}).get('review_mastered_action', '')).strip().lower() == 'easy' \
        else MASTERED_SUSPEND


def mark_mastered(api, cfg, question):
    """Take a word out of study, in whichever of the two ways the setting says.

    Suspend is the lever Anki itself honours, and every card query here already excludes
    suspended cards, so the word stops appearing at once and stays fully reversible. The tag
    is what makes the decision findable later: everything marked here can be recovered with
    one browser search instead of a guess. In rate mode nothing is suspended and the card is
    answered with Easy, which is the same judgement expressed in the scheduler's language.
    """
    card_id = question['card_id']
    notes = [item.get('note') for item in (api('cardsInfo', {'cards': [card_id]}) or []) if item.get('note')]
    if mastered_action(cfg) == MASTERED_RATE:
        result = api('answerCards', {'answers': [{'cardId': card_id, 'ease': RATE_EASE_FOR_MASTERED}]})
        if result != [True]:
            raise ValueError('Anki 没有确认这次 Easy 评分，单词没有被标记为已掌握。')
    else:
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
