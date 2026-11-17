"""Per-review request state, kept separate from the persistent add-on config.

The first implementation passed `_review_exclude_cards`, `_review_inflight_new` and
friends through the same dictionary as user settings.  That made a prefetch thread and
a rating thread share mutable transport state.  This object is the single place those
per-request values are read; old callers that still pass the underscore keys are
accepted at the migration boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping


def _frozen(value: Any) -> frozenset:
    if value is None:
        return frozenset()
    try:
        return frozenset(value)
    except TypeError:
        return frozenset((value,))


@dataclass
class ReviewRequest:
    exclude_card: int | None = None
    exclude_cards: frozenset = field(default_factory=frozenset)
    exclude_words: frozenset = field(default_factory=frozenset)
    recent_words: frozenset = field(default_factory=frozenset)
    group_position: int = 0
    group_size: int = 0
    inflight_new: int = 0
    inflight_due: int = 0
    prefetch: bool = False
    capture_lookup_cache: dict | None = None
    book_decks: list | None = None
    book_decks_key: str | None = None

    @classmethod
    def from_cfg(cls, cfg: Mapping[str, Any] | None) -> "ReviewRequest":
        cfg = cfg or {}
        existing = cfg.get("_review")
        if isinstance(existing, cls):
            return existing
        position, size = (cfg.get("_review_group") or (0, 0))[:2]
        return cls(
            exclude_card=cfg.get("_review_exclude_card"),
            exclude_cards=_frozen(cfg.get("_review_exclude_cards")),
            exclude_words=_frozen(cfg.get("_review_exclude_words")),
            recent_words=_frozen(cfg.get("_review_recent_words")),
            group_position=int(position or 0),
            group_size=int(size or 0),
            inflight_new=int(cfg.get("_review_inflight_new") or 0),
            inflight_due=int(cfg.get("_review_inflight_due") or 0),
            prefetch=bool(cfg.get("_review_prefetch")),
            capture_lookup_cache=cfg.get("_capture_lookup_cache"),
            book_decks=cfg.get("_book_decks"),
            book_decks_key=cfg.get("_book_decks_key"),
        )

    def updated(self, **changes) -> "ReviewRequest":
        return replace(self, **changes)


def ensure_request(cfg: Mapping[str, Any]) -> ReviewRequest:
    """Return the request on ``cfg``, creating one for legacy callers.

    ``cfg`` is normally a plain dict created per call.  Keeping the object on that dict
    means `resolve_book_decks` can still cache within one request without leaking the
    cache into persistent settings.
    """
    existing = cfg.get("_review") if hasattr(cfg, "get") else None
    if isinstance(existing, ReviewRequest):
        return existing
    request = ReviewRequest.from_cfg(cfg)
    if isinstance(cfg, dict):
        cfg["_review"] = request
    return request


def request_for(cfg: Mapping[str, Any]) -> ReviewRequest:
    """Read-only accessor for callers that do not need to install a cache."""
    return ReviewRequest.from_cfg(cfg)
