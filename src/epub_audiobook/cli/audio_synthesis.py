"""Optional standalone CLI entry point"""
import argparse
import json
import logging
from pathlib import Path

from epub_audiobook.audio.generator import generate_selected, read_chunks_jsonl
from epub_audiobook.audio.progress import file_sha256, model_identity


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate chunk WAVs with Breeze")
    parser.add_argument("--chunks", type=Path, required=True, help="Chapter-level chunks.jsonl")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True, help="GGUF path")
    parser.add_argument("--voice", type=Path, required=True, help="Saved voice path")
    parser.add_argument("--chapters", help='e.g. "1,3-5" (overrides config)')
    parser.add_argument("--config", type=Path, help="Optional JSON config; supports chapters")
    parser.add_argument("--cfg-scale", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--force", action="store_true", help="Regenerate selected WAVs")
    parser.add_argument("--no-retry-failed", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
    chapter_spec = args.chapters if args.chapters is not None else config.get("chapters", "all")
    chunks = read_chunks_jsonl(args.chunks)

    # Adjust this line if your custom load_voice signature differs.
    from breeze import BreezeWrapper, load_voice

    from epub_audiobook.audio.breeze_backend import BreezeBackend

    voice = load_voice(str(args.voice))
    with BreezeWrapper(gguf_path=str(args.model), use_gpu=not args.cpu) as tts:
        backend = BreezeBackend(tts=tts, voice=voice, cfg_scale=args.cfg_scale)
        result = generate_selected(
            chunks=chunks, output_dir=args.output_dir, synthesize=backend.synthesize,
            model_identity=model_identity(args.model),
            voice_identity=file_sha256(args.voice) + ":" + voice.transcript,
            cfg_scale=args.cfg_scale, seed=args.seed, chapters=chapter_spec,
            force=args.force, retry_failed=not args.no_retry_failed,
        )
    print(f"Generated: {result.generated}; skipped: {result.skipped}; failed: {result.failed}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
