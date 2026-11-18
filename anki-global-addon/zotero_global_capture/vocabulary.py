"""Application service for turning a NoteDraft into an Anki note.

The capture path and the three import paths used to build almost identical note
payloads by hand.  Field escaping, empty optional fields, tags, deck/model selection
and the addNote/addNotes envelope now live here.  Source-specific extraction stays in
the importer; this module only owns the write shape.
"""
from __future__ import annotations

import html
from typing import Any, Iterable, Mapping, Sequence

from .domain.models import NoteDraft


def field_value(value: Any, preserve_html: bool = False) -> str:
    """Escape a user-facing value exactly the way the old writers did.

    The only intentional exception is the speaker link the capture path stores in a
    field: it is already an anchor tag and must not be escaped into visible text.
    """
    text = str(value or "")
    if preserve_html and text.startswith("<a "):
        return text
    return html.escape(text).replace("\n", "<br>")


def note_values(draft: NoteDraft, cfg: Mapping[str, Any], field_names: Sequence[str],
                preserve_html: bool = False) -> dict[str, str]:
    """Build the complete field map for one draft, including empty required fields."""
    values = {field: "" for field in field_names}
    values[cfg["front_field"]] = field_value(draft.front, preserve_html)
    values[cfg["back_field"]] = field_value(draft.back, preserve_html)
    for field, value in (draft.fields or {}).items():
        if field in values and value:
            values[field] = field_value(value, preserve_html)
    return values


def note_payload(draft: NoteDraft, cfg: Mapping[str, Any], field_names: Sequence[str],
                 preserve_html: bool = False) -> dict[str, Any]:
    """The single addNote/addNotes payload shape used by every writer."""
    return {
        "deckName": draft.deck or cfg["deck"],
        "modelName": draft.model or cfg["model"],
        "fields": note_values(draft, cfg, field_names, preserve_html),
        "tags": list(draft.tags),
        "options": {"allowDuplicate": False},
    }


def note_payload_from_values(values: Mapping[str, str], deck: str, model: str,
                             tags: Iterable[str] = ()) -> dict[str, Any]:
    """Shared envelope for callers that already built an escaped field map.

    The capture path updates an existing note in place, but its new-note branch still
    needs exactly the same addNote envelope as the importers.  Keeping that last step
    here prevents the envelope from drifting again.
    """
    return {
        "deckName": deck,
        "modelName": model,
        "fields": dict(values),
        "tags": list(tags),
        "options": {"allowDuplicate": False},
    }


def add_note(api, draft: NoteDraft, cfg: Mapping[str, Any], field_names: Sequence[str],
             preserve_html: bool = False) -> Any:
    return api("addNote", {"note": note_payload(draft, cfg, field_names, preserve_html)})


def add_notes(api, drafts: Iterable[NoteDraft], cfg: Mapping[str, Any],
              field_names: Sequence[str], preserve_html: bool = False) -> Any:
    notes = [note_payload(draft, cfg, field_names, preserve_html) for draft in drafts]
    if not notes:
        return []
    return api("addNotes", {"notes": notes})
