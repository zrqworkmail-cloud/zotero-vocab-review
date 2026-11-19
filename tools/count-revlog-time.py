"""Count zero/non-zero ``revlog.time`` entries through AnkiConnect.

Read-only: this tool only calls ``findCards`` and ``getReviewsOfCards``.  It never
writes a review, changes a config, or opens the collection with SQLite while Anki is
running.

Examples
--------
    python tools/count-revlog-time.py
    python tools/count-revlog-time.py --limit 30
    python tools/count-revlog-time.py --limit 30 --since 2026-11-17T17:16:49+08:00
    python tools/count-revlog-time.py --since 1794907009000

``--since`` accepts an ISO date/time, a local date, epoch milliseconds, or epoch
seconds.  A naive date/time is interpreted in the machine's local timezone.  The
script reports the actual number of entries; if fewer than ``--limit`` exist it says
so instead of silently padding the sample.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

DEFAULT_URL = 'http://127.0.0.1:8765'
MAX_WINDOW_DAYS = 36500
WINDOW_DAYS = (1, 7, 30, 365, 3650, MAX_WINDOW_DAYS)


class AnkiConnectError(RuntimeError):
    """AnkiConnect is unreachable or returned an error payload."""


@dataclass(frozen=True)
class Review:
    review_id: int
    card_id: int
    time_ms: int
    ease: int | None = None
    kind: int | None = None


def connect(action: str, params: dict[str, Any] | None = None,
            url: str = DEFAULT_URL, timeout: float = 30.0) -> Any:
    """Call one AnkiConnect action, bypassing any system HTTP proxy."""
    body = json.dumps(
        {'action': action, 'version': 6, 'params': params or {}},
        ensure_ascii=False,
    ).encode('utf-8')
    request = urllib.request.Request(
        url, data=body, headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception as error:
        raise AnkiConnectError('%s: %s' % (type(error).__name__, error)) from error
    if payload.get('error'):
        raise AnkiConnectError(str(payload['error']))
    return payload.get('result')


def parse_since(value: str) -> tuple[int, datetime]:
    """Return (epoch milliseconds, the same instant keeping the given offset)."""
    text = value.strip()
    if not text:
        raise ValueError('--since cannot be empty')

    if re.fullmatch(r'\d+(?:\.\d+)?', text):
        number = float(text)
        # Accept seconds, milliseconds, and (for completeness) microseconds.
        if number < 10_000_000_000:
            number *= 1000
        elif number > 10_000_000_000_000:
            number /= 1000
        milliseconds = int(number)
        return milliseconds, datetime.fromtimestamp(milliseconds / 1000).astimezone()

    iso = text[:-1] + '+00:00' if text.endswith(('Z', 'z')) else text
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        parsed = None
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(
                '--since must be an ISO date/time, local date, epoch seconds, '
                'or epoch milliseconds')

    if parsed.tzinfo is None:
        # A date/time typed without an offset means the user's local clock.
        parsed = parsed.astimezone()
    # Keep the offset the value was written with. Normalising to the machine's
    # timezone made the same command describe a different calendar day on a runner
    # whose clock is UTC, which moved the candidate window and turned the pinned
    # +08:00 assertion into a red build.
    return int(parsed.timestamp() * 1000), parsed


def window_days_for_since(since: datetime, now: datetime) -> int:
    """Cover the calendar-day window Anki's ``rated:N`` search uses."""
    days = (now.date() - since.date()).days + 1
    return max(1, min(MAX_WINDOW_DAYS, days))


def fetch_reviews(card_ids: Iterable[int], url: str, timeout: float) -> list[Review]:
    """Read all revlog entries for the supplied card ids, in bounded batches."""
    cards = [int(card_id) for card_id in card_ids]
    reviews: list[Review] = []
    for start in range(0, len(cards), 500):
        chunk = cards[start:start + 500]
        if not chunk:
            continue
        payload = connect('getReviewsOfCards', {'cards': chunk}, url, timeout)
        if not isinstance(payload, dict):
            raise AnkiConnectError('getReviewsOfCards returned a non-object result')
        for card_key, rows in payload.items():
            try:
                card_id = int(card_key)
            except (TypeError, ValueError):
                continue
            for row in rows or []:
                try:
                    review_id = int(row['id'])
                    time_ms = int(row.get('time') or 0)
                except (KeyError, TypeError, ValueError):
                    continue
                ease = row.get('ease')
                kind = row.get('type')
                reviews.append(Review(
                    review_id=review_id,
                    card_id=card_id,
                    time_ms=time_ms,
                    ease=int(ease) if ease is not None else None,
                    kind=int(kind) if kind is not None else None,
                ))
    return reviews


