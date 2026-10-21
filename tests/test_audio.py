import json
import wave

import pytest

from epub_audiobook.audio.generator import (
    AudioChunk,
    generate_selected,
    read_chunks_jsonl,
)
from epub_audiobook.audio.selection import select_chapters


def wav_writer(text, path, seed):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 160)


def test_selection():
    assert select_chapters("1,3-4", {1, 2, 3, 4}) == [1, 3, 4]
    assert select_chapters("all", {1, 2}) == [1, 2]
    with pytest.raises(ValueError):
        select_chapters("2-7", {1, 2, 3})


def test_resume_and_force(tmp_path):
    chunks = [AudioChunk("ch0001-c000001", "ch0001", 1, 1, "Hello"),
              AudioChunk("ch0002-c000001", "ch0002", 2, 1, "World")]
    called = []

    def synth(text, output, seed):
        called.append(text)
        wav_writer(text, output, seed)

    kwargs = dict(chunks=chunks, output_dir=tmp_path, synthesize=synth,
                  model_identity="m", voice_identity="v", chapters="1")
    assert generate_selected(**kwargs).generated == 1
    assert generate_selected(**kwargs).skipped == 1
    assert called == ["Hello"]
    assert generate_selected(**kwargs, force=True).generated == 1
    assert called == ["Hello", "Hello"]
    kwargs["chunks"] = [AudioChunk("ch0001-c000001", "ch0001", 1, 1, "Changed")]
    assert generate_selected(**kwargs).generated == 1


def test_fail_retry(tmp_path):
    chunks = [AudioChunk("ch0001-c000001", "ch0001", 1, 1, "Hello")]

    def fail(text, output, seed):
        output.write_bytes(b"broken")
        raise RuntimeError("failure")

    kwargs = dict(chunks=chunks, output_dir=tmp_path,
                  model_identity="m", voice_identity="v")
    assert generate_selected(**kwargs, synthesize=fail).failed == 1
    assert not list(tmp_path.rglob("*.partial.wav"))
    assert generate_selected(**kwargs, synthesize=wav_writer).generated == 1
    assert json.loads((tmp_path / "progress.json").read_text())["chunks"][chunks[0].id]["status"] == "completed"


def test_jsonl(tmp_path):
    source = tmp_path / "chunks.jsonl"
    source.write_text(json.dumps({"id": "ch0001-c000001", "chapter_id": "ch0001", "chapter_index": 1, "chunk_index": 1, "text": "Original", "tts_text": "Spoken"}) + "\n")
    assert read_chunks_jsonl(source)[0].text == "Spoken"
