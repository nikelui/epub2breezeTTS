from dataclasses import asdict, dataclass, field
from pathlib import Path


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
class Boundary:
    position: int
    kind: str
    score: float = 0.0

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

@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    def __post_init__(self):
        object.__setattr__(
            self,
            "root",
            Path(self.root).expanduser().resolve(),
        )

    @property
    def metadata(self) -> Path:
        return self.root / "book_metadata.json"

    @property
    def paragraphs(self) -> Path:
        return self.root / "paragraphs.jsonl"

    @property
    def chunks(self) -> Path:
        return self.root / "chunks.jsonl"

    @property
    def audio(self) -> Path:
        return self.root / "audio"

    @property
    def progress(self) -> Path:
        return self.audio / "progress.json"

    def chapter_audio(self, chapter_id: str) -> Path:
        return self.audio / chapter_id

    def chunk_audio(
        self,
        chapter_id: str,
        chunk_id: str,
    ) -> Path:
        return (
            self.chapter_audio(chapter_id)
            / f"{chunk_id}.wav"
        )

    @property
    def full_chapters(self) -> Path:
        return self.audio / "full_chapters"

    @property
    def audiobook(self) -> Path:
        return self.root / "combined_audiobook.m4b"

    def create(self) -> None:
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )
