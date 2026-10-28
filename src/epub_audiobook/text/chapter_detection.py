"""Heuristics for identifying chapter and section headings."""

from __future__ import annotations

import re

from dataclasses import dataclass


NUMBER = (
    r"(?:"
    r"\d+"
    r"|[IVXLCDM]+"
    r"|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eigtheen|nineteen"
    r"|twenty"
    r")"
)

CHAPTER_PATTERNS = [
    # Chapter 1, Chapter IV, Chapter One, Ch. 12
    re.compile(
        rf"^(?:chapter|chap\.?|ch\.?)\s+{NUMBER}"
        r"(?:\b|[.:—–-])",
        re.IGNORECASE,
    ),

    # Part 1, Part II, Book Three, Volume IV
    re.compile(
        rf"^(?:part|book|volume|vol\.?)\s+{NUMBER}"
        r"(?:\b|[.:—–-])",
        re.IGNORECASE,
    ),

    # Standalone Roman numerals
    re.compile(
        r"^[IVXLCDM]+\.?$",
        re.IGNORECASE,
    ),

    # Standalone Arabic numerals
    re.compile(
        r"^\d+\.?$",
    ),

    # Front and back matter
    re.compile(
        r"^(?:"
        r"preface"
        r"|foreword"
        r"|prologue"
        r"|introduction"
        r"|epilogue"
        r"|afterword"
        r"|appendix(?:\s+[A-Z0-9]+)?"
        r"|acknowledg(?:e)?ments"
        r"|bibliography"
        r"|notes"
        r")$",
        re.IGNORECASE,
    ),
]


@dataclass(frozen=True)
class HeadingCandidate:
    text: str
    kind: str
    confidence: float


def classify_heading(
    text: str,
    tag_name: str | None = None,
) -> HeadingCandidate | None:
    """Classify a potential chapter heading."""

    normalized = " ".join(text.split())

    if not normalized:
        return None

    for pattern in CHAPTER_PATTERNS:
        if pattern.match(normalized):

            confidence = 0.75

            if tag_name in {"h1", "h2"}:
                confidence = 0.95

            elif tag_name in {"h3", "h4"}:
                confidence = 0.85

            return HeadingCandidate(
                text=normalized,
                kind="chapter",
                confidence=confidence,
            )

    return None
