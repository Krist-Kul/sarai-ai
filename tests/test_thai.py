"""Thai normalization and truncation."""

from __future__ import annotations

from sarai import thai


def test_normalizes_spelled_out_and_spaced_mai_yamok() -> None:
    assert thai.normalize("เร็ว ๆ นี้") == "เร็วๆ นี้"
    assert thai.normalize("ต่างไม้ยมก") == "ต่างๆ"


def test_collapses_a_repeated_short_thai_word() -> None:
    assert thai.normalize("ครับ ครับ") == "ครับๆ"


def test_leaves_a_repeated_long_phrase_alone() -> None:
    # Two long identical words are far more likely to be genuinely repeated.
    text = "ขอบคุณมากครับ ขอบคุณมากครับ"
    assert thai.normalize(text) == text


def test_buddhist_era_years_convert_and_ce_years_do_not() -> None:
    assert thai.be_to_ce(2569) == 2026
    assert thai.be_to_ce(2026) == 2026
    assert thai.convert_be_years("ประชุมปี 2569 ต่อจากปี 2568") == "ประชุมปี 2026 ต่อจากปี 2025"
    assert thai.convert_be_years("รุ่น 2024") == "รุ่น 2024"


def test_truncate_never_splits_on_spaces() -> None:
    """Thai has no word spaces; a space-based truncator would return the whole
    string untouched and blow the budget it was given."""
    text = "ผมขอเริ่มที่เรื่องการปล่อยระบบใหม่ก่อนนะครับตอนนี้ยังไม่ผ่านการทดสอบ"
    out = thai.truncate(text, 20)
    assert len(out) <= 20
    assert out != text
    assert out.endswith("…")


def test_truncate_returns_short_text_unchanged() -> None:
    assert thai.truncate("สั้น", 50) == "สั้น"


def test_normalize_is_idempotent() -> None:
    once = thai.normalize("เร็ว ๆ ครับ ครับ")
    assert thai.normalize(once) == once
