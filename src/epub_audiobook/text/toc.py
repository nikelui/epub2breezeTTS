"""Extract chapter references from an EPUB table of contents."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from urllib.parse import unquote, urldefrag

from ebooklib import epub


@dataclass(frozen=True)
class TocChapter:
    title: str
    href: str
    fragment: str


def iter_toc_links(entries):
    """Recursively yield links from an EbookLib TOC."""

    for entry in entries:

        if isinstance(entry, epub.Link):
            yield entry

        elif isinstance(entry, epub.Section):
            # Some TOCs have sections with their own targets.
            href = getattr(entry, "href", None)

            if href:
                yield entry

        elif isinstance(entry, (tuple, list)):
            yield from iter_toc_links(entry)


def extract_toc_chapters(epub_book) -> list[TocChapter]:
    """Extract chapter references in TOC order.

    Initial strategy:
    Select links whose fragments match chapter-N.

    This works for the supplied Project Gutenberg Gatsby EPUB.
    Other EPUBs may use different anchor naming conventions.
    """

    chapters = []

    for link in iter_toc_links(epub_book.toc):

        href = getattr(link, "href", None)

        if not href:
            continue

        document, fragment = urldefrag(href)

        document = posixpath.normpath(
            unquote(document)
        )

        fragment = unquote(fragment)

        # Gutenberg-style chapter anchors.
        if not re.fullmatch(
            r"chapter-\d+",
            fragment,
            flags=re.IGNORECASE,
        ):
            continue

        chapters.append(
            TocChapter(
                title=str(link.title).strip(),
                href=document,
                fragment=fragment,
            )
        )

    return chapters
