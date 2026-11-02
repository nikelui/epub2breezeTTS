from __future__ import annotations

import argparse
import sys
from pathlib import Path

from epub_audiobook.cli import assemble_cli, audio_synthesis, book_info, process_text
from epub_audiobook.config import (
    DEFAULT_CONFIG_PATH,
    get_command_defaults,
    load_config,
    validate_and_coerce_defaults,
)


def add_config_argument(parser):
    parser.add_argument(
        "--config",
        type=Path,
        default=argparse.SUPPRESS,
        help="Application configuration file",
    )

def build_parser() -> tuple[argparse.ArgumentParser, dict[str, None]]:
    parser = argparse.ArgumentParser(
        prog="epub2breezeTTS",
        description="Extract text from an ebook and synthesisze a narrated audiobook using Breeze voice TTS.",
    )

    add_config_argument(parser)

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title="commands",
    )

    command_parsers = {
    "audio_synthesis": audio_synthesis.add_subparser(subparsers),
    "process_text": process_text.add_subparser(subparsers),
    "info": book_info.add_subparser(subparsers),
    "assemble_audiobook": assemble_cli.add_subparser(subparsers),
    }
    # Make --config available both before and after
    # the subcommand.
    for command_parser in command_parsers.values():
        add_config_argument(command_parser)

    return parser, command_parsers

# ---------------------------------------------------------
# Required argument validation
# ---------------------------------------------------------

REQUIRED_ARGUMENTS = {
    "process_text": (),
    "info": ("output_dir",),
    "audio_synthesis": ("output_dir",),
    "assemble_audiobook": ("output_dir",),
}

def validate_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:

    for name in REQUIRED_ARGUMENTS.get(
        args.command,
        (),
    ):

        if getattr(args, name, None) is None:
            parser.error(
                f"The argument for '{name}' must be "
                "provided either in the configuration "
                "file or on the command line."
            )

# ---------------------------------------------------------
# Two-pass parsing
# ---------------------------------------------------------

def parse_args(argv=None):

    if argv is None:
        argv = sys.argv[1:]

    parser, command_parsers = build_parser()

    # -----------------------------------------------------
    # PASS 1: discover the command and config path.
    # -----------------------------------------------------

    preliminary_args, _ = parser.parse_known_args(argv)

    config_path = getattr(
        preliminary_args,
        "config_file",
        None,
    )

    if config_path is None and DEFAULT_CONFIG_PATH.is_file():
        config_path = DEFAULT_CONFIG_PATH

    # -----------------------------------------------------
    # Load configuration.
    # -----------------------------------------------------

    try:
        config = load_config(config_path)
        command = preliminary_args.command
        defaults = get_command_defaults(
            config=config,
            command=command,
        )

        defaults = validate_and_coerce_defaults(
            command_parsers[command],
            defaults,
            command=command,
        )

    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))

    # -----------------------------------------------------
    # Install config values as parser defaults.
    # -----------------------------------------------------

    command_parsers[command].set_defaults(
        **defaults
    )


    # -----------------------------------------------------
    # PASS 2: parse everything again.
    #
    # Explicit CLI arguments override the defaults loaded
    # from the configuration.
    # -----------------------------------------------------

    args = parser.parse_args(argv)

    args.config_file = config_path
    args.app_config = config

    validate_args(parser, args)

    return args

def main():
    args = parse_args()
    return args.handler(args)

if __name__ == "__main__":
    raise SystemExit(main())
