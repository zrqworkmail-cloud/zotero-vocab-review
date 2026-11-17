"""Ports (protocols) between application logic and host adapters.

The application layer should depend on these shapes, not on AnkiConnect's HTTP API or
Anki's in-process collection.  No implementation is imported here.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence


class CollectionPort(Protocol):
    """The read/write surface the review application depends on.

    The three read methods below return raw AnkiConnect results (card ids, or the
    ``(learned, total)`` pair) and are the first query strings moved out of
    ``review_logic``.  ``__call__`` remains for actions that have not migrated yet.
    """

    def __call__(
        self,
        action: str,
        params: Mapping[str, Any] | None = None,
        timeout: int | None = None,
    ) -> Any:
        ...

    def suspended_card_ids(self, entries: Sequence[Mapping[str, Any]]) -> Any:
        ...

    def due_card_ids(self, entries: Sequence[Mapping[str, Any]] | None = None) -> Any:
        ...

    def progress_counts(
        self,
        model: str,
        entries: Sequence[Mapping[str, Any]],
    ) -> tuple[int, int]:
        ...

    def search_query(
        self,
        model: str,
        deck: str,
        entries: Sequence[Mapping[str, Any]],
        fallback_book: Mapping[str, Any] | None = None,
        all_decks: bool = False,
    ) -> str:
        ...

    def availability_reads(self, searches: Sequence[tuple[str, str]]) -> Any:
        ...


class BatchCollectionPort(CollectionPort, Protocol):
    """Optional batched-read capability.

    AnkiConnect exposes ``multi``; an in-process adapter may implement the same method
    with a loop.  Callers should fall back to sequential ``__call__`` when it is absent.
    """

    def multi(self, actions: Sequence[Mapping[str, Any]]) -> Any:
        ...


class SchedulerPort(CollectionPort, Protocol):
    """The one write operation the review UI needs from the scheduler."""

    def answer_card(self, card_id: int, ease: int) -> Any:
        ...


class DictionaryPort(Protocol):
    """A word lookup source (e.g. Youdao) used for optional enrichment."""

    def __call__(self, word: str) -> Mapping[str, Any]:
        ...
