"""Combine encoded M4B chapter files into one bookmarked audiobook.

Requires ffmpeg and ffprobe on PATH. Intended for chapter files produced using
consistent AAC encoding settings by the chapter assembler.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from epub_audiobook.audio.assembler import parse_chapter_selection
from epub_audiobook.models import ProjectPaths


@dataclass(frozen=True)
class AudiobookOptions:
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    overwrite: bool = False
    filename: str = "combined_audiobook.m4b"


def _run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {command[0]}\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _probe(path: Path, executable: str) -> dict[str, Any]:
    data = _run([
        executable, "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,sample_rate,channels",
        "-of", "json", str(path),
    ])
    return json.loads(data)


def _duration_ms(info: dict[str, Any], path: Path) -> int:
    raw = info.get("format", {}).get("duration")
    try:
        duration = Decimal(str(raw))
    except Exception as exc:
        raise ValueError(f"No valid duration for {path}") from exc
    if not duration.is_finite() or duration <= 0:
        raise ValueError(f"Non-positive duration for {path}")
    return int((duration * 1000).to_integral_value(rounding=ROUND_HALF_UP))


def _audio_format(info: dict[str, Any], path: Path) -> tuple[str, str, int, int]:
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if len(streams) != 1:
        raise ValueError(f"Expected exactly one audio stream in {path}")
    audio = streams[0]
    value = (str(audio.get("codec_name")), str(audio.get("sample_rate")),
             int(audio.get("channels", 0)))
    if value[0] != "aac":
        raise ValueError(f"M4B input must be AAC: {path} ({value[0]})")
    return ("aac", *value)


def _ffconcat_quote(path: Path) -> str:
    value = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{value}'"


def _meta_escape(value: object) -> str:
    """Escape FFmetadata reserved characters."""
    text = str(value)
    for char in ("\\", "=", ";", "#", "\n"):
        text = text.replace(char, "\\" + char)
    return text


def _ffmetadata(book: dict, chapter_details: list[tuple[dict, int]]) -> str:
    authors = book.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    author = ", ".join(map(str, authors))
    lines = [
        ";FFMETADATA1",
        f"title={_meta_escape(book.get('title') or 'Audiobook')}",
        f"artist={_meta_escape(author)}",
        f"album={_meta_escape(book.get('title') or 'Audiobook')}",
        f"album_artist={_meta_escape(author)}",
        "genre=Audiobook",
    ]
    cursor_ms = 0
    for chapter, duration_ms in chapter_details:
        end_ms = cursor_ms + duration_ms
        lines += [
            "[CHAPTER]", "TIMEBASE=1/1000", f"START={cursor_ms}",
            f"END={end_ms}",
            f"title={_meta_escape(chapter.get('title') or f'Chapter {chapter["index"]}')}"
        ]
        cursor_ms = end_ms
    return "\n".join(lines) + "\n"


def audiobook_filename(
    selected_chapters: list[dict],
    *,
    partial: bool,
) -> str:
    """Return a predictable filename for the combined audiobook."""

    if not partial:
        return "combined_audiobook.m4b"

    indices = [
        int(chapter["index"])
        for chapter in selected_chapters
    ]

    suffix = "_".join(f"{index:04d}" for index in indices)

    return f"combined_chapters_{suffix}.m4b"


def combine_m4b_book(
    paths: ProjectPaths,
    options: AudiobookOptions | None = None,
    chapters: str | None = None,
) -> Path:
    """Combine *all* chapters in metadata order into one M4B with bookmarks.

    Refuses a missing chapter. If output exists, skips unless overwrite=True.
    Writes a temporary output first, then atomically replaces the destination.
    """
    options = options or AudiobookOptions()
    if Path(options.filename).name != options.filename or not options.filename.endswith(".m4b"):
        raise ValueError("filename must be a simple .m4b filename")

    selected = parse_chapter_selection(chapters)

    metadata = json.loads(paths.metadata.read_text(encoding="utf-8"))
    book_chapters = sorted(metadata["chapters"], key=lambda x: int(x["index"]))
    if not book_chapters:
        raise ValueError("No chapters in metadata.json")

    available_indices = {
        int(chapter["index"])
        for chapter in book_chapters
    }

    if selected is not None:
        missing_indices = selected - available_indices

        if missing_indices:
            raise ValueError(
                f"Unknown chapter indices: {sorted(missing_indices)}"
            )

        book_chapters = [
            chapter
            for chapter in book_chapters
            if int(chapter["index"]) in selected
        ]

    if not book_chapters:
        raise ValueError("No chapters selected for audiobook")

    chapter_dir = paths.audio / "full_chapters"
    destination = (
        chapter_dir
        / audiobook_filename(
            book_chapters,
            partial=selected is not None,
        )
    )
    if destination.is_file() and not options.overwrite:
        print(f"[SKIP] Combined audiobook already exists: {destination}")
        return destination

    files = [chapter_dir / f"chapter{int(ch['index']):04d}.m4b" for ch in book_chapters]
    missing = [str(path) for path in files if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError("Missing assembled M4B chapters:\n" + "\n".join(missing))

    details: list[tuple[dict, int]] = []
    reference_format = None
    for chapter, path in zip(book_chapters, files):
        info = _probe(path, options.ffprobe)
        audio_format = _audio_format(info, path)
        if reference_format is None:
            reference_format = audio_format
        elif audio_format != reference_format:
            raise ValueError(f"Mismatched audio settings in {path}: {audio_format} vs {reference_format}")
        details.append((chapter, _duration_ms(info, path)))

    chapter_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="book_", dir=chapter_dir) as temp:
        tempdir = Path(temp)
        concat = tempdir / "chapters.ffconcat"
        concat.write_text("ffconcat version 1.0\n" + "\n".join(_ffconcat_quote(f) for f in files) + "\n", encoding="utf-8")
        tags = tempdir / "chapters.ffmeta"
        tags.write_text(_ffmetadata(metadata, details), encoding="utf-8")
        temporary_output = tempdir / "combined.m4b"

        _run([
            options.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat),
            "-f", "ffmetadata", "-i", str(tags),
            "-map", "0:a:0", "-map_metadata", "1", "-map_chapters", "1",
            "-c:a", "copy", "-movflags", "+faststart", str(temporary_output),
            "-f", "ipod",
        ])
        if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
            raise RuntimeError("FFmpeg generated no audiobook output")
        chapter_check = json.loads(_run([
            options.ffprobe, "-v", "error", "-show_chapters", "-of", "json", str(temporary_output),
        ]))
        if len(chapter_check.get("chapters", [])) != len(book_chapters):
            raise RuntimeError("Bookmark verification failed: incorrect chapter count")
        temporary_output.replace(destination)
    return destination
