from epub_audiobook.models import Chapter, Paragraph
from epub_audiobook.text.chapter_text import build_chapter_text
from epub_audiobook.text.chunker import ChunkConfig, chunk_chapter


def chapter(*texts):
    return Chapter('ch0001', 1, 'Title', 'chap.xhtml', [
        Paragraph(f'ch0001-p{i:04d}', i, text)
        for i, text in enumerate(texts, 1)
    ])


def test_roundtrip_and_spans():
    c = chapter('  The wizard approached.  ', 'He hesitated.', '“Who is there?” she asked.')
    source = build_chapter_text(c)
    chunks = chunk_chapter(c, ChunkConfig(30, 45, 80))
    assert chunks
    spans_by_id = {p.id: p.text for p in c.paragraphs}
    for chunk in chunks:
        assert chunk.sources
        for span in chunk.sources:
            p = spans_by_id[span.paragraph_id]
            assert 0 <= span.start_char < span.end_char <= len(p)
        assert chunk.tts_text == chunk.text
    # All non-whitespace content is preserved, in the same order.
    assert ''.join(ch for chunk in chunks for ch in chunk.text if not ch.isspace()) == \
           ''.join(ch for ch in source.text if not ch.isspace())


def test_short_paragraphs_can_merge():
    c = chapter('The room was silent.', 'Nobody moved.', 'Then the lights went out.')
    chunks = chunk_chapter(c, ChunkConfig(20, 70, 100))
    assert len(chunks) == 1
    assert len(chunks[0].sources) == 3


def test_dialogue_attribution_prefers_staying_together():
    c = chapter('“Where are you going?” she asked. “I am leaving now,” he said.')
    chunks = chunk_chapter(c, ChunkConfig(15, 42, 65))
    assert all(not chunk.text.endswith('going?”') for chunk in chunks)


def test_offsets_preserve_leading_whitespace():
    c = chapter('  Hello there.  ')
    chunk = chunk_chapter(c)[0]
    assert chunk.text == 'Hello there.'
    assert chunk.sources[0].start_char == 2
    assert chunk.sources[0].end_char == 14


def test_empty_chapter():
    assert chunk_chapter(chapter('   ')) == []
