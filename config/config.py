"""Application configuration loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("config/config.json")


def load_config(path: Path | str | None) -> dict[str, Any]:
    """Load the application configuration."""

    if path is None:
        return {}

    path = Path(path).expanduser()

    if not path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    if not isinstance(config, dict):
        raise TypeError(
            "Configuration must contain a JSON object"
        )

    return config


# Configuration sections applied to each command.
COMMAND_CONFIG_SECTIONS = {
    "info": (),
    "process_text": (),
    "audio_synthesis": (
        "audio_generation",
    ),
    "assemble_audiobook": (
        "tools",
        "chapter_assembly",
        "audiobook_assembly",
    ),
}


# Built-in defaults.
#
# These are used when a value is neither in the configuration
# nor explicitly supplied on the command line.

COMMAND_DEFAULTS = {
    "assemble_audiobook": {
        "format": "m4a",
        "bitrate": "128k",
        "ffmpeg": "ffmpeg",
        "ffprobe": "ffprobe",
        "overwrite": False,
        "include_intro": True,
        "pause_config": None,
        "combine": True,
        "combine_chapters": None,
        "chapters": None,
    }
}


def get_command_defaults(
    config: dict[str, Any],
    command: str,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Return merged defaults for a specific CLI command.

    Configuration sections are merged in order.
    Later sections override earlier ones.
    """

    defaults = COMMAND_DEFAULTS.get(
        command,
        {},
    ).copy()

    sections = COMMAND_CONFIG_SECTIONS.get(
        command,
        (),
    )

    for section_name in sections:

        section = config.get(section_name, {})

        if not isinstance(section, dict):
            raise TypeError(
                f"Configuration section "
                f"{section_name!r} must be an object"
            )

        defaults.update(section)

    # Resolve configuration-relative file paths.
    pause_config = defaults.get("pause_config")

    if pause_config and config_path:

        pause_path = Path(pause_config).expanduser()

        if not pause_path.is_absolute():
            defaults["pause_config"] = (
                config_path.parent / pause_path
            ).resolve()

    return defaults
