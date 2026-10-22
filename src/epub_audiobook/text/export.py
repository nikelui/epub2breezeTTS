"""JSONL export compatible with chapter-level Chunk and SourceSpan."""
import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from epub_audiobook.models import Book, ProjectPaths


def _atomic_write_json(destination: Path, payload: dict) -> None:
    """Write metadata completely before replacing an existing version."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n",
            dir=destination.parent, prefix=f".{destination.name}.",
            suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def write_chunks_jsonl(book: Book, output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    output = ProjectPaths(output_dir)
    output.create()
    with output.chunks.open('w', encoding='utf-8') as f:
        for chapter in book.chapters:
            for chunk in chapter.chunks:
                row = {
                    'id': chunk.id,
                    'chapter_id': chapter.id,
                    'chapter_index': chapter.index,
                    'chapter_title': chapter.title,
                    'chunk_index': chunk.index,
                    'text': chunk.text,
                    'tts_text': chunk.tts_text,
                    'sources': [vars(span) for span in chunk.sources],
                }
                f.write(json.dumps(row, ensure_ascii=False) + '\n')

def write_metadata_json(book: Book, destination: Path) -> None:
    """Export compact book metadata, excluding all paragraph and chunk text."""
    payload = {
        "schema_version": 1,
        "title": book.title,
        "authors": list(book.authors),
        "language": book.language,
        "identifier": book.identifier,
        "publisher": book.publisher,
        "description": book.description,
        "chapters": [
            {
                "id": chapter.id,
                "index": chapter.index,
                "title": chapter.title,
                "source_href": chapter.source_href,
                "paragraph_count": len(chapter.paragraphs),
                "chunk_count": len(chapter.chunks),
            }
            for chapter in book.chapters
        ],
    }
    _atomic_write_json(Path(destination), payload)


def write_paragraphs_jsonl(book: Book, destination: Path) -> None:
    """Write one source paragraph per line; never write its generated chunks."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n",
            dir=destination.parent, prefix=f".{destination.name}.",
            suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            for chapter in book.chapters:
                for paragraph in chapter.paragraphs:
                    record = {
                        "id": paragraph.id,
                        "chapter_id": chapter.id,
                        "chapter_index": chapter.index,
                        "paragraph_index": paragraph.index,
                        "text": paragraph.text,
                    }
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
