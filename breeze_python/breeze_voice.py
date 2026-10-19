"""Read Breeze-TTS-2.cpp version-1 saved voice files without native dependencies.

Layout: BRZV, five little-endian uint32 fields (version, sample rate,
codebooks, frames, UTF-8 byte length), transcript, then frame-major int32.
"""
from pathlib import Path
import struct
from typing import NamedTuple

_HEADER = struct.Struct('<4s5I')
_INT32_SIZE = 4


class SavedVoice(NamedTuple):
    codes: list[int]
    n_codebooks: int
    transcript: str
    frames: int
    sample_rate: int


def load_voice(path: str | Path) -> SavedVoice:
    """Load and validate a .breeze file, preserving flat frame-major code order.

    A value for frame f and codebook c is codes[f * n_codebooks + c].
    """
    path = Path(path)
    with path.open('rb') as file:
        header = file.read(_HEADER.size)
        if len(header) != _HEADER.size:
            raise ValueError(f'{path}: truncated .breeze header')
        magic, version, sample_rate, n_codebooks, frames, text_bytes = _HEADER.unpack(header)
        if magic != b'BRZV':
            raise ValueError(f'{path}: invalid magic (expected BRZV)')
        if version != 1:
            raise ValueError(f'{path}: unsupported .breeze version {version}')
        if not sample_rate or not n_codebooks or not frames:
            raise ValueError(f'{path}: invalid sample rate / dimensions')

        # Bounds checking before materializing potentially large arrays.
        file_size = path.stat().st_size
        expected_size = _HEADER.size + text_bytes + frames * n_codebooks * _INT32_SIZE
        if file_size != expected_size:
            raise ValueError(
                f'{path}: size mismatch: expected {expected_size} bytes, '
                f'found {file_size}'
            )
        transcript = file.read(text_bytes).decode('utf-8')
        raw = file.read(frames * n_codebooks * _INT32_SIZE)

    # Little-endian int32 regardless of host endianness / C long width.
    codes = [value[0] for value in struct.iter_unpack('<i', raw)]
    return SavedVoice(codes, n_codebooks, transcript, frames, sample_rate)


def read_voice(path: str | Path) -> tuple[list[int], int, str]:
    """Return (flat_codes, number_of_codebooks, audio_transcript)."""
    voice = load_voice(path)
    return voice.codes, voice.n_codebooks, voice.transcript
