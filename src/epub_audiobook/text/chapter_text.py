"""Build chapter text while preserving offsets into original Paragraph.text."""
from dataclasses import dataclass

from epub_audiobook.models import Chapter, SourceSpan


@dataclass(frozen=True)
class ParagraphLocation:
    paragraph_id: str
    start: int  # chapter text (inclusive)
    end: int    # chapter text (exclusive)


@dataclass(frozen=True)
class ChapterText:
    text: str
    locations: tuple[ParagraphLocation, ...]

    def source_spans(self, start: int, end: int) -> list[SourceSpan]:
        if not (0 <= start <= end <= len(self.text)):
            raise ValueError('Invalid chapter offsets')
        result = []
        for loc in self.locations:
            left = max(start, loc.start)
            right = min(end, loc.end)
            if left < right:
                result.append(SourceSpan(loc.paragraph_id, left - loc.start, right - loc.start))
            if loc.start >= end:
                break
        return result


def build_chapter_text(chapter: Chapter, separator: str = '\n\n') -> ChapterText:
    parts: list[str] = []
    locations: list[ParagraphLocation] = []
    pos = 0
    for paragraph in chapter.paragraphs:
        # No destructive strip: all offsets still index the original paragraph.
        if not paragraph.text.strip():
            continue
        if parts:
            parts.append(separator)
            pos += len(separator)
        start = pos
        parts.append(paragraph.text)
        pos += len(paragraph.text)
        locations.append(ParagraphLocation(paragraph.id, start, pos))
    return ChapterText(''.join(parts), tuple(locations))
