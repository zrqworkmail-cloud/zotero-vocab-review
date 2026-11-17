"""Pure collection-query fragments, with no transport or UI dependency.

These are the strings AnkiConnect searches by.  They live outside ``review_logic`` so
the adapter can own query assembly while the pure functions stay unit-testable without
an Anki process.
"""

from __future__ import annotations

from typing import Iterable, Mapping

try:
    from .domain.models import SelectionEntry
except ImportError:  # standalone test loader
    import sys
    from pathlib import Path

    _package_root = str(Path(__file__).resolve().parent)
    if _package_root not in sys.path:
        sys.path.insert(0, _package_root)
    from domain.models import SelectionEntry


UNTAGGED = '（无标签）'


def escape_query(value):
    return str(value).replace('\\', '\\\\').replace('"', '\\"')


def book_clause(book):
    if not book:
        return ''
    if book.get('tag'):
        return ' tag:"%s"' % escape_query(book['tag'])
    if book.get('deck'):
        return ' deck:"%s"' % escape_query(book['deck'])
    return ''


def _book_mapping(entry):
    entry = SelectionEntry.coerce(entry)
    return entry.book_mapping if entry.book_mapping is not None else entry.book.to_mapping()


def entry_clause(entry):
    """One entry's search fragment: its book, narrowed to the union of chosen tags.

    The UNTAGGED sentinel joins the union as explicit negations: "none of the other
    tags on this book's cards".  It has to remain identical to the old review_logic
    implementation; the Qt/selection tests are the behaviour contract.
    """
    entry = SelectionEntry.coerce(entry)
    book = _book_mapping(entry)
    base = book_clause(book)
    tags = entry.tags
    if not tags:
        return base
    operands = ['tag:"%s"' % escape_query(tag) for tag in tags if tag != UNTAGGED]
    if UNTAGGED in tags:
        exclude = entry.untagged_exclude
        if not exclude:
            return base
        negations = ' AND '.join('-tag:"%s"' % escape_query(tag) for tag in exclude)
        operands.append('(%s)' % negations if operands else negations)
    joined = ' OR '.join(operands)
    subset = '(%s)' % joined
    if not base.strip():
        return ' %s' % subset
    return ' %s AND %s' % (base.strip(), subset)


def selection_clause(entries):
    parts = []
    for raw_entry in entries:
        entry = SelectionEntry.coerce(raw_entry)
        part = entry_clause(entry).strip()
        if not part:
            continue
        parts.append('(%s)' % part if ' AND ' in part else part)
    if not parts:
        return ''
    if len(parts) == 1:
        return ' %s' % parts[0]
    return ' (%s)' % ' OR '.join(parts)


def clause_for(entries: Iterable[Mapping | SelectionEntry]) -> str:
    """The book/tag fragment for a whole selection, or one pinned entry."""
    entries = [SelectionEntry.coerce(entry) for entry in entries]
    if len(entries) == 1:
        return entry_clause(entries[0])
    return selection_clause(entries)


def suspended_query(entries) -> str:
    return 'is:suspended' + clause_for(entries)


def due_query(entries=None) -> str:
    return 'is:due' + (clause_for(entries) if entries else '')


def progress_queries(model: str, entries) -> list[str]:
    """Total and learned-card searches, in this order.

    ``learned`` means answered at least once: Anki's prop search takes no colon
    (``prop:reps>0``), and the response is consumed by ``progress_counts``.
    """
    base = 'note:"%s"%s -is:suspended -is:buried' % (escape_query(model), clause_for(entries))
    return [base, base + ' prop:reps>0']


def tag_query(book, tag: str) -> str:
    return '%s tag:"%s"' % (book_clause(book), escape_query(tag))


def untagged_query(book, tags) -> str:
    clause = book_clause(book) or ''
    for tag in tags or []:
        clause += ' -tag:"%s"' % escape_query(tag)
    return clause


def deck_query(model: str, book, deck: str) -> str:
    return 'deck:"%s" note:"%s"%s -is:suspended -is:buried' % (
        escape_query(deck), escape_query(model), book_clause(book))


def search_query(model: str, deck: str, entries, fallback_book=None,
                 all_decks: bool = False) -> str:
    """The query meaning "cards from this selection", inside one deck.

    The book/tag fragment is dropped only when it is provably redundant: one whole-deck
    entry and that same deck.  Otherwise the fragment stays, so a multi-词组 selection
    cannot silently match the whole deck.
    """
    deck_part = '' if all_decks else 'deck:"%s" ' % escape_query(deck)
    if (len(entries) == 1 and not entries[0]['tags']
            and entries[0]['book'].get('deck')
            and deck == entries[0]['book']['deck']):
        clause = ''
    elif entries:
        clause = clause_for(entries)
    else:
        book = fallback_book
        redundant = book and book.get('deck') and deck == book['deck']
        clause = '' if redundant else book_clause(book)
    return '%snote:"%s"%s -is:suspended -is:buried' % (
        deck_part, escape_query(model), clause)


def availability_query(base: str, kind: str) -> str:
    return base + (' is:new' if kind == 'new' else ' is:due')


CAPTURE_QUERY = 'tag:anki_global_capture or tag:zotero_vocab_review'


def capture_tag_query(base: str) -> str:
    return base + ' (' + CAPTURE_QUERY + ')'


def card_state_query(card_id) -> str:
    return 'cid:%s is:learn -is:review' % card_id


def queue_card_query(base: str, card_id, kind: str) -> str:
    return base + ' cid:%s %s' % (card_id, 'is:new' if kind == 'new' else 'is:due')


def plan_query(base: str, stage: str) -> str:
    suffix = {'new': 'is:new', 'due': 'is:due -is:new',
              'done': 'rated:1', 'introduced': 'introduced:1'}[stage]
    return base + ' ' + suffix


def deck_only_clause(deck: str) -> str:
    return 'deck:"%s"' % escape_query(deck)


def deck_limit_queries(deck: str) -> list[str]:
    clause = deck_only_clause(deck)
    return [clause + ' introduced:1', clause + ' is:new', clause + ' is:due']


def prefix_query(base: str, field: str, prefix: str) -> str:
    return base + ' "' + escape_query(field) + ':' + prefix + '*"'


def field_value_query(base: str, field: str, word: str) -> str:
    return base + ' "' + escape_query(field) + ':' + escape_query(word) + '"'
