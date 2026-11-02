import argparse  # noqa: I001
from pathlib import Path
from epub_audiobook.book_info import print_book_info
from epub_audiobook.models import ProjectPaths

def add_subparser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser('info', help='Print information about a processed book.')
    parser.add_argument("--output-dir", type=Path, default=argparse.SUPPRESS)
    parser.add_argument("--chunks", action=argparse.BooleanOptionalAction,
        default=argparse.SUPPRESS, help="List each chunk and its status")

    parser.set_defaults(handler=main)
    return parser

def main(args: argparse.Namespace):
    out_dir = Path(args.output_dir)
    proj_dir = ProjectPaths(out_dir)

    print_book_info(proj_dir, show_chunks=args.chunks)
