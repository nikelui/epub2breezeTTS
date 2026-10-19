"""JSONL export compatible with chapter-level Chunk and SourceSpan."""
import json
from pathlib import Path

from ..models import Book


def write_chunks_jsonl(book: Book, output: str | Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8') as f:
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
