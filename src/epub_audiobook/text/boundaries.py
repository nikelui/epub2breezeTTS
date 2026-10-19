"""Classify boundary opportunities; dialogue protection is deliberately heuristic."""
import re
from dataclasses import dataclass

from .chapter_text import ChapterText
from .sentence_splitter import sentence_ends


@dataclass(frozen=True)
class Boundary:
    position: int
    kind: str
    penalty: float  # smaller is better


# Scores are costs of BREAKING here, not rewards. Tunable independently of the DP.
BREAK_COST = {
    'chapter_end': 0.0,
    'paragraph_speaker': 0.0,
    'paragraph': 8.0,
    'sentence': 15.0,
    'semicolon': 32.0,
    'colon': 35.0,
    'comma': 50.0,
    'space': 90.0,
}

PAUSE_RE = re.compile(r'[,;:]["\'”’)]*(?=\s|$)')
WHITESPACE_RE = re.compile(r'\s+')
# A sentence-end before a lower-case speech tag is almost never a good split.
ATTRIBUTION_RE = re.compile(
    r'^\s*(?:he|she|they|i|we|[A-Z][a-z]+)\s+'
    r'(?:said|asked|replied|whispered|muttered|shouted|cried|answered|'
    r'demanded|added|continued|exclaimed|called|snapped)\b', re.IGNORECASE
)
OPEN_QUOTE_RE = re.compile(r'^\s*["“«‘\']')


def find_boundaries(chapter: ChapterText, language: str = 'en') -> list[Boundary]:
    text = chapter.text
    found: dict[int, Boundary] = {}

    def add(pos: int, kind: str, extra: float = 0.0) -> None:
        if not (0 < pos <= len(text)):
            return
        penalty = BREAK_COST[kind] + extra
        prev = found.get(pos)
        if prev is None or penalty < prev.penalty:
            found[pos] = Boundary(pos, kind, penalty)

    # Word boundaries are last-resort candidates, not the default splitting strategy.
    for m in WHITESPACE_RE.finditer(text):
        add(m.start(), 'space')

    for m in PAUSE_RE.finditer(text):
        kind = {';': 'semicolon', ':': 'colon', ',': 'comma'}[m.group()[0]]
        add(m.end(), kind)

    for pos in sentence_ends(text, language):
        # May be a continuation of the very same speaker's utterance.
        extra = 150.0 if ATTRIBUTION_RE.match(text[pos:pos + 100]) else 0.0
        add(pos, 'sentence', extra)

    for idx, loc in enumerate(chapter.locations[:-1]):
        nxt = chapter.locations[idx + 1]
        next_paragraph = text[nxt.start:nxt.end]
        prior_paragraph = text[loc.start:loc.end]
        likely_turn = bool(OPEN_QUOTE_RE.match(next_paragraph) and
                           OPEN_QUOTE_RE.match(prior_paragraph))
        add(loc.end, 'paragraph_speaker' if likely_turn else 'paragraph')

    add(len(text), 'chapter_end')
    return sorted(found.values(), key=lambda b: b.position)
