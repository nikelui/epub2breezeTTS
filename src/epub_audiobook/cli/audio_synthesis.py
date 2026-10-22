"""Optional standalone CLI entry point"""
from __future__ import annotations

import argparse
import json
import logging
from contextlib import nullcontext
from pathlib import Path

from epub_audiobook.audio.generator import generate_selected, read_chunks_jsonl
from epub_audiobook.audio.http_backend import BreezeHTTPBackend, HTTPVoice
from epub_audiobook.audio.progress import file_sha256, model_identity
from epub_audiobook.audio.server_process import ManagedBreezeServer, ServerConfig


def add_subparser(subparsers):
    parser = subparsers.add_parser('audio_synthesis', help='Generate audio from text chunks')
    parser.add_argument('--backend', choices=('cython', 'http'), default=None)
    parser.add_argument("--chunks", type=Path, required=True, help="Chapter-level chunks.jsonl")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True, help="GGUF path")
    parser.add_argument('--reference-wav', type=Path, help='HTTP reference audio for cloning')
    parser.add_argument('--reference-text', help='Exact transcript of HTTP reference WAV')
    parser.add_argument("--voice", type=Path, required=True, help="Saved voice path")
    parser.add_argument('--voice-id', help='Registered HTTP server voice ID')
    parser.add_argument("--chapters", help='e.g. "1,3-5" (overrides config)')
    parser.add_argument("--chapter-intro", action=argparse.BooleanOptionalAction, default=None, help="Generate a spoken chapter heading")
    parser.add_argument("--config", type=Path, help="Optional JSON config; supports chapters")
    parser.add_argument("--cfg-scale", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--force", action="store_true", help="Regenerate selected WAVs")
    parser.add_argument("--no-retry-failed", action="store_true")

    parser.set_defaults(handler=main)

def main(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
    chapter_spec = args.chapters if args.chapters is not None else config.get("chapters", "all")
    chapter_intro = (
        args.chapter_intro
        if args.chapter_intro is not None
        else config.get("chapter_intro", True)
    )
    chunks = read_chunks_jsonl(args.chunks)
    cfg_scale = args.cfg_scale if args.cfg_scale is not None else config.get('cfg_scale', 1.0)
    backend_kind = args.backend or config.get('backend', 'cython')

    def generate(synthesizer, *, model_key: str, voice_key: str):
            return generate_selected(
                chunks=chunks, output_dir=args.output_dir, synthesize=synthesizer,
                model_identity=model_key, voice_identity=voice_key,
                cfg_scale=cfg_scale, seed=args.seed, chapters=chapter_spec,
                force=args.force, retry_failed=not args.no_retry_failed,
                chapter_intro=chapter_intro,
            )

    if backend_kind == 'cython':
        # Adjust this line if your custom load_voice signature differs.
        from breeze import BreezeWrapper, load_voice

        from epub_audiobook.audio.breeze_backend import BreezeBackend

        voice = load_voice(str(args.voice))
        with BreezeWrapper(gguf_path=str(args.model), use_gpu=not args.cpu) as tts:
            backend = BreezeBackend(tts=tts, voice=voice, cfg_scale=cfg_scale)
            result = generate_selected(
                chunks=chunks, output_dir=args.output_dir, synthesize=backend.synthesize,
                model_identity=model_identity(args.model),
                voice_identity=file_sha256(args.voice) + ":" + voice.transcript,
                cfg_scale=cfg_scale, seed=args.seed, chapters=chapter_spec,
                force=args.force, retry_failed=not args.no_retry_failed,
                chapter_intro=chapter_intro,
            )

    elif backend_kind == 'http':
            server_cfg = config.get('server', {})
            managed = bool(server_cfg.get('managed', False))
            model = args.model or (Path(server_cfg['model']) if server_cfg.get('model') else None)
            if managed and model is None:
                args.parser.error('Managed HTTP mode requires --model or server.model in config')
            if managed:
                options = {k: v for k, v in server_cfg.items()
                           if k in ServerConfig.__dataclass_fields__ and k not in ('model',)}
                if args.cpu:
                    options['cpu'] = True
                context = ManagedBreezeServer(ServerConfig(model=str(model), **options))
            else:
                context = nullcontext(None)
            http_cfg = config.get('http', {})
            voice_id = args.voice_id or http_cfg.get('voice_id')
            reference_wav = args.reference_wav or http_cfg.get('reference_wav')
            reference_text = args.reference_text or http_cfg.get('reference_text')
            voice = HTTPVoice(voice_id=voice_id,
                              reference_wav=Path(reference_wav) if reference_wav else None,
                              transcript=reference_text)
            # Identity includes settings not otherwise recorded in the manifest signature.
            params_key = json.dumps({
                'backend': 'http', 'instruction': http_cfg.get('instruction'),
                'split_chars': http_cfg.get('split_chars'),
            }, sort_keys=True)
            with context as server:
                url = server.url if server is not None else http_cfg.get('url', 'http://127.0.0.1:8080')
                with BreezeHTTPBackend(
                    base_url=url, voice=voice, cfg_scale=cfg_scale,
                    instruction=http_cfg.get('instruction'), split_chars=http_cfg.get('split_chars'),
                    timeout=float(http_cfg.get('timeout', 600)),
                ) as backend:
                    backend.health()
                    # An external server cannot be reliably identified through /health.
                    # Supply a stable version identifier when external to invalidate old audio
                    # after changing its model or server build.
                    model_key = (model_identity(model) if model is not None else
                                 'external:' + str(http_cfg.get('model_version', 'unspecified')))
                    result = generate(backend.synthesize, model_key=model_key,
                                      voice_key=voice.identity() + ':' + params_key)
    else:
        args.parser.error(f'Unknown backend: {backend_kind}')
    if result:
        print(f'Generated: {result.generated}; skipped: {result.skipped}; failed: {result.failed}')
        return 1 if result.failed else 0


# if __name__ == "__main__":
#     raise SystemExit(main())