def reviews_in_window(days: int, url: str, timeout: float) -> list[Review]:
    """All revlog entries for cards with at least one review in the last N days."""
    card_ids = connect('findCards', {'query': 'rated:%d' % days}, url, timeout)
    if not isinstance(card_ids, list):
        raise AnkiConnectError('findCards returned a non-list result')
    return fetch_reviews(card_ids, url, timeout)


def choose_reviews(limit: int, since_ms: int | None, since_local: datetime | None,
                   now: datetime, url: str, timeout: float) -> tuple[list[Review], int | None]:
    """Return (newest entries, window_days).  Expand the window until enough data."""
    if limit == 0:
        days = MAX_WINDOW_DAYS
        entries = reviews_in_window(days, url, timeout)
        if since_ms is not None:
            entries = [entry for entry in entries if entry.review_id >= since_ms]
        return sorted(entries, key=lambda entry: entry.review_id, reverse=True), days

    if since_local is not None and since_ms is not None:
        days = window_days_for_since(since_local, now)
        entries = reviews_in_window(days, url, timeout)
        entries = [entry for entry in entries if entry.review_id >= since_ms]
        entries.sort(key=lambda entry: entry.review_id, reverse=True)
        return entries[:limit], days

    # No lower bound: start with today and widen until the requested number exists.
    entries: list[Review] = []
    used_days = WINDOW_DAYS[0]
    for days in WINDOW_DAYS:
        used_days = days
        entries = reviews_in_window(days, url, timeout)
        if len(entries) >= limit or days == MAX_WINDOW_DAYS:
            break
    entries.sort(key=lambda entry: entry.review_id, reverse=True)
    return entries[:limit], used_days


def print_report(entries: list[Review], requested_limit: int, window_days: int | None,
                 since_local: datetime | None) -> None:
    zero = sum(1 for entry in entries if entry.time_ms == 0)
    nonzero = len(entries) - zero
    distinct_cards = len({entry.card_id for entry in entries})
    times = [entry.time_ms for entry in entries]

    print('source=AnkiConnect')
    print('since=%s' % (since_local.isoformat(timespec='seconds')
                        if since_local is not None else 'none'))
    print('window_days=%s' % (window_days if window_days is not None else 'n/a'))
    print('requested_limit=%d' % requested_limit)
    print('total=%d' % len(entries))
    print('zero=%d' % zero)
    print('nonzero=%d' % nonzero)
    print('distinct_cards=%d' % distinct_cards)
    if times:
        print('time_ms_min=%d' % min(times))
        print('time_ms_max=%d' % max(times))
    if requested_limit and len(entries) < requested_limit:
        print('shortfall=%d' % (requested_limit - len(entries)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--limit', type=int, default=30,
                        help='number of newest revlog entries to inspect; 0 means all (default: 30)')
    parser.add_argument('--since',
                        help='only entries at/after this time: ISO date/time, local date, '
                             'epoch seconds, or epoch milliseconds')
    parser.add_argument('--url', default=DEFAULT_URL, help='AnkiConnect endpoint')
    parser.add_argument('--timeout', type=float, default=30.0, help='HTTP timeout in seconds')
    args = parser.parse_args(argv)

    if args.limit < 0:
        parser.error('--limit must be >= 0')
    if args.timeout <= 0:
        parser.error('--timeout must be > 0')

    now = datetime.now().astimezone()
    since_ms = None
    since_local = None
    if args.since:
        try:
            since_ms, since_local = parse_since(args.since)
        except ValueError as error:
            parser.error(str(error))

    try:
        entries, window_days = choose_reviews(
            args.limit, since_ms, since_local, now, args.url, args.timeout)
    except AnkiConnectError as error:
        print('error: %s' % error, file=sys.stderr)
        return 2

    print_report(entries, args.limit, window_days, since_local)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
