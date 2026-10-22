"""HTTP synthesis for HoppouAI/Breeze-TTS-2.cpp breeze-server.

Requires requests. Works with a user-managed or programmatically launched server.
"""
from __future__ import annotations

import hashlib
import wave
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass(frozen=True)
class HTTPVoice:
    """Use either a saved voice ID or a reference WAV and exact transcript."""

    voice_id: str | None = None
    reference_wav: Path | None = None
    transcript: str | None = None

    def __post_init__(self):
        if bool(self.voice_id) == bool(self.reference_wav):
            raise ValueError("Specify exactly one of voice_id or reference_wav")
        if self.reference_wav is not None:
            if not self.transcript:
                raise ValueError("reference_wav requires transcript")
            if not Path(self.reference_wav).is_file():
                raise FileNotFoundError(self.reference_wav)

    def identity(self) -> str:
        if self.voice_id:
            return f"server_voice:{self.voice_id}"
        wav = Path(self.reference_wav)
        digest = hashlib.sha256()
        with wav.open('rb') as file:
            for block in iter(lambda: file.read(1024 * 1024), b''):
                digest.update(block)
        digest.update((self.transcript or '').encode('utf-8'))
        return f"ref_wav:{digest.hexdigest()}"


class BreezeHTTPBackend:
    """Same synthesize(text, output, seed) contract as BreezeBackend."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8080",
        voice: HTTPVoice,
        cfg_scale: float = 1.0,
        instruction: str | None = None,
        split_chars: int | None = None,
        timeout: float = 600.0,
        connect_timeout: float = 10.0,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip('/')
        self.voice = voice
        self.cfg_scale = cfg_scale
        self.instruction = instruction
        self.split_chars = split_chars
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self._owned_session = session is None
        self.session = session or requests.Session()

    def close(self) -> None:
        if self._owned_session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def health(self) -> dict:
        response = self.session.get(
            f"{self.base_url}/health", timeout=self.connect_timeout
        )
        response.raise_for_status()
        data = response.json()
        if data.get('status') != 'ok':
            raise RuntimeError(f"Unexpected Breeze health response: {data!r}")
        return data

    def synthesize(self, text: str, output: Path, seed: int) -> None:
        if not text.strip():
            raise ValueError("Cannot synthesize empty text")
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        fields = {
            'text': text,
            'cfg_scale': str(self.cfg_scale),
            'seed': str(seed),
        }
        if self.instruction is not None:
            fields['instruction'] = self.instruction
        if self.split_chars is not None:
            fields['split_chars'] = str(self.split_chars)
        if self.voice.voice_id:
            fields['voice_id'] = self.voice.voice_id

        wav_ref = self.voice.reference_wav
        # requests uses urlencoded form when no files are supplied, multipart otherwise.
        try:
            if wav_ref is not None:
                with Path(wav_ref).open('rb') as ref:
                    response = self.session.post(
                        f"{self.base_url}/v1/audio/speech",
                        data={**fields, 'ref_text': self.voice.transcript},
                        files={'ref_audio': (Path(wav_ref).name, ref, 'audio/wav')},
                        stream=True,
                        timeout=(self.connect_timeout, self.timeout),
                    )
            else:
                response = self.session.post(
                    f"{self.base_url}/v1/audio/speech",
                    data=fields,
                    stream=True,
                    timeout=(self.connect_timeout, self.timeout),
                )
            with response:
                response.raise_for_status()
                if 'audio/pcm' not in response.headers.get('Content-Type', '').lower():
                    raise RuntimeError('Expected audio/pcm, received: ' + str(response.headers.get('Content-Type')))
                if response.headers.get('X-Sample-Format', 's16le').lower() != 's16le':
                    raise RuntimeError('Unsupported PCM sample format')
                sample_rate = int(response.headers.get('X-Sample-Rate', '24000'))
                if sample_rate <= 0:
                    raise RuntimeError('Invalid sample rate')
                total = 0
                # Generator calls us with a *.partial.wav filename; it commits the final file.
                # The streamed result is PCM, converted incrementally to a WAV.
                with wave.open(str(output), 'wb') as dst:
                    dst.setnchannels(1)
                    dst.setsampwidth(2)
                    dst.setframerate(sample_rate)
                    leftover = b''
                    for block in response.iter_content(chunk_size=65536):
                        if not block:
                            continue
                        data = leftover + block
                        complete = len(data) & ~1
                        dst.writeframesraw(data[:complete])
                        total += complete
                        leftover = data[complete:]
                    if leftover or total == 0:
                        raise RuntimeError('Empty or odd-length PCM stream')
        except Exception:
            output.unlink(missing_ok=True)
            raise
