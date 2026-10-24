import argparse

from epub_audiobook.cli import audio_synthesis, process_text, book_info


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epub2breezeTTS",
        description="Extract text from an ebook and synthesisze a narrated audiobook using Breeze voice TTS.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title="commands",
    )

    audio_synthesis.add_subparser(subparsers)
    process_text.add_subparser(subparsers)
    book_info.add_subparser(subparsers)
    return parser

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
