"""Atomic JSON manifest and generation fingerprints; sequential-writer design."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import wave


def fingerprint(text: str, *, model_identity: str, voice_identity: str,
                cfg_scale: float, seed: int) -> str:
    payload = {
        "text": text,
        "model": model_identity,
        "voice": voice_identity,
        "cfg_scale": cfg_scale,
        "seed": seed,
        "backend": "breeze-v1",
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def model_identity(path: Path) -> str:
    """Cheap identity; use model SHA256 instead for stronger invalidation."""
    stat = path.stat()
    return f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"


def valid_wav(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 44:
        return False
    try:
        with wave.open(str(path), "rb") as stream:
            return stream.getnframes() > 0 and stream.getframerate() > 0
    except (wave.Error, EOFError, OSError):
        return False


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
            if self.data.get("schema_version") != 1:
                raise ValueError("Unsupported progress manifest schema")
        else:
            self.data = {"schema_version": 1, "chunks": {}}

    def get(self, chunk_id: str) -> dict | None:
        return self.data["chunks"].get(chunk_id)

    def update(self, chunk_id: str, **properties) -> None:
        self.data["chunks"][chunk_id] = properties
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".progress-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(self.data, output, indent=2, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
