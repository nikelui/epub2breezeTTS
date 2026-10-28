"""Assemble synthesized WAV chunks into complete chapter audio files.

Features:
- MP3 and M4A output.
- Configurable silence based on chunk ending types.
- Optional chapter introduction.
- Chapter selection.
- Book and chapter metadata.
- Skip existing chapters unless overwrite=True.
- Temporary files and atomic output replacement.
- Windows/Linux compatible paths.

Requires FFmpeg to be available on PATH.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping

from epub_audiobook.models import ProjectPaths
from epub_audiobook.pause_types import (
    get_pause_duration,
    merge_pauses,
)

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class AssemblyOptions:
    """Options controlling chapter assembly."""

    format: Literal["mp3", "m4a"] = "mp3"

    # Used for old chunks.jsonl files without ending_type.
    silence_seconds: float = 0.1

    bitrate: str = "128k"
    ffmpeg: str = "ffmpeg"

    overwrite: bool = False
    include_intro: bool = True

    # Optional ending-specific duration overrides.
    pauses: Mapping[str, float] | None = None

    def __post_init__(self) -> None:

        if self.format not in {"mp3", "m4a"}:
            raise ValueError(
                "Output format must be 'mp3' or 'm4a'"
            )

        if (
            not math.isfinite(self.silence_seconds)
            or self.silence_seconds < 0
        ):
            raise ValueError(
                "silence_seconds must be finite and nonnegative"
            )

        # Validate user configuration immediately.
        merge_pauses(self.pauses)


@dataclass
class AssemblyResult:
    """Summary of chapter assembly operations."""

    generated: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class AudioPart:
    """One source WAV and the ending type following it."""

    path: Path
    ending_type: str | None


@dataclass(frozen=True)
class WavFormat:
    """Audio properties required for compatible concatenation."""

    channels: int
    sample_width: int
    sample_rate: int


# ---------------------------------------------------------------------
# Metadata and chunk manifest loading
# ---------------------------------------------------------------------


def load_metadata(path: Path) -> dict:
    """Load book metadata."""

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise TypeError("metadata.json must contain an object")

    if not isinstance(data.get("chapters"), list):
        raise TypeError(
            "metadata.json does not contain a chapters list"
        )

    return data


def load_chunks(path: Path) -> dict[str, list[dict]]:
    """Load chunk records, grouped by chapter ID.

    The records are sorted by chunk_index.
    """

    chapters: dict[str, list[dict]] = {}

    with path.open("r", encoding="utf-8") as file:

        for line_number, line in enumerate(file, start=1):

            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"Expected object on line {line_number}"
                )

            chapter_id = str(record["chapter_id"])

            chapters.setdefault(
                chapter_id,
                [],
            ).append(record)

    for chapter_id, records in chapters.items():

        records.sort(
            key=lambda row: int(row["chunk_index"])
        )

        indices = [
            int(row["chunk_index"])
            for row in records
        ]

        if len(indices) != len(set(indices)):
            raise ValueError(
                f"Duplicate chunk indices in {chapter_id}"
            )

    return chapters


# ---------------------------------------------------------------------
# Chapter selection
# ---------------------------------------------------------------------


def parse_chapter_selection(
    chapters: str | None,
) -> set[int] | None:
    """Parse expressions such as '1,3-5'.

    None or 'all' selects every chapter.
    """

    if chapters is None or chapters.strip().lower() == "all":
        return None

    selected: set[int] = set()

    for item in chapters.split(","):

        item = item.strip()

        if not item:
            raise ValueError("Empty chapter selection")

        if "-" in item:

            start_text, end_text = item.split("-", 1)

            start = int(start_text)
            end = int(end_text)

            if start < 1 or end < start:
                raise ValueError(
                    f"Invalid chapter range: {item}"
                )

            selected.update(range(start, end + 1))

        else:

            number = int(item)

            if number < 1:
                raise ValueError(
                    f"Invalid chapter number: {number}"
                )

            selected.add(number)

    return selected


# ---------------------------------------------------------------------
# WAV validation
# ---------------------------------------------------------------------


def get_wav_format(path: Path) -> WavFormat:
    """Read and validate the input WAV's audio properties."""

    if not path.is_file():
        raise FileNotFoundError(
            f"Missing WAV file: {path}"
        )

    with wave.open(str(path), "rb") as wav:

        if wav.getcomptype() != "NONE":
            raise ValueError(
                f"Compressed WAV is not supported: {path}"
            )

        if wav.getnframes() == 0:
            raise ValueError(
                f"Empty WAV file: {path}"
            )

        return WavFormat(
            channels=wav.getnchannels(),
            sample_width=wav.getsampwidth(),
            sample_rate=wav.getframerate(),
        )


