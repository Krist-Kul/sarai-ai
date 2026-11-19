"""MinutesJSON -> .pdf, the read-only twin of the .docx.

The .docx stays the editable document; the PDF is what gets sent around. It
is rendered from the same MinutesJSON with the same section order and headings
as `sarai.docgen.render`, through HTML and WeasyPrint rather than by converting
the .docx: that would need LibreOffice on every host, and WeasyPrint shapes
Thai through Pango and HarfBuzz, which handles stacked vowels and tone marks
and breaks lines between Thai words (via libthai).

Sarabun is loaded from the same font files the .docx embeds. Without them the
PDF falls back to whatever Thai font the host has.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from sarai.docgen.fonts import FONT_NAME, FONTS_DIR
from sarai.meeting_types import profile
from sarai.models import MeetingType, MinutesJSON
from sarai.thai import soft_wrap

log = logging.getLogger("sarai.docgen")


def _font_faces() -> str:
    faces = []
    for weight, filename in ((400, "Sarabun-Regular.ttf"), (700, "Sarabun-Bold.ttf")):
        path = FONTS_DIR / filename
        if path.is_file():
            faces.append(
                f"@font-face {{ font-family: '{FONT_NAME}'; font-weight: {weight}; "
                f"src: url('{path.resolve().as_uri()}'); }}"
            )
    return "\n".join(faces)


_CSS = """
@page { size: A4; margin: 20mm 18mm 18mm 18mm;
        @bottom-right { content: counter(page) " / " counter(pages);
                        font-size: 9pt; color: #9c9184; } }
body { font-family: '%(font)s', 'Noto Sans Thai', 'Tahoma', sans-serif;
       font-size: 12pt; line-height: 1.5; color: #1f1b16; }
h1 { font-size: 18pt; margin: 0 0 4pt 0; }
h2 { font-size: 14pt; margin: 14pt 0 4pt 0; }
h3 { font-size: 13pt; margin: 8pt 0 2pt 0; }
.meta, .speakers, .rationale, .footer { font-size: 10pt; color: #6f6659; }
.speakers, .rationale, .quote { font-style: italic; }
ul, ol { margin: 0 0 4pt 0; padding-left: 18pt; }
li { margin-bottom: 2pt; }
/* Fixed layout: column widths come from <col>, never from the longest
   unbreakable run of text, so a table cannot grow past the page. */
table { width: 100%%; border-collapse: collapse; margin-top: 4pt;
        table-layout: fixed; }
th, td { border: 0.6pt solid #b8ad9f; padding: 4pt 6pt; vertical-align: top;
         text-align: left; overflow-wrap: anywhere; }
th { font-size: 11pt; background: #f4efe7; }
.quote { display: block; font-size: 10pt; color: #6f6659; margin-top: 2pt; }
.actions { page-break-before: always; }
.footer { margin-top: 24pt; color: #9c9184; }
"""


def _bilingual(thai_label: str, english_label: str) -> str:
    return escape(f"{thai_label} / {english_label}")


def to_html(minutes: MinutesJSON, *, model: str, meeting_type: MeetingType) -> str:
    """The whole document as one HTML string. Every value is escaped: the
    minutes are model output built from what people said in the room."""
    labels = profile(meeting_type)
    e = escape

    def c(text: str) -> str:
        """Escape a table cell, with break points between Thai words."""
        return escape(soft_wrap(text))

    out: list[str] = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<style>{_font_faces()}\n{_CSS % {'font': FONT_NAME}}</style></head><body>",
        f"<h1>{e(minutes.title)}</h1>",
        f"<p class='meta'>{_bilingual('วันที่ประชุม', 'Date')}: {e(minutes.meeting_date or '—')}</p>",
    ]

    if minutes.attendees:
        out.append(
            f"<h2>{_bilingual('ผู้เข้าร่วมประชุม', 'Attendees')}</h2><table>"
            "<col style='width:40%'><col style='width:60%'>"
        )
        for a in minutes.attendees:
            out.append(f"<tr><td>{c(a.name)}</td><td>{c(a.role or '—')}</td></tr>")
        out.append("</table>")

    if minutes.summary:
        out.append(f"<h2>{_bilingual(*labels.summary_label)}</h2><p>{e(minutes.summary)}</p>")

    if minutes.agenda:
        out.append(f"<h2>{_bilingual('วาระการประชุม', 'Agenda')}</h2><ol>")
        out.extend(f"<li>{e(item)}</li>" for item in minutes.agenda)
        out.append("</ol>")

    if minutes.discussion:
        out.append(f"<h2>{_bilingual(*labels.discussion_label)}</h2>")
        for topic in minutes.discussion:
            out.append(f"<h3>{e(topic.topic)}</h3>")
            if topic.speakers:
                out.append(f"<p class='speakers'>{e(', '.join(topic.speakers))}</p>")
            if topic.points:
                out.append("<ul>")
                out.extend(f"<li>{e(p)}</li>" for p in topic.points)
                out.append("</ul>")

    if minutes.decisions:
        out.append(f"<h2>{_bilingual('มติที่ประชุม', 'Decisions')}</h2><ol>")
        for d in minutes.decisions:
            rationale = f"<div class='rationale'>{e(d.rationale)}</div>" if d.rationale else ""
            out.append(f"<li>{e(d.decision)}{rationale}</li>")
        out.append("</ol>")

    if minutes.action_items:
        out.append(
            f"<h2 class='actions'>{_bilingual('สิ่งที่ต้องดำเนินการ', 'Action items')}</h2>"
            "<table><col style='width:62%'><col style='width:20%'><col style='width:18%'><tr>"
            f"<th>{_bilingual('สิ่งที่ต้องทำ', 'Task')}</th>"
            f"<th>{_bilingual('ผู้รับผิดชอบ', 'Owner')}</th>"
            f"<th>{_bilingual('กำหนดส่ง', 'Due')}</th></tr>"
        )
        for item in minutes.action_items:
            out.append(
                f"<tr><td>{c(item.task)}<span class='quote'>“{c(item.source_quote)}”</span></td>"
                f"<td>{c(item.owner or '—')}</td><td>{c(item.due or '—')}</td></tr>"
            )
        out.append("</table>")

    if minutes.open_questions:
        out.append(f"<h2>{_bilingual('ประเด็นค้าง', 'Open questions')}</h2><ul>")
        out.extend(f"<li>{e(q)}</li>" for q in minutes.open_questions)
        out.append("</ul>")

    if minutes.next_meeting:
        out.append(
            f"<h2>{_bilingual('การประชุมครั้งต่อไป', 'Next meeting')}</h2>"
            f"<p>{e(minutes.next_meeting)}</p>"
        )

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out.append(f"<p class='footer'>Generated by Sarai AI · {e(model)} · {generated}</p>")
    out.append("</body></html>")
    return "\n".join(out)


def render_pdf(
    minutes: MinutesJSON,
    dest: Path,
    *,
    model: str,
    meeting_type: MeetingType = MeetingType.GENERAL,
) -> Path:
    """Write the minutes to `dest` as PDF. Returns the path written."""
    # Imported here: WeasyPrint loads Pango through cffi at import time, and
    # nothing but this function needs it.
    from weasyprint import HTML

    dest.parent.mkdir(parents=True, exist_ok=True)
    html = to_html(minutes, model=model, meeting_type=meeting_type)
    # base_url=None plus file:// font URLs: the document can reach the font
    # files and nothing else.
    HTML(string=html).write_pdf(str(dest))
    log.info("rendered minutes to %s", dest)
    return dest
