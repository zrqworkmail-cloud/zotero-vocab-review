"""Select and grade vocabulary cards through AnkiConnect."""

import html
import random
import re
from html.parser import HTMLParser


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


def answer_matches(expected, actual):
    normalize = lambda value: re.sub(r'\s+', ' ', str(value or '').strip()).casefold()
    return bool(normalize(expected)) and normalize(expected) == normalize(actual)


def should_style_card(deck, model, kind, cfg):
    return (bool(cfg.get('review_beautify', True)) and kind in ('reviewQuestion', 'reviewAnswer') and
            (deck == cfg['deck'] or deck.startswith(cfg['deck'] + '::')) and model == cfg['model'])


def _search(cfg):
    escape = lambda value: str(value).replace('\\', '\\\\').replace('"', '\\"')
    return 'deck:"%s" note:"%s" -is:suspended -is:buried' % (escape(cfg['deck']), escape(cfg['model']))


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
            (deck == cfg['deck'] or deck.startswith(cfg['deck'] + '::')) and
            bool(clean_text(_field(card, cfg['front_field']))) and
            bool(clean_text(_field(card, cfg['back_field']))))


def _weight(card, cfg):
    text = _field(card, cfg['back_field'])
    matches = re.findall(r'(?:Zotero 收录次数|全局划词收录次数|Global capture count)\s*[:：]\s*(\d+)', text, re.I)
    return min(5, max([1] + [int(value) for value in matches]))


def _cards(api, ids, cfg, limit=80):
    if not ids:
        return []
    return [item for item in (api('cardsInfo', {'cards': ids[:limit]}) or []) if _eligible(item, cfg)]


def prepare_question(api, cfg, mode='mixed', rng=random):
    profile = api('getActiveProfile', {})
    stats = _stats(api, cfg['deck'])
    base = _search(cfg)
    card = None
    kind = None
    for label, allowed, suffix in (
        ('due', int(stats.get('learn_count', 0)) + int(stats.get('review_count', 0)) > 0, 'is:due'),
        ('new', int(stats.get('new_count', 0)) > 0, 'is:new'),
    ):
        if not allowed:
            continue
        ids = api('findCards', {'query': base + ' ' + suffix}) or []
        cards = _cards(api, ids, cfg)
        if cards:
            card = rng.choices(cards, weights=[_weight(item, cfg) for item in cards], k=1)[0]
            kind = label
            break
    if card is None:
        return None

    word = clean_text(_field(card, cfg['front_field']))
    meaning = clean_text(_field(card, cfg['back_field']))
    if mode == 'mixed':
        mode = rng.choice(('choice', 'typing'))
    options = []
    if mode == 'choice':
        ids = api('findCards', {'query': base}) or []
        others = [cid for cid in ids if cid != card['cardId']]
        others = rng.sample(others, min(60, len(others)))
        meanings = []
        seen = {meaning.casefold()}
        prefixes = {meaning[:30].casefold()}
        for other in _cards(api, others, cfg):
            value = clean_text(_field(other, cfg['back_field']))
            if value and value.casefold() not in seen and value[:30].casefold() not in prefixes:
                meanings.append(value)
                seen.add(value.casefold())
                prefixes.add(value[:30].casefold())
        if len(meanings) >= 3:
            options = [meaning] + rng.sample(meanings, 3)
            rng.shuffle(options)
        else:
            mode = 'typing'

    return {
        'profile': profile, 'card_id': card['cardId'], 'kind': kind, 'mode': mode, 'word': word,
        'meaning': meaning, 'options': options,
        'phonetic': clean_text(_field(card, '音标')),
        'example': clean_text(_field(card, '例句')),
        'literature': clean_text(_field(card, '权威例句')),
        'snapshot': {key: card.get(key) for key in ('queue', 'due', 'reps', 'mod')},
    }


def submit_review(api, cfg, question, ease):
    if ease not in (1, 3, 4):
        raise ValueError('无效的复习评分。')
    if api('getActiveProfile', {}) != question['profile']:
        raise ValueError('Anki 账户已切换，这张卡片不会被评分。')
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
    result = api('answerCards', {'answers': [{'cardId': question['card_id'], 'ease': ease}]})
    if result != [True]:
        raise ValueError('Anki 没有确认保存评分，请检查 Anki 后再试。')