def validate_wav_files(
    files: list[Path],
) -> WavFormat:
    """Ensure all WAV files have compatible audio properties."""

    if not files:
        raise ValueError("No audio files to assemble")

    expected = get_wav_format(files[0])

    for path in files[1:]:

        current = get_wav_format(path)

        if current != expected:
            raise ValueError(
                "Incompatible WAV format:\n"
                f"  First file: {expected}\n"
                f"  File: {path}\n"
                f"  Format: {current}"
            )

    return expected


# ---------------------------------------------------------------------
# Silence generation
# ---------------------------------------------------------------------


def create_silence_wav(
    destination: Path,
    duration: float,
    audio_format: WavFormat,
) -> None:
    """Create a PCM WAV containing silence.

    The silence WAV uses the same:
    - sample rate
    - channel count
    - sample width

    as the synthesized source audio.
    """

    if duration < 0 or not math.isfinite(duration):
        raise ValueError("Invalid silence duration")

    frame_count = round(
        duration * audio_format.sample_rate
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # PCM silence is zero-valued except for unsigned 8-bit PCM,
    # where the midpoint (128) represents silence.
    if audio_format.sample_width == 1:
        silent_frame = bytes(
            [128] * audio_format.channels
        )
    else:
        silent_frame = bytes(
            audio_format.channels * audio_format.sample_width
        )

    with wave.open(str(destination), "wb") as wav:

        wav.setnchannels(audio_format.channels)
        wav.setsampwidth(audio_format.sample_width)
        wav.setframerate(audio_format.sample_rate)

        # Write in batches to avoid allocating a huge buffer.
        batch_frames = 4096

        while frame_count > 0:

            count = min(
                batch_frames,
                frame_count,
            )

            wav.writeframes(
                silent_frame * count
            )

            frame_count -= count


class SilenceCache:
    """Create and reuse silence WAVs for distinct durations."""

    def __init__(
        self,
        directory: Path,
        audio_format: WavFormat,
    ) -> None:

        self.directory = directory
        self.audio_format = audio_format

        self._cache: dict[int, Path] = {}

    def get(self, duration: float) -> Path | None:
        """Return the silence WAV for a duration.

        Returns None when no silence is required.
        """

        if duration <= 0:
            return None

        # Convert seconds into an exact number of audio frames.
        # Durations which round to the same frame count can reuse
        # the same silence WAV.
        frames = round(
            duration * self.audio_format.sample_rate
        )

        if frames <= 0:
            return None

        if frames in self._cache:
            return self._cache[frames]

        actual_duration = (
            frames / self.audio_format.sample_rate
        )

        destination = (
            self.directory
            / f"silence_{frames}_frames.wav"
        )

        create_silence_wav(
            destination=destination,
            duration=actual_duration,
            audio_format=self.audio_format,
        )

        self._cache[frames] = destination

        return destination


# ---------------------------------------------------------------------
# FFmpeg concat manifest
# ---------------------------------------------------------------------


def ffmpeg_concat_path(path: Path) -> str:
    """Format an absolute path for an FFmpeg concat manifest.

    Always use forward slashes, including on Windows.
    """

    value = path.resolve().as_posix()

    # Escape apostrophes according to FFmpeg concat quoting rules.
    value = value.replace("'", "'\\''")

    return f"file '{value}'"


def write_concat_manifest(
    destination: Path,
    parts: list[AudioPart],
    pauses: Mapping[str, float],
    fallback_silence: float,
    silence_cache: SilenceCache,
) -> None:
    """Create an FFmpeg concat list with variable-length silence.

    Silence is inserted after each part except the final one.

    The duration is selected using the preceding part's ending type.
    """

    if not parts:
        raise ValueError("No audio parts to concatenate")

    lines: list[str] = []

    for index, part in enumerate(parts):

        lines.append(
            ffmpeg_concat_path(part.path)
        )

        # Never insert silence after the last audio file.
        if index == len(parts) - 1:
            continue

        duration = get_pause_duration(
            ending_type=part.ending_type,
            pauses=pauses,
            fallback=fallback_silence,
        )

        silence_file = silence_cache.get(duration)

        if silence_file is not None:
            lines.append(
                ffmpeg_concat_path(silence_file)
            )

    destination.write_text(
        "ffconcat version 1.0\n"
        + "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------
# Chapter source collection
# ---------------------------------------------------------------------


def _validate_id(value: str) -> str:
    """Reject identifiers that could escape the audio directory."""

    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(
            f"Unsafe chapter or chunk identifier: {value!r}"
        )

    return value


def collect_chapter_parts(
    paths: ProjectPaths,
    chapter: dict,
    chunk_records: list[dict],
    include_intro: bool,
) -> list[AudioPart]:
    """Build an ordered list of WAV files for a chapter."""

    chapter_id = _validate_id(str(chapter["id"]))

    chapter_directory = (
        paths.audio / chapter_id
    )

    parts: list[AudioPart] = []

    # Chapter introduction is a synthesized chunk with index zero.
    intro_id = f"{chapter_id}-c000000"

    intro_path = (
        chapter_directory
        / f"{intro_id}.wav"
    )

    if include_intro and intro_path.exists():

        parts.append(
            AudioPart(
                path=intro_path,
                ending_type="chapter_title",
            )
        )

    # Add body chunks in numerical order.
    for record in chunk_records:

        chunk_id = _validate_id(str(record["id"]))
        chunk_index = int(record["chunk_index"])

        # Ignore synthetic introductions if they happen to appear
        # in the chunk manifest.
        if chunk_index == 0:
            continue

        wav_path = (
            chapter_directory
            / f"{chunk_id}.wav"
        )

        if not wav_path.is_file():
            raise FileNotFoundError(
                f"Missing chunk audio: {wav_path}"
            )

        parts.append(
            AudioPart(
                path=wav_path,
                ending_type=record.get("ending_type"),
            )
        )

    return parts


# ---------------------------------------------------------------------
# FFmpeg execution
# ---------------------------------------------------------------------


def run_ffmpeg(
    manifest: Path,
    destination: Path,
    chapter: dict,
    book_metadata: dict,
    options: AssemblyOptions,
) -> None:
    """Run FFmpeg to concatenate, encode, and tag a chapter."""

    codec = {
        "mp3": "libmp3lame",
        "m4a": "aac",
    }[options.format]

    authors = book_metadata.get("authors") or []

    if isinstance(authors, str):
        authors = [authors]

    author = ", ".join(str(a) for a in authors)

    chapter_title = str(
        chapter.get("title")
        or f"Chapter {chapter['index']}"
    )

    book_title = str(
        book_metadata.get("title") or ""
    )

    command = [
        options.ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",

        "-f", "concat",
        "-safe", "0",
        "-i", str(manifest),

        "-map", "0:a:0",
        "-vn",

        "-c:a", codec,
        "-b:a", options.bitrate,

        "-metadata", f"title={chapter_title}",
        "-metadata", f"artist={author}",
        "-metadata", f"album={book_title}",
        "-metadata", f"album_artist={author}",
        "-metadata", f"track={chapter['index']}",
        "-metadata", "genre=Audiobook",

        "-metadata",
        f"language={book_metadata.get('language') or ''}",

        str(destination),
    ]

    try:

        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )

    except subprocess.CalledProcessError as exc:

        raise RuntimeError(
            f"FFmpeg failed for chapter "
            f"{chapter['index']}:\n"
            f"{exc.stderr}"
        ) from exc


# ---------------------------------------------------------------------
# Chapter assembly
# ---------------------------------------------------------------------


def assemble_chapters(
    paths: ProjectPaths,
    chapter: dict,
    chunk_records: list[dict],
    book_metadata: dict,
    options: AssemblyOptions,
    destination: Path,
    pauses: Mapping[str, float],
) -> Path:
    """Assemble one chapter into MP3 or M4A."""

    parts = collect_chapter_parts(
        paths=paths,
        chapter=chapter,
        chunk_records=chunk_records,
        include_intro=options.include_intro,
    )

    if not parts:
        raise ValueError(
            f"No WAV files found for chapter {chapter['id']}"
        )

    # Validate format compatibility before invoking FFmpeg.
    audio_format = validate_wav_files(
        [part.path for part in parts]
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Temporary files are created on the same filesystem as
    # the final output so the final replacement is atomic.
    with tempfile.TemporaryDirectory(
        prefix="assembly_",
        dir=destination.parent,
    ) as temporary_directory:

        temp_dir = Path(temporary_directory)

        silence_dir = (
            temp_dir / "silence"
        )

        silence_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        silence_cache = SilenceCache(
            directory=silence_dir,
            audio_format=audio_format,
        )

        manifest_path = (
            temp_dir / "concat.txt"
        )

        write_concat_manifest(
            destination=manifest_path,
            parts=parts,
            pauses=pauses,
            fallback_silence=options.silence_seconds,
            silence_cache=silence_cache,
        )

        # Keep the correct extension so FFmpeg recognizes
        # the desired output container.
        temporary_output = (
            temp_dir
            / f"chapter_output.{options.format}"
        )

        run_ffmpeg(
            manifest=manifest_path,
            destination=temporary_output,
            chapter=chapter,
            book_metadata=book_metadata,
            options=options,
        )

        if (
            not temporary_output.is_file()
            or temporary_output.stat().st_size == 0
        ):
            raise RuntimeError(
                "FFmpeg did not produce a valid output file"
            )

        # Only replace the final chapter after successful encoding.
        temporary_output.replace(destination)

    return destination


# ---------------------------------------------------------------------
# Book assembly
# ---------------------------------------------------------------------


def assemble_book(
    paths: ProjectPaths,
    options: AssemblyOptions | None = None,
    chapters: str | None = None,
) -> AssemblyResult:
    """Assemble selected chapters into individual audio files.

    Args:
        paths:
            Project directory structure.

        options:
            Encoding and silence configuration.

        chapters:
            Selection string, e.g. "1,3-5".
            None means all chapters.

    Returns:
        AssemblyResult containing generated and skipped files.
    """

    options = options or AssemblyOptions()

    pauses = merge_pauses(
        options.pauses
    )

    metadata = load_metadata(
        paths.metadata
    )

    chunks_by_chapter = load_chunks(
        paths.chunks
    )

    selected = parse_chapter_selection(
        chapters
    )

    output_directory = getattr(
        paths,
        "full_chapters",
        paths.audio / "full_chapters",
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = AssemblyResult()

    book_chapters = sorted(
        metadata["chapters"],
        key=lambda chapter: int(chapter["index"]),
    )

    available_indices = {
        int(chapter["index"])
        for chapter in book_chapters
    }

    if selected is not None:

        missing = selected - available_indices

        if missing:
            raise ValueError(
                f"Unknown chapter indices: {sorted(missing)}"
            )

    for chapter in book_chapters:

        chapter_index = int(
            chapter["index"]
        )

        if (
            selected is not None
            and chapter_index not in selected
        ):
            continue

        chapter_id = str(
            chapter["id"]
        )

        destination = (
            output_directory
            / f"chapter{chapter_index:04d}.{options.format}"
        )

        # ---------------------------------------------------------
        # Skip completed chapters unless overwrite is enabled.
        # ---------------------------------------------------------

        if destination.exists() and not options.overwrite:

            print(
                f"[SKIP] Chapter {chapter_index}: "
                f"{destination.name}"
            )

            result.skipped.append(destination)
            continue

        # ---------------------------------------------------------
        # Collect expected chunk records.
        # ---------------------------------------------------------

        chunk_records = chunks_by_chapter.get(
            chapter_id,
            [],
        )

        expected_count = chapter.get(
            "chunk_count"
        )

        if expected_count is not None:

            actual_count = len(
                [
                    row
                    for row in chunk_records
                    if int(row["chunk_index"]) != 0
                ]
            )

            if actual_count != int(expected_count):
                raise ValueError(
                    f"Chapter {chapter_index}: "
                    f"expected {expected_count} chunks, "
                    f"found {actual_count}"
                )

        # ---------------------------------------------------------
        # Assemble chapter.
        # ---------------------------------------------------------

        print(
            f"[ASSEMBLE] Chapter {chapter_index}: "
            f"{chapter.get('title', '')}"
        )

        output = assemble_chapters(
            paths=paths,
            chapter=chapter,
            chunk_records=chunk_records,
            book_metadata=metadata,
            options=options,
            destination=destination,
            pauses=pauses,
        )

        result.generated.append(output)

        print(
            f"[DONE] {output.name}"
        )

    print()
    print("Assembly completed:")
    print(f"  Generated: {len(result.generated)}")
    print(f"  Skipped:   {len(result.skipped)}")

    return result
