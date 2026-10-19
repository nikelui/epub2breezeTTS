"""Contains object definitions for book, chapter, paragraph and chunks"""
from dataclasses import asdict, dataclass, field


@dataclass
class Chunk:
    id: str
    index: int
    text: str
    start_char: int
    end_char: int


@dataclass
class Paragraph:
    id: str
    index: int
    text: str
    chunks: list[Chunk] = field(default_factory=list)


@dataclass
class Chapter:
    id: str
    index: int
    title: str
    source_href: str
    paragraphs: list[Paragraph] = field(default_factory=list)


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
