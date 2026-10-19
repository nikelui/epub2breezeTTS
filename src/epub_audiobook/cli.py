import argparse
from pathlib import Path

from .chunker import chunk_paragraph
from .epub_reader import read_epub
from .project_store import save_project


def main():
    parser = argparse.ArgumentParser(
        description="Extract and chunk text from an EPUB."
    )
    parser.add_argument("epub", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("projects/my-book")
    )
    parser.add_argument("--max-chars", type=int, default=400)
    parser.add_argument("--min-chars", type=int, default=180)

    args = parser.parse_args()

    book = read_epub(args.epub)

    for chapter in book.chapters:
        for paragraph in chapter.paragraphs:
            chunk_paragraph(
                paragraph,
                max_chars=args.max_chars,
                min_chars=args.min_chars,
            )

    save_project(book, args.output)

    print(f"Title: {book.title}")
    print(f"Authors: {', '.join(book.authors) or 'Unknown'}")
    print(f"Language: {book.language or 'Unknown'}")
    print(f"Chapters: {len(book.chapters)}")
    print(
        "Paragraphs:",
        sum(len(ch.paragraphs) for ch in book.chapters),
    )
    print(
        "Chunks:",
        sum(
            len(p.chunks)
            for ch in book.chapters
            for p in ch.paragraphs
        ),
    )
    print(f"Project saved to: {args.output.resolve()}")


if __name__ == "__main__":
    main()
