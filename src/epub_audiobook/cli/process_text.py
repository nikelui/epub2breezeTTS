import argparse  # noqa: I001
from pathlib import Path

from epub_audiobook.text.epub_reader import read_epub
from epub_audiobook.text.chunker import ChunkConfig, chunk_chapter
from epub_audiobook.text.export import write_chunks_jsonl


def main():
    parser = argparse.ArgumentParser(
        description="Extract and chunk text from an EPUB."
    )
    parser.add_argument("epub", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("output/")
    )
    parser.add_argument("--max-chars", type=int, default=500)
    parser.add_argument("--target-chars", type=int, default=300)
    parser.add_argument("--min-chars", type=int, default=150)
    parser.add_argument("--verbose", type=bool, default=False)

    args = parser.parse_args()

    book = read_epub(args.epub)

    config = ChunkConfig(
        min_chars = args.min_chars,
        target_chars = args.target_chars,
        max_chars = args.max_chars,
    )

    for chapter in book.chapters:
        chunk_chapter(chapter, config)

    write_chunks_jsonl(book, args.output / book.title / "chunks.jsonl")

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

        print(f"Project saved to: {args.output.resolve()}")


if __name__ == "__main__":
    main()
