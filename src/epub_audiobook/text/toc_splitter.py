"""Split XHTML content using EPUB TOC chapter anchors."""

from __future__ import annotations

from bs4 import BeautifulSoup

from epub_audiobook.text.toc import TocChapter

MARKER_PREFIX = "__EPUB_CHAPTER_BOUNDARY_"


def mark_chapter_boundaries(
    content: bytes,
    chapters: list[TocChapter],
) -> bytes:
    """Insert temporary chapter markers into XHTML.

    Chapters must correspond to the current XHTML document.

    Markers are inserted immediately before the relevant
    chapter element, preserving original content order.
    """

    soup = BeautifulSoup(content, "lxml-xml")

    for index, chapter in enumerate(chapters):

        target = soup.find(id=chapter.fragment)

        if target is None:
            raise ValueError(
                f"Chapter anchor not found: "
                f"{chapter.href}#{chapter.fragment}"
            )

        # Anchors are sometimes inside headings:
        #
        # <h2><a id="chapter-1"></a>I</h2>
        #
        # Insert the marker before the whole heading rather
        # than in the middle of its content.

        heading = target.find_parent(
            ["h1", "h2", "h3", "h4", "h5", "h6"]
        )

        insertion_target = heading or target

        marker = soup.new_tag("h6")
        marker.string = f"{MARKER_PREFIX}{index}__"

        insertion_target.insert_before(marker)

    return soup.encode("utf-8")


def split_marked_blocks(
    blocks: list[tuple[str, str]],
    chapters: list[TocChapter],
) -> list[tuple[TocChapter, list[tuple[str, str]]]]:
    """Group extracted blocks according to chapter markers."""

    result = []

    current_chapter = None
    current_blocks = []

    seen_markers = set()

    for kind, text in blocks:

        if text.startswith(MARKER_PREFIX):

            if current_chapter is not None:
                result.append(
                    (current_chapter, current_blocks)
                )

            marker_index = int(
                text.removeprefix(MARKER_PREFIX)
                .removesuffix("__")
            )

            if marker_index >= len(chapters):
                raise ValueError(
                    f"Invalid chapter marker: {text}"
                )

            if marker_index in seen_markers:
                raise ValueError(
                    f"Duplicate chapter marker: {text}"
                )

            seen_markers.add(marker_index)

            current_chapter = chapters[marker_index]
            current_blocks = []

            continue

        # Ignore cover, title-page and TOC material before
        # the first actual chapter marker.

        if current_chapter is None:
            continue

        current_blocks.append((kind, text))

    if current_chapter is not None:
        result.append(
            (current_chapter, current_blocks)
        )

    if len(seen_markers) != len(chapters):
        raise ValueError(
            "Some chapter markers were not extracted. "
            "Check extract_paragraphs() heading handling."
        )

    return result
