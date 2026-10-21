import argparse

from . import audio_synthesis, process_text

# def main():
#     # Create the top-level parser
#     parser = argparse.ArgumentParser(description="epub2breezeTTS - Process EPUBs and generate audiobooks")
#     subparsers = parser.add_subparsers(dest='command', help='Available commands')
#
#     # Add the audio_synthesis subparser
#     from epub_audiobook.cli.audio_synthesis import add_subparser as add_audio_subparser
#     add_audio_subparser(subparsers)
#
#     # Add the process_text subparser
#     from epub_audiobook.cli.process_text import add_subparser as add_text_subparser
#     add_text_subparser(subparsers)
#
#     args = parser.parse_args()
#
#     if args.command == 'audio_synthesis':
#         from epub_audiobook.cli.audio_synthesis import main as audio_main
#         return audio_main(vars(args))
#     elif args.command == 'process_text':
#         from epub_audiobook.cli.process_text import main as text_main
#         return text_main(vars(args))
#     else:
#         parser.print_help()
#         return 1

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
    return parser

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
