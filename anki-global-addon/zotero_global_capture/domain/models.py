"""Typed vocabulary objects shared by the capture, import and review paths.

The models are intentionally thin and dependency-free.  They describe the shapes that
currently travel as plain dictionaries, without forcing those call sites to migrate yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


def _text(value: Any) -> str:
    return str(value or "")


@dataclass(frozen=True)
class Book:
    """One study book, backed by a deck or by a tag on cards in arbitrary decks."""

    id: str
    name: str
    deck: str = ""
    tag: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "Book":
        value = value or {}
        return cls(
            id=_text(value.get("id")),
            name=_text(value.get("name")),
            deck=_text(value.get("deck")),
            tag=_text(value.get("tag")),
        )

    def to_mapping(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "deck": self.deck, "tag": self.tag}


@dataclass(frozen=True)
class SelectionEntry:
    """One ordered book selection; an empty tag tuple means the whole book.

    ``book_mapping`` keeps the catalogue dictionary that produced the typed ``Book`` so
    serialization returns the same dictionary at the boundary while the rest of the code
    starts using the model.  It is deliberately excluded from equality.  ``untagged_exclude``
    is the runtime vocabulary injected by ``current_entries``; it stays optional so a saved
    selection is still serialized without the internal key.
    """

    book: Book
    tags: tuple[str, ...] = ()
    untagged_exclude: tuple[str, ...] = ()
    book_mapping: dict[str, Any] | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "SelectionEntry":
        value = value or {}
        raw_book = value.get("book")
        if isinstance(raw_book, Mapping):
            book = Book.from_mapping(raw_book)
            book_mapping = raw_book if isinstance(raw_book, dict) else dict(raw_book)
        else:
            book = Book.from_mapping(None)
            book_mapping = None
        tags = tuple(
            tag for tag in (str(item).strip() for item in (value.get("tags") or ()))
            if tag
        )
        exclude = value.get("_untagged_exclude")
        if exclude is None:
            exclude = value.get("untagged_exclude")
        untagged_exclude = tuple(
            tag for tag in (str(item).strip() for item in (exclude or ()))
            if tag
        )
        return cls(book=book, tags=tags, untagged_exclude=untagged_exclude,
                   book_mapping=book_mapping)

    @classmethod
    def coerce(cls, value: "SelectionEntry | Mapping[str, Any] | None") -> "SelectionEntry":
        return value if isinstance(value, cls) else cls.from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        book = self.book_mapping if self.book_mapping is not None else self.book.to_mapping()
        result = {"book": book, "tags": list(self.tags)}
        if self.untagged_exclude:
            result["_untagged_exclude"] = list(self.untagged_exclude)
        return result


@dataclass(frozen=True)
class NoteDraft:
    """A vocabulary note before it is written to Anki.

    ``fields`` is for optional note-type fields (例句/音标/…); ``front`` and ``back``
    stay explicit because every import/capture path needs them.
    """

    front: str
    back: str
    fields: Mapping[str, str] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    deck: str = ""
    model: str = ""
    source: str = ""
