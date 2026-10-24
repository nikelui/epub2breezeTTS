import argparse  # noqa: I001
from pathlib import Path
from epub_audiobook.book_info import print_book_info
from epub_audiobook.models import ProjectPaths

def add_subparser(subparsers):
    parser = subparsers.add_parser('info', help='Print information about a processed book.')
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--chunks", action="store_true", help="List each chunk and its status")

    parser.set_defaults(handler=main)

def main(args: argparse.Namespace):
    out_dir = Path(args.output_dir)
    proj_dir = ProjectPaths(out_dir)

    print_book_info(proj_dir, show_chunks=args.chunks)
