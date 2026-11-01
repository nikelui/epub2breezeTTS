"""Standalone chapter assembly CLI; also callable from the main argparse CLI."""
import argparse

# import json
# import subprocess
# from ast import arguments
from pathlib import Path

from epub_audiobook.audio.assembler import AssemblyOptions, assemble_book
from epub_audiobook.audio.audiobook import AudiobookOptions, combine_m4b_book
from epub_audiobook.models import ProjectPaths
from epub_audiobook.pause_types import load_pause_config


def add_subparser(subparsers) -> None:
    parser = subparsers.add_parser('assemble_audiobook', help='Assemble audiobook chapters')
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pause-config", type=Path, default="config/assembly_pauses.json",
        help="JSON file containing silence durations by ending type")
    parser.add_argument("--format", choices=("mp3", "m4b"), default="m4b")
    parser.add_argument("--silence", type=float, default=0.1, help="Seconds between chunks")
    parser.add_argument("--bitrate", default="128k")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-intro", action="store_true")
    parser.add_argument("--chapters", help="Comma-separated chapter indices/ranges: 1,3-5")
    parser.add_argument("--combine", action=argparse.BooleanOptionalAction, default=False,
        help="Combine M4A chapters into a single bookmarked audiobook")
    parser.add_argument("--combine-chapters", type=str, default=None, metavar="SELECTION",
        help=("Chapters to include in the combined audiobook, "
            "for example 1,3-5. Defaults to all chapters."))
    parser.set_defaults(handler=main)


def parse_chapter_selection(value: str | None) -> set[int] | None:
    if value is None or value.lower() == "all":
        return None
    result: set[int] = set()
    for part in value.split(","):
        if "-" in part:
            a, b = map(int, part.strip().split("-", 1))
            if a < 1 or b < a:
                raise ValueError(f"Invalid range: {part}")
            result.update(range(a, b + 1))
        else:
            n = int(part.strip())
            if n < 1:
                raise ValueError(f"Invalid chapter: {part}")
            result.add(n)
    return result


# def verify_chapters(
#     path: Path,
#     expected_count: int,
#     ffprobe: str = "ffprobe",
# ) -> None:
#
#     command = [
#         ffprobe,
#         "-v", "error",
#         "-show_chapters",
#         "-of", "json",
#         str(path),
#     ]
#
#     result = subprocess.run(
#         command,
#         check=True,
#         capture_output=True,
#         text=True,
#     )
#
#     data = json.loads(result.stdout)
#
#     actual_count = len(data.get("chapters", []))
#
#     if actual_count != expected_count:
#         raise RuntimeError(
#             f"Expected {expected_count} chapters, "
#             f"found {actual_count} in {path}"
#         )


def main(args: argparse.Namespace) -> int:
    paths = ProjectPaths(args.output_dir)

    pauses = (
            load_pause_config(args.pause_config)
            if args.pause_config
            else None
        )

    options = AssemblyOptions(
        format=args.format,
        silence_seconds=args.silence,
        bitrate=args.bitrate,
        ffmpeg=args.ffmpeg,
        overwrite=args.overwrite,
        include_intro=not args.no_intro,
        pauses=pauses,
    )

    outputs = assemble_book(
                paths=paths,
                options=options,
                chapters=args.chapters,
        )
    if args.format == "m4b" and args.combine:

        print("Combining chapters into a single audiobook...")

        audiobook = combine_m4b_book(
            paths=paths,
            options=AudiobookOptions(
                ffmpeg=args.ffmpeg,
                ffprobe="ffprobe",
                overwrite=args.overwrite,
            ),
            chapters=args.combine_chapters,
        )

        print(f"Audiobook: {audiobook}")

    print("\nChapter assembly complete.\n")
    print(f"Generated: {len(outputs.generated)}\nSkipped:   {len(outputs.skipped)}")
    # for output in outputs:
    #     print(f"Created: {output}")
    return 0
