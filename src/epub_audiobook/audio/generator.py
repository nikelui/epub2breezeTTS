"""Sequential chunk generation with resume, atomic WAV output and failure logging."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from epub_audiobook.audio.progress import Manifest, fingerprint, valid_wav
from epub_audiobook.audio.selection import select_chapters
from epub_audiobook.models import ChapterIntroOptions, ProjectPaths

logger = logging.getLogger(__name__)

ROMAN_PATTERN = re.compile(
    r"^(?=.+$)"
    r"M{0,3}"
    r"(?:CM|CD|D?C{0,3})"
    r"(?:XC|XL|L?X{0,3})"
    r"(?:IX|IV|V?I{0,3})$",
    re.IGNORECASE,
)

@dataclass(frozen=True)
class AudioChunk:
    id: str
    chapter_id: str
    chapter_index: int
    chunk_index: int
    text: str
    chapter_title: str = ""


def read_chunks_jsonl(path: Path) -> list[AudioChunk]:
    proj_path = ProjectPaths(path)

    chunks = []
    seen: set[str] = set()
    orders: set[tuple[int, int]] = set()
    with proj_path.chunks.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                chunk = AudioChunk(
                    id=str(entry["id"]),
                    chapter_id=str(entry["chapter_id"]),
                    chapter_index=int(entry["chapter_index"]),
                    chunk_index=int(entry["chunk_index"]),
                    text=entry.get("tts_text") if entry.get("tts_text") is not None else entry["text"],
                    chapter_title=str(entry.get("chapter_title") or ""),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid JSONL record at line {line_number}") from exc
            if not isinstance(chunk.text, str) or not chunk.text.strip():
                raise ValueError(f"Empty/invalid text at line {line_number}")
            order = (chunk.chapter_index, chunk.chunk_index)
            if chunk.id in seen or order in orders:
                raise ValueError(f"Duplicate chunk id/index at line {line_number}")
            seen.add(chunk.id)
            orders.add(order)
            chunks.append(chunk)
    return sorted(chunks, key=lambda chunk: (chunk.chapter_index, chunk.chunk_index))


@dataclass
class GenerationSummary:
    generated: int = 0
    skipped: int = 0
    failed: int = 0


def generate_selected(
    *,
    chunks: list[AudioChunk],
    output_dir: Path,
    synthesize: Callable[[str, Path, int], None],
    model_identity: str,
    voice_identity: str,
    cfg_scale: float = 1.0,
    seed: int = 42,
    chapters: str | None = None,
    chapter_intro: bool = True,
    intro_options: ChapterIntroOptions | None,
    force: bool = False,
    retry_failed: bool = True,
) -> GenerationSummary:
    """Process selected chunks. synthesize(text, temp_wav_path, seed) writes WAV.

    Single-process only. Existing audio is reused *only* when its manifest
    fingerprint matches and the WAV is readable; force regenerates all selected.
    """
    proj_path = ProjectPaths(output_dir)
    selected = set(select_chapters(chapters, {c.chapter_index for c in chunks}))
    manifest = Manifest(proj_path.progress)
    summary = GenerationSummary()

    # Add chapter intro chunks
    selected_chunks = [
        chunk
        for chunk in chunks
        if chunk.chapter_index in selected
    ]

    tasks = selected_chunks + (
        make_chapter_intros(selected_chunks, intro_options)
        if chapter_intro
        else []
    )

    tasks.sort(
        key=lambda chunk: (
            chunk.chapter_index,
            chunk.chunk_index,
        )
    )

    for chunk in tasks:
        if chunk.chapter_index not in selected:
            continue
        path = proj_path.chunk_audio(chunk.chapter_id, chunk.id)
        # path = output_dir / "audio" / chunk.chapter_id / f"{chunk.id}.wav"
        temp_path = path.with_name(path.stem + ".partial.wav")
        signature = fingerprint(chunk.text, model_identity=model_identity,
                                voice_identity=voice_identity,
                                cfg_scale=cfg_scale, seed=seed)
        previous = manifest.get(chunk.id)
        fresh = (previous is not None and previous.get("status") == "completed"
                 and previous.get("fingerprint") == signature and valid_wav(path))
        if not force and fresh:
            summary.skipped += 1
            continue
        if not force and not retry_failed and previous and previous.get("status") == "failed" and previous.get("fingerprint") == signature:
            summary.skipped += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.unlink(missing_ok=True)
        manifest.update(chunk.id, status="in_progress", fingerprint=signature,
                        audio_file=str(path.relative_to(proj_path.root)))
        try:
            synthesize(chunk.text, temp_path, seed)
            if not valid_wav(temp_path):
                raise RuntimeError("Synthesis did not produce a valid PCM WAV")
            os.replace(temp_path, path)
            manifest.update(chunk.id, status="completed", fingerprint=signature,
                            audio_file=str(path.relative_to(proj_path.root)))
            summary.generated += 1
            logger.info("Generated %s", chunk.id)
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            manifest.update(chunk.id, status="failed", fingerprint=signature,
                            audio_file=str(path.relative_to(proj_path.root)),
                            error=f"{type(exc).__name__}: {exc}")
            summary.failed += 1
            logger.exception("Failed to generate %s", chunk.id)
    return summary


def roman_to_int(value: str) -> int:
    """Convert a valid Roman numeral to an integer."""

    roman = value.upper()

    if not ROMAN_PATTERN.fullmatch(roman):
        raise ValueError(
            f"Invalid Roman numeral: {value!r}"
        )

    values = {
        "I": 1,
        "V": 5,
        "X": 10,
        "L": 50,
        "C": 100,
        "D": 500,
        "M": 1000,
    }

    result = 0

    for index, character in enumerate(roman):

        current = values[character]

        if (
            index + 1 < len(roman)
            and current < values[roman[index + 1]]
        ):
            result -= current
        else:
            result += current

    return result


def convert_roman_numerals_in_title(title: str) -> str:
    """Convert Roman numerals used in chapter titles.

    Examples:
        Chapter IV       -> Chapter 4
        CHAPTER IX       -> CHAPTER 9
        Part XII         -> Part 12
        IV               -> 4
        Chapter IV: ...  -> Chapter 4: ...

    Ordinary standalone Roman-looking words are not converted
    unless the title consists entirely of a numeral.
    """

    # Match a Roman numeral following a common section label.
    labelled_pattern = re.compile(
        r"\b("
        r"chapter|chap\.?|ch\.?|"
        r"part|section|book|volume|vol\.?"
        r")\s+([IVXLCDM]+)\b",
        re.IGNORECASE,
    )

    def replace_labelled(match: re.Match) -> str:
        label = match.group(1)
        numeral = match.group(2)

        try:
            number = roman_to_int(numeral)
        except ValueError:
            return match.group(0)

        return f"{label} {number}"

    title = labelled_pattern.sub(
        replace_labelled,
        title,
    )

    # Also support titles consisting only of a Roman numeral:
    # "IV" -> "4".
    stripped = title.strip()

    if ROMAN_PATTERN.fullmatch(stripped):
        try:
            return str(roman_to_int(stripped))
        except ValueError:
            pass

    return title


def make_chapter_intros(
    chunks: list[AudioChunk],
    options: ChapterIntroOptions | None = None,
) -> list[AudioChunk]:
    """Generates a brief text with the chapter number and title (where available)"""
    options = options or ChapterIntroOptions()
    by_chapter: dict[str, AudioChunk] = {}

    for chunk in chunks:
        previous = by_chapter.setdefault(
            chunk.chapter_id,
            chunk,
        )

        if (
            previous.chapter_index != chunk.chapter_index
            or previous.chapter_title != chunk.chapter_title
        ):
            raise ValueError(f"Inconsistent chapter metadata: {chunk.chapter_id}")

    intros = []

    for chapter_id, chunk in by_chapter.items():

        title = chunk.chapter_title.strip()

        if options.include_title and not title:
                    raise ValueError(f"Missing chapter_title for {chapter_id}")

        if options.roman_to_decimal and title:
            title = convert_roman_numerals_in_title(title)

        components = []

        # Prefix.
        if options.include_prefix:
            components.append(options.prefix.strip())

        # Chapter number (human-readable index, not internal ID).
        if options.include_id:
            components.append(str(chunk.chapter_index))

        header = options.prefix_id_separator.join(components)

        # Add title.
        if options.include_title:

            if header:
                intro_text = (header + options.title_separator + title)
            else:
                intro_text = title

        else:
            intro_text = header

        intros.append(
            AudioChunk(
                id=f"{chapter_id}-c000000",
                chapter_id=chapter_id,
                chapter_index=chunk.chapter_index,
                chunk_index=0,
                text=intro_text,
                chapter_title=title,
            )
        )

    return intros
