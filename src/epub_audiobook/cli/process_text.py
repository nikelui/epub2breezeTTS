import argparse  # noqa: I001
from pathlib import Path
from epub_audiobook.models import Book

from epub_audiobook.text.epub_reader import read_epub, inspect_epub_structure
from epub_audiobook.text.chunker import ChunkConfig, chunk_chapter
from epub_audiobook.text.export import (
    write_chunks_jsonl, write_metadata_json, write_paragraphs_jsonl)

def add_subparser(subparsers):
    parser = subparsers.add_parser('process_text', help='Process EPUB text and chunk it')
    parser.add_argument("epub", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("output/"))
    parser.add_argument("--max-chars", type=int, default=400)
    parser.add_argument("--target-chars", type=int, default=300)
    parser.add_argument("--min-chars", type=int, default=150)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--book-structure", action="store_true")

    parser.set_defaults(handler=main)

def process_text(epub_path:Path, output_dir: Path, chunk_config) -> Book:
    """Extract text from epub and save relevant metadata, paragraphs and text chunks."""
    paths = Path(output_dir)

    # 1. Extract book structure and text
    book = read_epub(epub_path)

    # 2. Preserve original paragraphs
    write_paragraphs_jsonl(book, paths)

    # 3. Generate chapter-level chunks
    for chapter in book.chapters:
        chunk_chapter(chapter, chunk_config)

    # 4. Export generated chunks
    write_chunks_jsonl(book, paths)

    # 5. Export compact metadata
    write_metadata_json(book, paths)

    return book

def main(args: argparse.Namespace):

    # Debug option
    if args.book_structure:
        inspect_epub_structure(args.epub)
        return

    config = ChunkConfig(
        min_chars = args.min_chars,
        target_chars = args.target_chars,
        max_chars = args.max_chars,
    )

    book = process_text(args.epub, args.output_dir, config)

    if args.verbose:
        print(f"Title: {book.title}")
        print(f"Authors: {', '.join(book.authors) or 'Unknown'}")
        print(f"Language: {book.language or 'Unknown'}")
        print(f"Chapters: {len(book.chapters)}")
        print(
            "Paragraphs:",
            sum(len(ch.paragraphs) for ch in book.chapters),
        )
        for ch, chapter in enumerate(book.chapters, 1):
            print(f"Ch.{ch}: {len(chapter.chunks)} chunks.")

        print(f"Project saved to: {args.output_dir.resolve()}")


# if __name__ == "__main__":
#     raise SystemExit(main())
