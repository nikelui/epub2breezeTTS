"""Standalone chapter assembly CLI; also callable from the main argparse CLI."""
import argparse
from pathlib import Path

from epub_audiobook.audio.assembler import AssemblyOptions, assemble_chapters


def add_subparser(subparsers) -> None:
    parser = subparsers.add_parser('assemble_audiobook', help='Assemble audiobook chapters')
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--format", choices=("mp3", "m4a"), default="mp3")
    parser.add_argument("--silence", type=float, default=0.1, help="Seconds between chunks")
    parser.add_argument("--bitrate", default="128k")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-intro", action="store_true")
    parser.add_argument("--chapters", help="Comma-separated chapter indices/ranges: 1,3-5")
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


def main(args: argparse.Namespace) -> int:
    from epub_audiobook.models import ProjectPaths
    paths = ProjectPaths(args.output_dir)
    options = AssemblyOptions(
        format=args.format, silence_seconds=args.silence, bitrate=args.bitrate,
        ffmpeg=args.ffmpeg, overwrite=args.overwrite, include_intro=not args.no_intro,
    )
    outputs = assemble_chapters(paths, options=options, chapter_indices=parse_chapter_selection(args.chapters))
    
    print("\nChapter assembly complete.\n")
    print(f"Generated: {len(outputs.generated)}\nSkipped:   {len(outputs.skipped)}")
    # for output in outputs:
    #     print(f"Created: {output}")
    return 0


# def main(argv=None):
#     parser = argparse.ArgumentParser(description="Assemble audiobook chapters")
#     configure_parser(parser)
#     return run_assemble(parser.parse_args(argv))

#
# if __name__ == "__main__":
#     raise SystemExit(main())
