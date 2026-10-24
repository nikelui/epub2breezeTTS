"""Read-only report for a processed book project (no TTS dependencies)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, TextIO

from epub_audiobook.models import ProjectPaths


def _json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required project file missing: {path}")
    with path.open(encoding="utf-8") as stream:
        obj = json.load(stream)
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return obj


def _records(path: Path):
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSONL {path}:{line_number}: {error}") from error
            if not isinstance(obj, dict):
                raise ValueError(f"Expected object in {path}:{line_number}")
            yield obj


def collect_book_info(paths: ProjectPaths, *, include_chunks: bool = False) -> dict[str, Any]:
    """Aggregate metadata, chunk counts, and progress without modifying output."""
    metadata = _json_file(paths.metadata)
    manifest = (
        _json_file(paths.progress).get("chunks", {})
        if paths.progress.is_file() else {}
    )
    if not isinstance(manifest, dict):
        raise ValueError("progress.chunks must be an object")

    chunks_by_chapter: dict[str, list[dict]] = defaultdict(list)
    for chunk in _records(paths.chunks):
        chunks_by_chapter[str(chunk["chapter_id"])].append(chunk)
    paragraphs = Counter(
        str(rec["chapter_id"]) for rec in _records(paths.paragraphs)
    ) if paths.paragraphs.is_file() else Counter()

    chapters = []
    for chapter in metadata.get("chapters", []):
        chapter_id = str(chapter["id"])
        chapter_chunks = sorted(
            chunks_by_chapter.pop(chapter_id, []),
            key=lambda ch: int(ch.get("chunk_index", 0)),
        )
        states = Counter()
        details = []
        for chunk in chapter_chunks:
            chunk_id = str(chunk["id"])
            record = manifest.get(chunk_id) or {}
            state = str(record.get("status", "pending"))
            if state == "completed":
                file = paths.chunk_audio(chapter_id, chunk_id)
                if not file.is_file() or file.stat().st_size == 0:
                    state = "missing_wav"
            states[state] += 1
            if include_chunks:
                text = chunk.get("tts_text") or chunk.get("text") or ""
                details.append({
                    "id": chunk_id,
                    "chars": len(text),
                    "status": state,
                    "preview": " ".join(text.split())[:75],
                })
        intro_id = f"{chapter_id}-c000000"
        intro = manifest.get(intro_id)
        intro_status = str(intro.get("status")) if intro else "not_recorded"
        if intro_status == "completed":
            intro_file = paths.chunk_audio(chapter_id, intro_id)
            if not intro_file.is_file() or intro_file.stat().st_size == 0:
                intro_status = "missing_wav"
        chapters.append({
            "id": chapter_id,
            "index": chapter["index"],
            "title": chapter.get("title") or "(untitled)",
            "paragraphs": paragraphs[chapter_id] if paths.paragraphs.is_file() else chapter.get("paragraph_count"),
            "expected_chunks": chapter.get("chunk_count"),
            "actual_chunks": len(chapter_chunks),
            "status": dict(states),
            "intro_status": intro_status,
            "chunks": details if include_chunks else None,
        })
    return {"book": metadata, "chapters": chapters,
            "unknown_chapter_ids": sorted(chunks_by_chapter)}


def print_book_info(paths: ProjectPaths, *, show_chunks: bool = False,
                    out: TextIO | None = None) -> None:
    out = out or sys.stdout
    report = collect_book_info(paths, include_chunks=show_chunks)
    book = report["book"]
    print(f"Title:      {book.get('title', '(unknown)')}", file=out)
    print(f"Author(s):  {', '.join(book.get('authors') or []) or '(unknown)'}", file=out)
    print(f"Language:   {book.get('language') or '(unknown)'}", file=out)
    print(f"Publisher:  {book.get('publisher') or '(unknown)'}", file=out)
    print(f"Identifier: {book.get('identifier') or '(unknown)'}", file=out)
    print(f"Output:     {paths.root}", file=out)
    print(f"Chapters:   {len(report['chapters'])}", file=out)
    total = sum(ch["actual_chunks"] for ch in report["chapters"])
    print(f"Chunks:     {total} (body chunks; introductions excluded)", file=out)
    print("\nChapters:", file=out)
    for chapter in report["chapters"]:
        counts = chapter["status"]
        summary = ", ".join(f"{name}={num}" for name, num in sorted(counts.items())) or "no chunks"
        expected = chapter["expected_chunks"]
        mismatch = " [COUNT MISMATCH]" if expected is not None and expected != chapter["actual_chunks"] else ""
        print(f"  {chapter['index']:>3}  {chapter['title']} [{chapter['id']}]", file=out)
        print(f"       paragraphs={chapter['paragraphs']}, chunks={chapter['actual_chunks']}, "
              f"intro={chapter['intro_status']}; {summary}{mismatch}", file=out)
        if show_chunks:
            for chunk in chapter["chunks"]:
                print(f"       {chunk['id']}  {chunk['status']:>11}  "
                      f"{chunk['chars']:>4} chars  {chunk['preview']}", file=out)
    if report["unknown_chapter_ids"]:
        print(f"WARNING: chunks reference unlisted chapters: "
              f"{', '.join(report['unknown_chapter_ids'])}", file=out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a processed EPUB project")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--chunks", action="store_true", help="List each chunk and its status")
    args = parser.parse_args(argv)
    try:
        print_book_info(ProjectPaths(args.output_dir), show_chunks=args.chunks)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"book-info: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
