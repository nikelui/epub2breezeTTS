"""Extract structured navigation entries from an EPUB TOC."""

from __future__ import annotations

import posixpath
from urllib.parse import unquote, urldefrag

from ebooklib import epub

from epub_audiobook.models import TocEntry


def normalize_toc_href(href: str) -> tuple[str, str | None]:
    """Separate an EPUB navigation reference into path and fragment."""

    path, fragment = urldefrag(href)

    path = posixpath.normpath(
        unquote(path)
    ) if path else ""

    fragment = unquote(fragment) or None

    return path, fragment


def extract_toc_entries(book) -> list[TocEntry]:
    """Flatten an EbookLib TOC while retaining navigation depth.

    Supports:
        epub.Link
        epub.Section
        nested tuples and lists

    Does not filter entries by their titles or fragments.
    """

    entries: list[TocEntry] = []

    def add_entry(
        title: str,
        href: str,
        level: int,
    ) -> None:

        document, fragment = normalize_toc_href(href)

        entries.append(
            TocEntry(
                title=title.strip(),
                href=document,
                fragment=fragment,
                level=level,
                order=len(entries),
            )
        )

    def visit(node, level: int = 0) -> None:

        if isinstance(node, epub.Link):

            add_entry(
                node.title,
                node.href,
                level,
            )

        elif isinstance(node, epub.Section):

            href = getattr(node, "href", None)

            if href:
                add_entry(
                    node.title,
                    href,
                    level,
                )

        elif isinstance(node, (list, tuple)):

            # EbookLib commonly represents a section as:
            #
            # (Section(...), [child links])
            #
            # The section and its children have different depths.

            if (
                len(node) == 2
                and isinstance(node[0], epub.Section)
                and isinstance(node[1], (list, tuple))
            ):

                visit(node[0], level)
                visit(node[1], level + 1)

            else:

                for child in node:
                    visit(child, level)

    visit(book.toc)

    return entries
