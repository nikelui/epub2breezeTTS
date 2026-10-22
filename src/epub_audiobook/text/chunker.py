"""Chapter-level boundary-cost optimization with source mapping.

All chunk text is sliced from the original chapter buffer, never reconstructed
from segmented sentences. Only whitespace at chunk edges is omitted.
"""
from bisect import bisect_left
from dataclasses import dataclass

from epub_audiobook.models import Chapter, Chunk
from epub_audiobook.text.boundaries import Boundary, find_boundaries
from epub_audiobook.text.chapter_text import build_chapter_text


@dataclass(frozen=True)
class ChunkConfig:
    min_chars: int = 150          # soft minimum
    target_chars: int = 300       # ideal length
    max_chars: int = 500          # hard cap, except unavoidable long words
    language: str = 'en'

    def __post_init__(self) -> None:
        if not (0 <= self.min_chars <= self.target_chars <= self.max_chars):
            raise ValueError('Expected 0 <= min_chars <= target_chars <= max_chars')
        if self.max_chars <= 0:
            raise ValueError('max_chars must be positive')


def _length_cost(n: int, config: ChunkConfig) -> float:
    # Use a quadratic objective to discourage tiny tail chunks.
    deviation = (n - config.target_chars) / config.target_chars
    shortfall = max(0, config.min_chars - n) / max(config.min_chars, 1)
    return 45.0 * deviation ** 2 + 60.0 * shortfall ** 2


def _ensure_long_word_boundaries(text: str, boundaries: list[Boundary], cap: int) -> list[Boundary]:
    """Rare fallback for a token longer than max_chars; avoid endless loops."""
    found = {b.position: b for b in boundaries}
    ordered = sorted(found)
    previous = 0
    for pos in ordered:
        while pos - previous > cap:
            previous += cap
            found[previous] = Boundary(previous, 'forced', 300.0)
        previous = pos
    return sorted(found.values(), key=lambda b: b.position)


def chunk_chapter(chapter: Chapter, config: ChunkConfig | None = None) -> list[Chunk]:
    config = config or ChunkConfig()
    source = build_chapter_text(chapter)
    text = source.text
    if not text.strip():
        chapter.chunks = []
        return []

    boundaries = _ensure_long_word_boundaries(
        text, find_boundaries(source, config.language), config.max_chars
    )
    # DP only needs one position per candidate; add zero as the start.
    positions = [0] + [b.position for b in boundaries]
    boundary_cost = [0.0] + [b.penalty for b in boundaries]
    size = len(positions)
    best = [float('inf')] * size
    predecessor = [-1] * size
    best[0] = 0.0

    for j in range(1, size):
        end = positions[j]
        # Candidate chunk starts cannot be farther back than max_chars,
        # except when there is no usable split due to a long unbroken token.
        i_min = bisect_left(positions, end - config.max_chars, 0, j)
        for i in range(i_min, j):
            start = positions[i]
            segment = text[start:end]
            trimmed = segment.strip()
            if not trimmed:
                continue
            cost = best[i] + boundary_cost[j] + _length_cost(len(trimmed), config)
            if cost < best[j]:
                best[j] = cost
                predecessor[j] = i

    if predecessor[-1] < 0:
        raise RuntimeError('No valid chunking; inspect boundary construction')

    pairs: list[tuple[int, int]] = []
    j = size - 1
    while j:
        i = predecessor[j]
        if i < 0:
            raise RuntimeError('Broken chunk predecessor chain')
        pairs.append((positions[i], positions[j]))
        j = i
    pairs.reverse()

    chunks: list[Chunk] = []
    for start, end in pairs:
        # Preserve original source offsets; only trim chunk-edge whitespace.
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start == end:
            continue
        n = len(chunks) + 1
        content = text[start:end]
        chunks.append(Chunk(
            id=f'{chapter.id}-c{n:06d}',
            index=n,
            text=content,
            tts_text=content,
            sources=source.source_spans(start, end),
        ))
    chapter.chunks = chunks
    return chunks
