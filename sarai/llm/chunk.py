"""Map-reduce chunking for long meetings.

A 90-minute meeting is roughly 60k characters of Thai, past what any provider
handles well in one call with reliable JSON output. Splitting happens at segment
boundaries only: half a speaker turn tells the model nothing, and cutting inside
a Thai sentence has no word boundary to land on.
"""

from __future__ import annotations

from sarai.models import Segment


def total_chars(segments: list[Segment]) -> int:
    return sum(len(s.text) for s in segments)


def split_segments(
    segments: list[Segment], *, max_chars: int, overlap: int = 2
) -> list[list[Segment]]:
    """Consecutive chunks under `max_chars`, each repeating the previous chunk's
    last `overlap` segments so a decision spoken across the seam is not lost.

    A single segment longer than `max_chars` gets a chunk of its own rather than
    being cut: the model handles one oversized turn far better than a severed
    sentence.
    """
    if not segments:
        return []
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    chunks: list[list[Segment]] = []
    current: list[Segment] = []
    size = 0

    for seg in segments:
        length = len(seg.text)
        if current and size + length > max_chars:
            chunks.append(current)
            tail = current[-overlap:] if overlap > 0 else []
            current = list(tail)
            size = sum(len(s.text) for s in current)
        current.append(seg)
        size += length

    if current:
        # The overlap tail can be all that is left when the last real segment
        # exactly filled the previous chunk; that carries no new content.
        if chunks and all(s in chunks[-1] for s in current):
            return chunks
        chunks.append(current)
    return chunks
