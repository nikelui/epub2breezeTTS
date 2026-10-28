"""Read ebook metadata and extract paragraphs in reading order"""
import re
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT, epub

from epub_audiobook.models import Book, Chapter, Paragraph
from epub_audiobook.text.toc import extract_toc_entries
from epub_audiobook.text.toc_splitter import (
    mark_chapter_boundaries,
    split_marked_blocks,
)


def get_metadata(book, name: str, default=None) -> str | None:
    try:
        values = book.get_metadata("DC", name)
    except KeyError:
        return default

    if not values:
            return None

    value = values[0][0]
    return str(value).strip() if value else None


def clean_inline_text(text: str) -> str:
    """Normalize Unicode and whitespace without rewriting prose."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_paragraphs(html: bytes) -> list[tuple[str, str]]:
    """
    Return (optional heading, paragraph text) pairs.

    Headings are retained separately rather than being merged into prose.
    """
    soup = BeautifulSoup(html, "lxml-xml")

    for tag in soup(
        ["script", "style", "noscript", "svg", "template"]
    ):
        tag.decompose()

    # Remove common non-content elements. Be conservative with classes:
    # book-specific classes may contain real prose.
    for tag in soup.select(
        "nav, [aria-hidden='true'], .pagebreak, .page-break"
    ):
        tag.decompose()

    # EPUB navigation documents are excluded at the item-selection stage.
    body = soup.body or soup
    result = []

    for element in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote"]):
        # Skip paragraphs nested inside another selected block.
        if element.find_parent(
            ["p", "blockquote", "h1", "h2", "h3", "h4" , "h5", "h6"]
        ):
            continue

        text = clean_inline_text(element.get_text(separator=""))
        if not text:
            continue

        if element.name.startswith("h"):
            result.append(("heading", text))
        else:
            result.append(("paragraph", text))

    return result


def inspect_epub_structure(epub_path):
    book = epub.read_epub(str(epub_path))

    print("\n=== SPINE ===")

    for index, (item_id, linear) in enumerate(
        book.spine, start=1
    ):

        item = book.get_item_with_id(item_id)

        if item is None:
            continue

        print(
            index,
            item_id,
            item.get_name(),
            f"linear={linear}",
        )

    print("\n=== TABLE OF CONTENTS ===")

    def show_toc(items, level=0):

        for entry in items:

            if isinstance(entry, epub.Link):
                print(
                    "  " * level,
                    entry.title,
                    entry.href,
                )

            elif isinstance(entry, epub.Section):
                print(
                    "  " * level,
                    "[SECTION]",
                    entry.title,
                )

            elif isinstance(entry, (tuple, list)):
                show_toc(entry, level + 1)

    show_toc(book.toc)


def read_epub(path: str | Path) -> Book:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    epub_book = epub.read_epub(str(path))

    result = Book(
        title=get_metadata(epub_book, "title") or path.stem,
        authors=[
            value
            for value, _ in epub_book.get_metadata("DC", "creator")
            if value
        ],
        language=get_metadata(epub_book, "language"),
        identifier=get_metadata(epub_book, "identifier"),
        publisher=get_metadata(epub_book, "publisher"),
        description=get_metadata(epub_book, "description"),
    )

    # Follow the spine's reading order, not the archive's file order.
    for idref, linear in epub_book.spine:
        if linear == "no":
            continue

        item = epub_book.get_item_with_id(idref)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue

        # Exclude EPUB3 navigation documents.
        if "nav" in item.properties:
            continue

        blocks = extract_paragraphs(item.get_content())
        if not blocks:
            continue

        chapter_index = len(result.chapters) + 1
        chapter = Chapter(
            id=f"ch{chapter_index:04d}",
            index=chapter_index,
            title=f"Section {chapter_index}",
            source_href=item.get_name(),
        )

        paragraph_index = 0

        for kind, text in blocks:
            if kind == "heading":
                # Use the first heading as the section title.
                if chapter.title.startswith("Section "):
                    chapter.title = text
                continue

            paragraph_index += 1
            chapter.paragraphs.append(
                Paragraph(
                    id=f"{chapter.id}-p{paragraph_index:05d}",
                    index=paragraph_index,
                    text=text,
                )
            )

        if chapter.paragraphs:
            result.chapters.append(chapter)

    return result



def read_epub2(path: str | Path) -> Book:
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(path)

    epub_book = epub.read_epub(str(path))

    result = Book(
        title=get_metadata(epub_book, "title") or path.stem,
        authors=[
            value
            for value, _ in epub_book.get_metadata("DC", "creator")
            if value
        ],
        language=get_metadata(epub_book, "language"),
        identifier=get_metadata(epub_book, "identifier"),
        publisher=get_metadata(epub_book, "publisher"),
        description=get_metadata(epub_book, "description"),
    )

    # ---------------------------------------------------------
    # 1. Read chapter references from TOC.
    # ---------------------------------------------------------

    toc_chapters = extract_toc_entries(epub_book)

    if not toc_chapters:
        raise ValueError(
            "No recognized TOC chapters found. "
            "A fallback extraction strategy is required."
        )

    # Group references by XHTML document.
    chapters_by_document = {}

    for chapter in toc_chapters:

        chapters_by_document.setdefault(
            chapter.href,
            [],
        ).append(chapter)

    # ---------------------------------------------------------
    # 2. Process spine documents in reading order.
    # ---------------------------------------------------------

    for idref, linear in epub_book.spine:

        if linear == "no":
            continue

        item = epub_book.get_item_with_id(idref)

        if item is None:
            continue

        if item.get_type() != ITEM_DOCUMENT:
            continue

        if "nav" in item.properties:
            continue

        document_href = item.get_name()

        # Only process documents containing selected TOC chapters.
        #
        # This excludes the Gutenberg cover, header-only files,
        # footer, and license when they are not part of the
        # selected chapters.

        document_chapters = chapters_by_document.get(
            document_href,
        )

        if not document_chapters:
            continue

        # -----------------------------------------------------
        # 3. Insert markers at the TOC anchors.
        # -----------------------------------------------------

        marked_content = mark_chapter_boundaries(
            item.get_content(),
            document_chapters,
        )

        # -----------------------------------------------------
        # 4. Extract paragraphs using the existing extractor.
        # -----------------------------------------------------

        blocks = extract_paragraphs(
            marked_content
        )

        # -----------------------------------------------------
        # 5. Split blocks into TOC-defined chapters.
        # -----------------------------------------------------

        sections = split_marked_blocks(
            blocks,
            document_chapters,
        )

        # -----------------------------------------------------
        # 6. Create Chapter and Paragraph objects.
        # -----------------------------------------------------

        for toc_chapter, chapter_blocks in sections:

            chapter_index = len(result.chapters) + 1

            chapter = Chapter(
                id=f"ch{chapter_index:04d}",
                index=chapter_index,
                title=toc_chapter.title,
                source_href=(
                    f"{toc_chapter.href}"
                    f"#{toc_chapter.fragment}"
                ),
            )

            paragraph_index = 0

            for kind, text in chapter_blocks:

                # Headings are used structurally and are
                # not synthesized as body text.
                #
                # Chapter introductions will be generated
                # separately by the TTS pipeline.

                if kind == "heading":
                    continue

                paragraph_index += 1

                chapter.paragraphs.append(
                    Paragraph(
                        id=(
                            f"{chapter.id}"
                            f"-p{paragraph_index:05d}"
                        ),
                        index=paragraph_index,
                        text=text,
                    )
                )

            if chapter.paragraphs:
                result.chapters.append(chapter)

    return result
