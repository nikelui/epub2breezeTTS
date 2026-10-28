"""Assemble synthesized WAV chunks into tagged chapter MP3/M4A files."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class AssemblyOptions:
    format: Literal["mp3", "m4a"] = "mp3"
    silence_seconds: float = 0.1
    bitrate: str = "128k"
    ffmpeg: str = "ffmpeg"
    overwrite: bool = False
    include_intro: bool = True

    pauses: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.format not in ("mp3", "m4a"):
            raise ValueError("format must be mp3 or m4a")
        if not 0 <= self.silence_seconds <= 60:
            raise ValueError("silence_seconds must be between 0 and 60")


def _wav_params(path: Path) -> tuple[int, int, int]:
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getnframes() <= 0 or wav.getcomptype() != "NONE":
                raise ValueError(f"Invalid/empty PCM WAV: {path}")
            return wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Invalid PCM WAV: {path}") from exc


def _write_silence(path: Path, params: tuple[int, int, int], seconds: float) -> None:
    channels, width, rate = params
    frames = round(seconds * rate)
    # 8-bit PCM silence is unsigned 128; 16/24/32-bit PCM silence is zero.
    sample = b"\x80" if width == 1 else b"\x00" * width
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(sample * channels * frames)

@dataclass
class AssemblyResult:
    generated: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def _ffconcat_entry(path: Path) -> str:
    # ffconcat uses single-quoted file names with backslash escaping.
    # Path.as_posix() also handles Windows separators correctly.
    s = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{s}'\n"


def load_manifest(paths) -> tuple[dict, dict[str, list[dict]]]:
    """Load compact book metadata and chunk manifest (not filesystem glob order)."""
    metadata = json.loads(paths.metadata.read_text(encoding="utf-8"))
    chapters: dict[str, list[dict]] = {}
    with paths.chunks.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            cid = str(record["chapter_id"])
            chapters.setdefault(cid, []).append(record)
    for cid, records in chapters.items():
        records.sort(key=lambda x: int(x["chunk_index"]))
        indices = [int(x["chunk_index"]) for x in records]
        if len(indices) != len(set(indices)) or len({str(x["id"]) for x in records}) != len(records):
            raise ValueError(f"Duplicate chunk indices or IDs in {cid}")
    return metadata, chapters


def assemble_chapters(paths, *, options: AssemblyOptions, chapter_indices: set[int] | None = None) -> AssemblyResult:
    """Assemble all or selected chapters, validating all source WAVs first.

    `paths` is the existing ProjectPaths instance from models.py.
    Missing chunks fail rather than silently producing an incomplete chapter.
    """
    metadata, records_by_chapter = load_manifest(paths)
    destination = paths.full_chapters
    destination.mkdir(parents=True, exist_ok=True)
    results = AssemblyResult()
    author = ", ".join(metadata.get("authors") or [])
    book_title = metadata.get("title") or ""

    #assembly_result = AssemblyResult()

    for chapter in metadata["chapters"]:
        index = int(chapter["index"])
        if chapter_indices is not None and index not in chapter_indices:
            continue
        cid = str(chapter["id"])
        rows = records_by_chapter.get(cid, [])
        expected = chapter.get("chunk_count")
        if expected is not None and len(rows) != int(expected):
            raise ValueError(f"{cid}: expected {expected} chunks, got {len(rows)}")
        if not rows:
            raise ValueError(f"{cid}: no body chunks found")

        files: list[Path] = []
        endings = []

        intro = paths.audio / cid / f"{cid}-c000000.wav"
        if options.include_intro and intro.exists():
            files.append(intro)
            endings.append("chapter_title")
        for row in rows:
            file = paths.audio / cid / f"{row['id']}.wav"
            if not file.is_file():
                raise FileNotFoundError(f"Missing source chunk: {file}")
            files.append(file)
            endings.append(row.get("ending_type"))

        params = _wav_params(files[0])
        for file in files[1:]:
            if _wav_params(file) != params:
                raise ValueError(f"WAV sample format mismatch in {cid}: {file}")

        output = destination / f"chapter{index:04d}.{options.format}"
        if output.exists() and not options.overwrite:
            print(f"[SKIP] Chapter {index:04d}: {destination.name}/{output.name}")
            results.skipped.append(destination)
            continue
        title = str(chapter.get("title") or f"Chapter {index}")
        with tempfile.TemporaryDirectory(prefix="chapter-assemble-") as tmp:
            tmpdir = Path(tmp)
            silence = tmpdir / "silence.wav"
            if options.silence_seconds:
                _write_silence(silence, params, options.silence_seconds)
            concat = tmpdir / "files.ffconcat"
            with concat.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write("ffconcat version 1.0\n")
                for idx, file in enumerate(files):
                    if idx and options.silence_seconds:
                        handle.write(_ffconcat_entry(silence))
                    handle.write(_ffconcat_entry(file))

            # Encode into a temporary file *with the right extension*, then atomically publish.
            staged = tmpdir / f"chapter.{options.format}"
            codec = "libmp3lame" if options.format == "mp3" else "aac"
            command = [
                options.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-safe", "0", "-f", "concat", "-i", str(concat),
                "-map", "0:a:0", "-vn", "-c:a", codec, "-b:a", options.bitrate,
                "-metadata", f"title={title}",
                "-metadata", f"album={book_title}",
                "-metadata", f"artist={author}",
                "-metadata", f"album_artist={author}",
                "-metadata", f"track={index}",
                "-metadata", "genre=Audiobook",
            ]
            if metadata.get("language"):
                command += ["-metadata:s:a:0", f"language={metadata['language']}"]
            command.append(str(staged))
            subprocess.run(command, check=True, capture_output=True, text=True)
            if not staged.exists() or staged.stat().st_size == 0:
                raise RuntimeError(f"FFmpeg produced an empty file for {cid}")
            os.replace(staged, output)
            print(f"[GENERATE] Chapter {index}: {destination.name}/{output.name}")
            results.generated.append(output)
        #results.append(output)
    return results
