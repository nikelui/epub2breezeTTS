"""Minimal adapter for the user's Cython Breeze wrapper."""
from pathlib import Path


class BreezeBackend:
    def __init__(self, *, tts, voice, cfg_scale: float = 1.0):
        self.tts = tts
        self.voice = voice
        self.cfg_scale = cfg_scale

    def synthesize(self, text: str, output: Path, seed: int) -> None:
        from breeze import BreezeRequest

        request = BreezeRequest(
            text=text,
            ref_text=self.voice.transcript,
            cfg_scale=self.cfg_scale,
            seed=seed,
        )
        self.tts.generate_voice_wav(
            request,
            self.voice.codes,
            self.voice.frames,
            self.voice.n_codebooks,
            str(output),
        )
