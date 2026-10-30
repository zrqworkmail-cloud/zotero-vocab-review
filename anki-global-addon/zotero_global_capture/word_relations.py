"""Spelling neighbours and dictionary-sourced antonyms for review cards."""
import difflib
import json
import re
import urllib.parse
import urllib.request

from .review_logic import _inflection_table


def candidate_words(text, target='', limit=30):
    result = []
    ignore = {'n', 'v', 'vt', 'vi', 'adj', 'adv', 'noun', 'verb', 'adjective', 'adverb', 'synonym', 'antonym'}
    for word in re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", str(text or '')):
        key = word.casefold()
        if key != str(target).casefold() and key not in ignore and key not in {x.casefold() for x in result}:
            result.append(word)
            if len(result) >= limit:
                break
    return result


def brief_meaning(text, limit=42):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    text = re.split(r'(?:Zotero 收录次数|全局划词收录次数|Global capture count)\s*[:：]', text, flags=re.I)[0].strip()
    if not text:
        return ''
    text = re.split(r'[；;]', text, maxsplit=1)[0].strip()
    return text if len(text) <= limit else text[:limit].rstrip() + '…'


def select_candidates(words, preferred, limit=3):
    preferred = {word.casefold() for word in preferred}
    return sorted(words, key=lambda word: word.casefold() not in preferred)[:limit]


def similar_words(word, limit=4):
    word = str(word or '').lower().strip()
    if not re.fullmatch(r'[a-z]{4,20}', word):
        return []
    table = _inflection_table()
    forms = table.get(word, set()) | {word}
    candidates = (candidate for candidate in table
                  if candidate not in forms and candidate.isascii() and candidate.isalpha()
                  and abs(len(candidate) - len(word)) <= 2)
    return difflib.get_close_matches(word, candidates, n=limit, cutoff=0.82)


def parse_words(entries, relation):
    result = []
    if not isinstance(entries, list):
        return result
    for entry in entries:
        for meaning in entry.get('meanings', []):
            words = list(meaning.get(relation) or [])
            for definition in meaning.get('definitions', []):
                words.extend(definition.get(relation) or [])
            pos = str(meaning.get('partOfSpeech') or '').strip()
            for word in words:
                if isinstance(word, str) and word.strip():
                    item = (pos, word.strip())
                    if item not in result:
                        result.append(item)
    return result[:8]


def parse_antonyms(entries):
    return parse_words(entries, 'antonyms')


def fetch_relations(word):
    if not re.fullmatch(r'[A-Za-z]{2,30}', str(word or '')):
        return {}
    url = 'https://api.dictionaryapi.dev/api/v2/entries/en/' + urllib.parse.quote(word)
    request = urllib.request.Request(url, headers={'User-Agent': 'AnkiVocabularyReview/1.0'})
    with urllib.request.urlopen(request, timeout=5) as response:
        entries = json.loads(response.read(512 * 1024).decode('utf-8'))
    return {key: parse_words(entries, key) for key in ('synonyms', 'antonyms')}


def comparison_glosses(words):
    result = []
    for word in words[:3]:
        if not re.fullmatch(r'[A-Za-z]{2,30}', word):
            continue
        url = 'https://api.dictionaryapi.dev/api/v2/entries/en/' + urllib.parse.quote(word)
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'AnkiVocabularyReview/1.0'})
            with urllib.request.urlopen(request, timeout=4) as response:
                entries = json.loads(response.read(512 * 1024).decode('utf-8'))
            for entry in entries:
                for meaning in entry.get('meanings', []):
                    definitions = meaning.get('definitions') or []
                    if definitions and definitions[0].get('definition'):
                        result.append('%s (%s): %s' % (word, meaning.get('partOfSpeech', ''), definitions[0]['definition']))
                        break
                else:
                    continue
                break
        except Exception:
            continue
    return '\n'.join(result)
