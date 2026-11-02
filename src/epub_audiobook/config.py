"""Application configuration loading."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("config/config.json")

# ---------------------------------------------------------
# Built-in defaults
# ---------------------------------------------------------

COMMAND_DEFAULTS: dict[str, dict[str, Any]] = {

    "process_text": {
        "output_dir": Path("output/"),
        "max_chars": 400,
        "target_chars": 300,
        "min_chars": 150,
        "verbose": False,
        "book_structure": False,
    },

    "info": {
        "output_dir": None,
        "chunks": False,
    },

    "audio_synthesis": {
        "backend": None,
        "output_dir": None,
        "model": None,
        "reference_wav": None,
        "reference_text": None,
        "voice_dir": None,
        "voice_id": None,
        "chapters": None,
        "chapter_intro": None,
        "cfg_scale": 1.0,
        "seed": 42,
        "cpu": False,
        "force": False,
        "retry_failed": True,
        "chapter_intro_options": {
            "prefix": "Chapter",
            "include_prefix": True,
            "include_id": True,
            "include_title": True,
            "roman_to_decimal": False,
            "prefix_id_separator": " ",
            "title_separator": ". ",
        },
        # Configuration-only settings
        "server": {
            "managed": False,
            "executable": "breeze_native/breeze-server",
            "model": None,
            "host": "127.0.0.1",
            "port": 8080,
            "ws_port": -1,
        },

        "http": {
            "url": "http://127.0.0.1:8080",
            "voice_id": "default",
            "split_chars": 0,
            "timeout": 600,
            "model_version": None,
        },
    },

    "assemble_audiobook": {
        "output_dir": None,
        "pause_config": Path("config/assembly_pauses.json"),
        "format": "m4b",
        "bitrate": "128k",
        "ffmpeg": "ffmpeg",
        "ffprobe": "ffprobe",
        "overwrite": False,
        "include_intro": True,
        "chapters": None,
        "combine": False,
        "combine_chapters": None,
    },
}

# ---------------------------------------------------------
# Configuration section mapping
# ---------------------------------------------------------

COMMAND_CONFIG_SECTIONS = {

    "process_text": (
        "process_text",
    ),

    "info": (
        "book_info",
    ),

    "audio_synthesis": (
        "audio_synthesis",
    ),

    "assemble_audiobook": (
        "tools",
        "chapter_assembly",
        "audiobook_assembly",
    ),
}

# Configuration-only attributes that are not individual
# argparse arguments.
CONFIG_ONLY_KEYS = {
    "audio_synthesis": {
        "server",
        "http",
        "chapter_intro_options",
    }
}

def deep_merge(
    base: dict,
    override: dict,
) -> dict:
    """Recursively merge dictionaries.

    Values from override take precedence.
    """

    result = deepcopy(base)

    for key, value in override.items():

        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(
                result[key],
                value,
            )

        else:
            result[key] = deepcopy(value)

    return result


def load_config(path: Path | str | None) -> dict[str, Any]:
    """Load the centralized JSON configuration."""

    if path is None:
        return {}

    path = Path(path).expanduser()

    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON configuration: {path}\n{exc}"
        ) from exc

    if not isinstance(config, dict):
        raise TypeError("Configuration root must be a JSON object")

    return config

# ---------------------------------------------------------
# Merge defaults and configuration sections
# ---------------------------------------------------------

def get_command_defaults(
    config: dict[str, Any],
    command: str,
) -> dict[str, Any]:
    """Return merged defaults for a CLI command.

        Precedence:
            Built-in defaults
            -> shared configuration
            -> command-specific configuration
        """

    defaults = deepcopy(COMMAND_DEFAULTS.get(command, {}))

    for section_name in COMMAND_CONFIG_SECTIONS.get(command, ()):
        section = config.get(section_name, {})

        if not isinstance(section, dict):
            raise TypeError(
                    f"Configuration section "
                    f"'{section_name}' must be a JSON object")

        defaults = deep_merge(defaults, section)

    return defaults

    # ---------------------------------------------------------
    # Convert and validate configuration values
    # ---------------------------------------------------------
def coerce_config_value(
    action: argparse.Action,
    value: Any,
) -> Any:
    """Convert a configuration value using its argparse action."""

    if value is None:
        return None

    if isinstance(action, argparse.BooleanOptionalAction):
        if not isinstance(value, bool):
            raise TypeError(
                f"Expected boolean for '{action.dest}', "
                f"got {value!r}")

    elif action.type is not None:
        try:
            value = action.type(value)

        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid value for '{action.dest}': {value!r}"
            ) from exc

    if action.choices is not None and value not in action.choices:
        raise ValueError(
            f"Invalid value for '{action.dest}': {value!r}. "
            f"Expected one of: {action.choices}"
        )

    return value


def validate_and_coerce_defaults(
    parser: argparse.ArgumentParser,
    defaults: dict[str, Any],
    command: str
) -> dict[str, Any]:
    """Validate configuration keys against parser arguments."""

    actions = {
        action.dest: action
        for action in parser._actions
        if action.dest != "help"
    }

    config_only = CONFIG_ONLY_KEYS.get(command, set())
    result = {}

    for key, value in defaults.items():

        if key in config_only:
            if not isinstance(value, dict):
                raise ValueError(
                    f"Configuration setting '{key}' "
                    "must be a JSON object"
                )

            result[key] = deepcopy(value)
            continue

        action = actions.get(key)

        if action is None:
            raise ValueError(
                f"Unknown configuration parameter '{key}'. "
                f"Check the configuration section for this command.")

        result[key] = coerce_config_value(action, value)

    return result
