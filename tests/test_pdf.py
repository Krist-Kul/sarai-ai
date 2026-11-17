"""The PDF twin of the .docx."""

from __future__ import annotations

from pathlib import Path

from sarai.docgen.pdf import render_pdf, to_html
from sarai.models import ActionItem, MeetingType, MinutesJSON


def _minutes(**extra: object) -> MinutesJSON:
    return MinutesJSON.model_validate(
        {
            "title": "ประชุมทีม",
            "meeting_date": "2026-11-18 14:30",
            "summary": "สรุปการประชุม",
            "action_items": [
                ActionItem(task="ส่งเอกสาร", owner="คุณมาลี", source_quote="จะส่งให้").model_dump()
            ],
            **extra,
        }
    )


def test_model_output_is_escaped() -> None:
    html = to_html(
        _minutes(summary="<script>alert(1)</script>"), model="m", meeting_type=MeetingType.GENERAL
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_headings_follow_the_meeting_type() -> None:
    html = to_html(_minutes(), model="m", meeting_type=MeetingType.LECTURE)
    assert "สาระสำคัญ / Key takeaways" in html


def test_render_writes_a_pdf(tmp_path: Path) -> None:
    dest = render_pdf(_minutes(), tmp_path / "out.pdf", model="m")
    assert dest.read_bytes()[:5] == b"%PDF-"
