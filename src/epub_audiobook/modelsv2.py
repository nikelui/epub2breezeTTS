from dataclasses import asdict, dataclass, field


@dataclass
class SourceSpan:
    """
    Identifies the portion of an original paragraph
    included in a chunk.

    Offsets are relative to Paragraph.text.
    """

    paragraph_id: str
    start_char: int
    end_char: int


@dataclass
class Chunk:
    """
    A continuous segment of text intended for TTS.
    """

    id: str
    index: int

    # Readable text, before pronunciation substitutions.
    text: str

    # Text actually passed to the TTS engine.
    tts_text: str | None = None

    # Original paragraph locations.
    sources: list[SourceSpan] = field(default_factory=list)


@dataclass
class Paragraph:
    """
    A paragraph extracted from the EPUB.
    """

    id: str
    index: int
    text: str


@dataclass
class Chapter:
    id: str
    index: int
    title: str
    source_href: str

    paragraphs: list[Paragraph] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)


@dataclass
class Book:
    title: str

    authors: list[str] = field(default_factory=list)
    language: str | None = None
    identifier: str | None = None
    publisher: str | None = None
    description: str | None = None

    chapters: list[Chapter] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
