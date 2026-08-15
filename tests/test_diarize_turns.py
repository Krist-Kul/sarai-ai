"""Turn shaping: merge fragments, split monologues, drop scraps."""

from __future__ import annotations

import numpy as np

from sarai.worker.diarize import (
    MAX_TURN_SECONDS,
    Turn,
    merge_turns,
    quietest_offset,
    rms_envelope,
    shape_turns,
    split_long_turn,
)

SR = 16_000


def test_merge_joins_same_speaker_across_a_breath() -> None:
    turns = [
        Turn(0.0, 2.0, "SPEAKER_00"),
        Turn(2.3, 5.0, "SPEAKER_00"),  # 0.3s gap -> same utterance
    ]
    assert merge_turns(turns) == [Turn(0.0, 5.0, "SPEAKER_00")]


def test_merge_keeps_different_speakers_apart() -> None:
    turns = [Turn(0.0, 2.0, "SPEAKER_00"), Turn(2.1, 4.0, "SPEAKER_01")]
    assert merge_turns(turns) == turns


def test_merge_keeps_a_real_pause() -> None:
    turns = [Turn(0.0, 2.0, "SPEAKER_00"), Turn(3.0, 4.0, "SPEAKER_00")]
    assert merge_turns(turns) == turns


def test_merge_sorts_and_absorbs_overlap() -> None:
    turns = [Turn(2.0, 6.0, "SPEAKER_00"), Turn(0.0, 3.0, "SPEAKER_00")]
    assert merge_turns(turns) == [Turn(0.0, 6.0, "SPEAKER_00")]


def test_merge_of_nothing_is_nothing() -> None:
    assert merge_turns([]) == []


def test_short_turn_is_left_alone() -> None:
    turn = Turn(0.0, 12.0, "SPEAKER_00")
    assert split_long_turn(turn, None, SR) == [turn]


def test_long_turn_is_split_below_the_limit() -> None:
    turn = Turn(0.0, 95.0, "SPEAKER_00")
    pieces = split_long_turn(turn, None, SR)
    assert len(pieces) > 1
    assert all(p.duration <= MAX_TURN_SECONDS + 1e-6 for p in pieces)
    # Splitting must not lose or invent audio.
    assert pieces[0].start == 0.0
    assert pieces[-1].end == 95.0
    for a, b in zip(pieces, pieces[1:], strict=False):
        assert a.end == b.start


def test_split_prefers_silence_over_the_midpoint() -> None:
    """A 40s turn with a silent gap at 24s must be cut at the gap, not at 20s."""
    samples = np.ones(int(40 * SR), dtype=np.float32) * 0.5
    quiet_start, quiet_end = int(23.9 * SR), int(24.1 * SR)
    samples[quiet_start:quiet_end] = 0.0

    energy = rms_envelope(samples, SR)
    pieces = split_long_turn(Turn(0.0, 40.0, "SPEAKER_00"), energy, SR)

    assert len(pieces) == 2
    assert pieces[0].end == pieces[1].start
    assert 23.8 < pieces[0].end < 24.2


def test_quietest_offset_ignores_audio_outside_the_window() -> None:
    energy = np.ones(10 * SR, dtype=np.float32)
    energy[int(1.0 * SR)] = 0.0  # quietest point, but outside the search window
    energy[int(6.0 * SR)] = 0.1
    offset = quietest_offset(energy, SR, lo=4.0, hi=8.0)
    assert offset is not None
    assert 5.9 < offset < 6.1


def test_quietest_offset_on_an_empty_window() -> None:
    assert quietest_offset(np.ones(SR, dtype=np.float32), SR, lo=2.0, hi=1.0) is None


def test_shape_turns_drops_scraps_and_bounds_length() -> None:
    samples = np.ones(int(120 * SR), dtype=np.float32) * 0.2
    turns = [
        Turn(0.0, 0.1, "SPEAKER_00"),  # scrap, dropped
        Turn(1.0, 3.0, "SPEAKER_01"),
        Turn(3.2, 100.0, "SPEAKER_01"),  # merged then split
    ]
    shaped = shape_turns(turns, samples, SR)

    assert all(t.duration >= 0.3 for t in shaped)
    assert all(t.duration <= MAX_TURN_SECONDS + 1e-6 for t in shaped)
    assert {t.speaker for t in shaped} == {"SPEAKER_01"}
    assert shaped[0].start == 1.0
    assert shaped[-1].end == 100.0


def test_shape_turns_without_audio_still_works() -> None:
    """Diarization can run before we have an energy envelope; don't crash."""
    shaped = shape_turns([Turn(0.0, 70.0, "SPEAKER_00")], None, SR)
    assert len(shaped) == 3
    assert all(t.duration <= MAX_TURN_SECONDS + 1e-6 for t in shaped)
