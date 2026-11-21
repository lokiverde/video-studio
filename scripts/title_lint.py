"""Title warnings at kit time. Warnings only: never an error, never an edit, Tony keeps the
final say. Rules come from the 2026-10-22 channel data (SKILL.md "What gets watched"):
winners carry a city plus a number or a question; flops are tool promos, trivia and
generic hashtag titles.
"""
from __future__ import annotations

import re

MAX_CHARS = 60
SHORTS_FRONT = 40
# The places the studio covers (the city by city series, the quiz brands, a second office).
PLACES = ("California", "Los Angeles", "LA County", "South Bay", "Westside", "Ogdenville", "Riverside",
          "Springfield", "Hermosa Beach", "Hermosa", "Manhattan Beach", "Redondo Beach", "Redondo", "Torrance",
          "El Segundo", "Carson", "Lawndale", "Shelbyville", "Palos Verdes", "San Pedro", "Wilmington",
          "Harbor City", "Long Beach", "Culver City", "Santa Monica", "Compton", "Westchester", "Sacramento",
          "Texas", "Austin", "Nevada", "Las Vegas", "Henderson")
PLACE = re.compile(r"\b(" + "|".join(re.escape(p) for p in PLACES) + r")\b", re.I)
PLACE_ABBR = re.compile(r"\bL\.?A\.?\b|\bCA\b")          # case-sensitive: never "la" or "ca"
LAW = re.compile(r"\b(AB|SB|ACA|SCA)\s?\d+|\bProp(osition)?\s?\d+|\bMeasure\s[A-Z]{1,3}\b|"
                 r"\bCosta[- ]Hawkins\b|\bEllis Act\b|\bDavis[- ]Stirling\b|\brent control\b|\bjust cause\b", re.I)
PROMO = ("best ai tool", "game changer", "game-changer", "gamechanger", "must-have ai", "must have ai",
         "you need this ai", "this ai tool", "secret ai tool", "top ai tools", "insane ai", "mind-blowing",
         "mind blowing", "ai hack")


def _searchable(text: str) -> bool:
    return bool(PLACE.search(text) or PLACE_ABBR.search(text) or LAW.search(text) or re.search(r"\d", text))


def lint(title: str, short: bool = False) -> list[str]:
    """Warnings for one title. Empty list when it is clean."""
    title = (title or "").strip()
    warnings = []
    if len(title) > MAX_CHARS:
        warnings.append(f"{len(title)} characters, over {MAX_CHARS}: YouTube cuts it in search and on phones")
    if re.search(r"#\w", title):
        warnings.append("hashtag in the title (#shorts included): hashtags go in the description, if anywhere")
    if not (re.search(r"\d", title) or "?" in title or PLACE.search(title) or PLACE_ABBR.search(title)):
        warnings.append("no number, no question and no place: winners carry a city plus a number or a question")
    if short and not _searchable(title[:SHORTS_FRONT]):
        warnings.append(f"no city, law or number in the first {SHORTS_FRONT} characters: front-load the searchable noun")
    lowered = title.lower()
    promo = [p for p in PROMO if p in lowered]
    if promo:
        warnings.append(f"tool-promo phrasing ({promo[0]!r}): tool promos are the channel's flops")
    return warnings
