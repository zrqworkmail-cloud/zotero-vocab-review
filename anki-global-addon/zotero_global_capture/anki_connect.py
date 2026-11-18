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
        """
        if elapsed_ms is not None and self._rpc is not None:
            try:
                prediction = self._rpc("scheduling.predict", {"cardId": str(card_id)})
            except Exception:
                # No mutation happened yet, so the legacy path is still safe.
                return self("answerCards", {"answers": [{"cardId": card_id, "ease": ease}]})
            token = (prediction or {}).get("stateToken")
            if token:
                rating = ("again", "hard", "good", "easy")[int(ease) - 1]
                result = self._rpc("scheduling.answer", {
                    "cardId": str(card_id),
                    "rating": rating,
                    "stateToken": token,
                    "elapsedMs": max(0, int(elapsed_ms)),
                })
                return [True] if result and result.get("cardId") else [False]
        return self("answerCards", {"answers": [{"cardId": card_id, "ease": ease}]})

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
