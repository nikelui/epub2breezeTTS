"""Chunk ending types and configurable silence durations."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path

# Default silence durations, in seconds.
#
# These represent additional silence inserted between WAV files,
# not the total audible pause (which may include silence already
# present in the synthesized audio).

DEFAULT_PAUSES: dict[str, float] = {
    "chapter_title": 0.80,
    "dialogue_end": 0.25,
    "sentence_end": 0.12,
    "paragraph_end": 0.30,
    "chapter_end": 0.00,
    "pause": 0.08,
    "uncertain": 0.10,
}


# Accepted ending types.
ENDING_TYPES = frozenset(DEFAULT_PAUSES)


# Mapping from the boundary kinds produced by the chunker
# to their semantic ending types.
#
# Adapt this mapping if find_boundaries() uses different names.

BOUNDARY_ENDING_TYPES: dict[str, str] = {
    "chapter_end": "chapter_end",
    "chapter": "chapter_end",

    "paragraph_speaker": "dialogue_end",
    "dialogue": "dialogue_end",
    "dialogue_end": "dialogue_end",

    "paragraph": "paragraph_end",
    "paragraph_end": "paragraph_end",

    "sentence": "sentence_end",
    "sentence_end": "sentence_end",

    "comma": "pause",
    "semicolon": "pause",
    "colon": "pause",
    "pause": "pause",

    "whitespace": "uncertain",
    "forced": "uncertain",
    "end": "chapter_end",
}


def validate_ending_type(ending_type: str) -> str:
    """Return a validated ending type.

    Unknown types fall back to 'uncertain'.
    """

    if ending_type in ENDING_TYPES:
        return ending_type
    else:
        return "uncertain"


def classify_boundary_kind(kind: str) -> str:
    """Convert a chunker boundary kind into an ending type."""

    return BOUNDARY_ENDING_TYPES.get(kind, "uncertain")


def validate_pauses(
    pauses: Mapping[str, float],
) -> dict[str, float]:
    """Validate and normalize pause durations.

    Durations must be finite, nonnegative numbers.
    Unknown ending types are rejected.
    """

    validated: dict[str, float] = {}

    for ending_type, duration in pauses.items():

        if ending_type not in ENDING_TYPES:
            raise ValueError(
                f"Unknown ending type: {ending_type!r}. "
                f"Valid types: {sorted(ENDING_TYPES)}"
            )

        if isinstance(duration, bool) or not isinstance(
            duration, (int, float)
        ):
            raise TypeError(
                f"Invalid duration for {ending_type}: {duration!r}"
            )

        value = float(duration)

        if not math.isfinite(value) or value < 0:
            raise ValueError(
                f"Invalid duration for {ending_type}: {duration!r}"
            )

        validated[ending_type] = value

    return validated


def merge_pauses(
    overrides: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Combine user-provided durations with the defaults."""

    result = DEFAULT_PAUSES.copy()

    if overrides:
        result.update(validate_pauses(overrides))

    return result


def load_pause_config(
    path: str | Path,
) -> dict[str, float]:
    """Load a JSON pause configuration.

    Both formats are supported:

        {"pauses": {"dialogue_end": 0.4}}

    and:

        {"dialogue_end": 0.4}

    Unspecified values retain their defaults.
    """

    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise TypeError("Pause configuration must be a JSON object")

    overrides = data.get("pauses", data)

    if not isinstance(overrides, dict):
        raise TypeError("'pauses' must be a JSON object")

    return merge_pauses(overrides)


def get_pause_duration(
    ending_type: str | None,
    pauses: Mapping[str, float],
    fallback: float = 0.10,
) -> float:
    """Return the silence duration associated with an ending.

    If ending_type is None (older JSONL format), use fallback.

    Unknown types use the 'uncertain' duration.
    """

    if ending_type is None:
        return fallback

    normalized = validate_ending_type(ending_type)

    return float(
        pauses.get(
            normalized,
            pauses.get("uncertain", fallback),
        )
    )
