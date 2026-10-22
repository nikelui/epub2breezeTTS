"""Sequential chunk generation with resume, atomic WAV output and failure logging."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from epub_audiobook.audio.progress import Manifest, fingerprint, valid_wav
from epub_audiobook.audio.selection import select_chapters

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioChunk:
    id: str
    chapter_id: str
    chapter_index: int
    chunk_index: int
    text: str
    chapter_title: str = ""


def read_chunks_jsonl(path: Path) -> list[AudioChunk]:
    chunks = []
    seen: set[str] = set()
    orders: set[tuple[int, int]] = set()
    with path.open(encoding="utf-8") as stream:
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
    force: bool = False,
    retry_failed: bool = True,
) -> GenerationSummary:
    """Process selected chunks. synthesize(text, temp_wav_path, seed) writes WAV.

    Single-process only. Existing audio is reused *only* when its manifest
    fingerprint matches and the WAV is readable; force regenerates all selected.
    """
    selected = set(select_chapters(chapters, {c.chapter_index for c in chunks}))
    manifest = Manifest(output_dir / "progress.json")
    summary = GenerationSummary()

    # Add chapter intro chunks
    selected_chunks = [
        chunk
        for chunk in chunks
        if chunk.chapter_index in selected
    ]

    tasks = selected_chunks + (
        make_chapter_intros(selected_chunks)
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
        path = output_dir / "audio" / chunk.chapter_id / f"{chunk.id}.wav"
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
                        audio_file=str(path.relative_to(output_dir)))
        try:
            synthesize(chunk.text, temp_path, seed)
            if not valid_wav(temp_path):
                raise RuntimeError("Synthesis did not produce a valid PCM WAV")
            os.replace(temp_path, path)
            manifest.update(chunk.id, status="completed", fingerprint=signature,
                            audio_file=str(path.relative_to(output_dir)))
            summary.generated += 1
            logger.info("Generated %s", chunk.id)
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            manifest.update(chunk.id, status="failed", fingerprint=signature,
                            audio_file=str(path.relative_to(output_dir)),
                            error=f"{type(exc).__name__}: {exc}")
            summary.failed += 1
            logger.exception("Failed to generate %s", chunk.id)
    return summary

def make_chapter_intros(
    chunks: list[AudioChunk],
) -> list[AudioChunk]:
    """Generates a brief text with the chapter number and title (where available)"""
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
            raise ValueError(
                f"Inconsistent chapter metadata: {chunk.chapter_id}"
            )

    intros = []

    for chapter_id, chunk in by_chapter.items():

        title = chunk.chapter_title.strip()

        if not title:
            raise ValueError(
                f"Missing chapter_title for {chapter_id}"
            )

        intros.append(
            AudioChunk(
                id=f"{chapter_id}-c000000",
                chapter_id=chapter_id,
                chapter_index=chunk.chapter_index,
                chunk_index=0,
                text=f"Chapter {chunk.chapter_index}. {title}",
                chapter_title=title,
            )
        )

    return intros
