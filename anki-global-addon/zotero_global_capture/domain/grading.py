"""Pure hint/grading arithmetic.

These functions were moved verbatim from ``review_logic`` as the first D1 seam.  They
have no Anki, Qt or I/O dependencies, so they can be tested and reused without a host.
"""

from __future__ import annotations


def letter_weight(index):
    """How much the letter at `index` is worth when a hint gives it away.

    The user's rule: 前面的字母比后面的字母权重要高. The first letter of an English word
    narrows the field of candidates far more than the next-to-last, so the value falls off
    as 1/(i+1) — cheap to compute, and it makes "one letter out of a 14-letter word" and
    "one letter out of a 5-letter word" mean different things, which a plain count cannot.
    """
    return 1.0 / (index + 1)


def hint_share(revealed, letters):
    """The position-weighted fraction of the word that letter hints already gave away."""
    if letters <= 0 or not revealed:
        return 0.0
    total = sum(letter_weight(index) for index in range(letters))
    given = sum(letter_weight(index) for index in revealed if 0 <= index < letters)
    return given / total


# Bands chosen so that one early letter of a long word is still a good recall (Good), the
# first letter of a short word is a real give-away (Hard), and a late letter barely counts.
HINT_SHARE_BANDS = ((0.20, 4), (0.40, 3), (0.70, 2))


def ease_from_hint_share(share):
    for limit, ease in HINT_SHARE_BANDS:
        if share <= limit:
            return ease
    return 1
