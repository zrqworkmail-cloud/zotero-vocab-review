"""AnkiConnect adapter for the collection port.

This is deliberately a transparent wrapper: the existing ``api(action, params, timeout)``
function remains the single transport implementation.  The adapter gives the application
layer a stable object to depend on and adds the optional ``multi`` convenience without
changing request/response semantics.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

try:
    from . import collection_queries
except ImportError:  # standalone test loader
    import sys
    from pathlib import Path

    _package_root = str(Path(__file__).resolve().parent)
    if _package_root not in sys.path:
        sys.path.insert(0, _package_root)
    import collection_queries


STALE_TOKEN_MESSAGE = 'Prediction/conversion token is stale.'


class AnkiConnectAdapter:
    """Forward collection calls to the existing AnkiConnect ``api`` function."""

    def __init__(self, request: Callable[..., Any], rpc: Callable[..., Any] | None = None):
        if not callable(request):
            raise TypeError("request must be callable")
        self._request = request
        self._rpc = rpc if callable(rpc) else None

    def __call__(
        self,
        action: str,
        params: Mapping[str, Any] | None = None,
        timeout: int | None = None,
    ) -> Any:
        # Do not pass timeout=None: the wrapped api keeps its own default (15 s), and
        # callables used in tests may accept only the two positional arguments.
        if timeout is None:
            return self._request(action, params or {})
        return self._request(action, params or {}, timeout=timeout)

    def request(
        self,
        action: str,
        params: Mapping[str, Any] | None = None,
        timeout: int | None = None,
    ) -> Any:
        return self(action, params, timeout)

    def multi(self, actions: Sequence[Mapping[str, Any]]) -> Any:
        return self("multi", {"actions": list(actions)})

    def answer_card(self, card_id: int, ease: int, elapsed_ms: int | None = None) -> Any:
        """Rate one card, preserving the measured review time when possible.

        Legacy ``answerCards`` does not accept an elapsed time, so every such review
        lands in Anki's revlog as 0 seconds.  The newer JSON-RPC scheduler endpoint
        does accept ``elapsedMs``.  Use it when a timer was measured, but fall back to
        the legacy action only *before* any write: a failed answer must never be
        retried through a second action, or one card could be graded twice.

        AnkiConnect's scheduler token includes the card's scheduling states.  For an
        overdue learning card those states contain a seconds-resolution field, so a
        prediction can become stale before the answer reaches Anki.  On that specific
        error the write was rejected before it started; verify the revlog and retry
        once with a fresh prediction.  A failed response is never assumed to mean the
        write was lost: the revlog may already contain the new entry.
        """
        if elapsed_ms is None or self._rpc is None:
            return self._legacy_answer(card_id, ease)

        before = self._latest_review_id(card_id)
        try:
            return self._scheduled_answer(card_id, ease, elapsed_ms, before)
        except Exception as raised:
            if not self._is_stale_token(raised):
                if self._has_new_review(card_id, before):
                    return [True]
                raise
            if self._has_new_review(card_id, before):
                return [True]
            # The stale-token response is a pre-write rejection.  Retry with a
            # newly predicted token, then verify the revlog again.
            try:
                return self._scheduled_answer(card_id, ease, elapsed_ms, before)
            except Exception as retry_error:
                if self._has_new_review(card_id, before):
                    return [True]
                raise retry_error

    def _scheduled_answer(self, card_id: int, ease: int, elapsed_ms: int,
                          before: int | None) -> Any:
        try:
            prediction = self._rpc("scheduling.predict", {"cardId": str(card_id)})
        except Exception:
            # No mutation happened yet, so the legacy path is still safe.
            return self._legacy_answer(card_id, ease)
        token = (prediction or {}).get("stateToken")
        if not token:
            return self._legacy_answer(card_id, ease)
        rating = ("again", "hard", "good", "easy")[int(ease) - 1]
        result = self._rpc("scheduling.answer", {
            "cardId": str(card_id),
            "rating": rating,
            "stateToken": token,
            "elapsedMs": max(0, int(elapsed_ms)),
        })
        if result and result.get("reviewId"):
            try:
                review_id = int(result["reviewId"])
            except (TypeError, ValueError):
                review_id = None
            if before is None or review_id is None or review_id > before:
                return [True]
        if result and result.get("cardId"):
            if before is None or self._has_new_review(card_id, before):
                return [True]
            return [False]
        if self._has_new_review(card_id, before):
            return [True]
        return [False]

    def _legacy_answer(self, card_id: int, ease: int) -> Any:
        return self("answerCards", {"answers": [{"cardId": card_id, "ease": ease}]})

    def _latest_review_id(self, card_id: int) -> int | None:
        """Return the newest revlog id for one card, or ``None`` if unknown."""
        try:
            values = self("getReviewsOfCards", {"cards": [card_id]})
        except Exception:
            return None
        if not isinstance(values, Mapping):
            return None
        rows = values.get(str(card_id))
        if rows is None:
            rows = values.get(card_id)
        if rows is None:
            return None
        ids = []
        for row in rows or []:
            try:
                ids.append(int(row.get("id")))
            except (AttributeError, TypeError, ValueError):
                continue
        return max(ids) if ids else 0

    def _has_new_review(self, card_id: int, before: int | None) -> bool:
        if before is None:
            return False
        after = self._latest_review_id(card_id)
        return after is not None and after > before

    @staticmethod
    def _is_stale_token(error: Exception) -> bool:
        return STALE_TOKEN_MESSAGE.lower() in str(error).lower()

    def _find_cards(self, queries: Sequence[str]) -> list[Any]:
        """Run independent searches in one batch, with the same sequential fallback."""
        return self._multi_or_sequential(
            [("findCards", {"query": query}) for query in queries])

    def _multi_or_sequential(self, actions: Sequence[tuple[str, Mapping[str, Any]]]) -> list[Any]:
        actions = list(actions)
        try:
            batch = getattr(self._request, 'multi', None)
            payload = [{"action": action, "params": params}
                       for action, params in actions]
            answers = batch(payload) if callable(batch) else self.multi(payload)
            if isinstance(answers, list) and len(answers) == len(actions):
                return answers
        except Exception:
            pass
        return [self(action, params) for action, params in actions]

    @staticmethod
    def search_query(model: str, deck: str, entries,
                     fallback_book=None, all_decks: bool = False) -> str:
        return collection_queries.search_query(model, deck, entries, fallback_book, all_decks)

    def availability_reads(self, searches: Sequence[tuple[str, str]]) -> list[Any]:
        actions = []
        for deck, base in searches:
            actions.extend([
                ("getDeckStats", {"decks": [deck]}),
                ("findCards", {"query": collection_queries.availability_query(base, "new")}),
                ("findCards", {"query": collection_queries.availability_query(base, "due")}),
            ])
        return self._multi_or_sequential(actions)

    def suspended_card_ids(self, entries: Sequence[Mapping[str, Any]]) -> Any:
        return self("findCards", {"query": collection_queries.suspended_query(entries)}) or []

    def due_card_ids(self, entries: Sequence[Mapping[str, Any]] | None = None) -> Any:
        return self("findCards", {"query": collection_queries.due_query(entries)}) or []

    def progress_counts(self, model: str,
                        entries: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
        total_ids, learned_ids = self._find_cards(
            collection_queries.progress_queries(model, entries))
        return (len(learned_ids or []), len(total_ids or []))

    def tag_card_ids(self, book: Mapping[str, Any], tags: Sequence[str]) -> Any:
        actions = [{"action": "findCards",
                    "params": {"query": collection_queries.tag_query(book, tag)}}
                   for tag in tags]
        return self("multi", {"actions": actions}) or []

    def untagged_card_ids(self, book: Mapping[str, Any], tags: Sequence[str]) -> Any:
        return self("findCards",
                    {"query": collection_queries.untagged_query(book, tags)}) or []

    def deck_names(self) -> Any:
        return self("deckNames", {}) or []

    def deck_card_ids(self, model: str, book: Mapping[str, Any],
                      decks: Sequence[str]) -> Any:
        return self._find_cards(
            [collection_queries.deck_query(model, book, deck) for deck in decks])

    def __repr__(self) -> str:
        return "AnkiConnectAdapter()"
