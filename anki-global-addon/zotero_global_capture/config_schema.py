"""Versioned configuration migration for the add-on.

The add-on has accumulated compatibility fallbacks for old selections and motion
switches.  Those are still read, but every read now goes through this one function so a
new stored shape can be migrated once instead of being guessed at every call site.
"""
from __future__ import annotations

from typing import Any, Mapping

CURRENT_CONFIG_VERSION = 2


def _version(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def migrate(stored: Mapping[str, Any] | None, defaults: Mapping[str, Any]) -> dict[str, Any]:
    """Merge defaults and apply one-way, idempotent migrations."""
    stored = dict(stored or {})
    value = dict(defaults)
    value.update(stored)

    # v1 -> v2: an old `review_auto_example` boolean meant "show an example"; the
    # newer key distinguishes the first example from all examples.  Do not overwrite a
    # value the user has already written.
    if _version(stored.get("config_version")) < 2:
        if "review_auto_example_mode" not in stored and stored.get("review_auto_example"):
            value["review_auto_example_mode"] = "example"
    value["config_version"] = CURRENT_CONFIG_VERSION
    return value
