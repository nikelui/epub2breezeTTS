"""pySBD produces *candidate* sentence ends, not final TTS chunks."""
from functools import lru_cache


@lru_cache(maxsize=8)
def _segmenter(language: str):
    import pysbd
    return pysbd.Segmenter(language=language, clean=False, char_span=True)


def sentence_ends(text: str, language: str = 'en') -> set[int]:
    """Character offsets measured in the unmodified chapter string."""
    return {span.end for span in _segmenter(language).segment(text)}
