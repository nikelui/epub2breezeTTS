"""Save processed text for subsequent speech synthesis."""
import json
from pathlib import Path

from .models import Book


def save_project(book: Book, output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "title": book.title,
        "authors": book.authors,
        "language": book.language,
        "identifier": book.identifier,
        "publisher": book.publisher,
        "description": book.description,
        "chapter_count": len(book.chapters),
        "paragraph_count": sum(
            len(ch.paragraphs) for ch in book.chapters
        ),
        "chunk_count": sum(
            len(p.chunks)
            for ch in book.chapters
            for p in ch.paragraphs
        ),
    }

    with (output_dir / "book.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    with (output_dir / "chunks.jsonl").open(
        "w", encoding="utf-8"
    ) as f:
        for ch, chapter in enumerate(book.chapters):
            raw_dir = output_dir / "raw_text" / f"ch{ch:03d}"
            raw_dir.mkdir(parents=True, exist_ok=True)
            with (raw_dir / "chunks.txt").open(
                  'w', encoding="utf-8") as raw:
                for paragraph in chapter.paragraphs:
                    for chunk in paragraph.chunks:
                        record = {
                            "id": chunk.id,
                            "chapter_id": chapter.id,
                            "chapter_index": chapter.index,
                            "chapter_title": chapter.title,
                            "paragraph_id": paragraph.id,
                            "paragraph_index": paragraph.index,
                            "chunk_index": chunk.index,
                            "text": chunk.text,
                            "start_char": chunk.start_char,
                            "end_char": chunk.end_char,
                        }
                        f.write(
                            json.dumps(record, ensure_ascii=False) + "\n"
                        )
                        raw.write(chunk.text + '\n')
