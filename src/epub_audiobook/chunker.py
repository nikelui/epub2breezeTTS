"""Split long paragraphs in speech-friendly chunks of text."""

import re

from .models import Chunk, Paragraph

# Match a punctuation boundary followed by whitespace, or the
# end of the paragraph. Keep punctuation in the preceding chunk.
SENTENCE_END = re.compile(r"""[.!?…]["'”’)\]]*(?=\s|$)""")
PAUSE_END = re.compile(r"""[,;:]["'”’)\]]*(?=\s|$)""")


def split_text(
    text: str,
    max_chars: int = 400,
    min_chars: int = 180,
) -> list[tuple[str, int, int]]:
    """
    Return (chunk_text, start_offset, end_offset) tuples.

    Offsets refer to the original input string. No text is intentionally
    discarded. The limits are soft when a sentence is indivisible.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if min_chars < 0 or min_chars > max_chars:
        raise ValueError("min_chars must be between 0 and max_chars")

    if not text.strip():
        return []

    chunks = []
    start = 0
    length = len(text)

    while start < length:
        # The remaining text fits into a single chunk.
        if length - start <= max_chars:
            end = length
        else:
            limit = start + max_chars

            # Prefer sentence endings, then weaker punctuation.
            candidates = [
                m.end()
                for m in SENTENCE_END.finditer(text, start, limit + 1)
                if m.end() > start + min_chars
            ]

            if not candidates:
                candidates = [
                    m.end()
                    for m in PAUSE_END.finditer(text, start, limit + 1)
                    if m.end() > start + min_chars
                ]

            if candidates:
                end = candidates[-1]
            else:
                # Find a whitespace boundary near the maximum.
                end = text.rfind(" ", start + 1, limit + 1)

                if end <= start:
                    # A long unbroken token: use a hard split.
                    end = limit

        # Trim only boundary whitespace; preserve source offsets.
        raw_start, raw_end = start, end
        while raw_start < raw_end and text[raw_start].isspace():
            raw_start += 1
        while raw_end > raw_start and text[raw_end - 1].isspace():
            raw_end -= 1

        if raw_start < raw_end:
            chunks.append(
                (text[raw_start:raw_end], raw_start, raw_end)
            )

        start = end

        # Skip whitespace between chunks without losing spoken text.
        while start < length and text[start].isspace():
            start += 1

    return chunks


def chunk_paragraph(
    paragraph: Paragraph,
    max_chars: int = 400,
    min_chars: int = 180,
) -> None:
    parts = split_text(paragraph.text, max_chars, min_chars)

    paragraph.chunks = [
        Chunk(
            id=f"{paragraph.id}-c{i:04d}",
            index=i,
            text=text,
            start_char=start,
            end_char=end,
        )
        for i, (text, start, end) in enumerate(parts, start=1)
    ]
