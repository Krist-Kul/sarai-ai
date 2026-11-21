"""MinutesJSON -> .pdf, the read-only twin of the .docx.

The .docx stays the editable document; the PDF is what gets sent around. It
is rendered from the same MinutesJSON with the same parts (Thai, then
English), section order and headings as `sarai.docgen.render`, through HTML
and WeasyPrint rather than by converting the .docx: that would need
LibreOffice on every host, and WeasyPrint shapes
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

from sarai.docgen import labels as L
from sarai.docgen.fonts import FONT_NAME, FONTS_DIR
from sarai.docgen.labels import Lang
from sarai.meeting_types import profile
from sarai.models import MeetingType, MinutesContent, MinutesJSON
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
.meta, .rationale, .footer { font-size: 10pt; color: #6f6659; }
.rationale, .quote { font-style: italic; }
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
.part + .part { page-break-before: always; }
.footer { margin-top: 24pt; color: #9c9184; }
.ai-notice { font-size: 10pt; color: #9a3412; background: #fff7ed;
             border-left: 3pt solid #ea580c; padding: 4pt 8pt; margin: 6pt 0 10pt 0; }
"""


def _label(labels: tuple[str, str], lang: Lang) -> str:
    return escape(labels[0] if lang == "th" else labels[1])


def _part(content: MinutesContent, lang: Lang, meeting_type: MeetingType) -> list[str]:
    """One language's full minutes, unlabelled: its headings show the
    language. Every value is escaped: the minutes are model output built from what people said."""
    labels = profile(meeting_type)
    e = escape

    def c(text: str) -> str:
        """Escape a table cell, with break points between Thai words."""
        return escape(soft_wrap(text))

    out: list[str] = [
        f"<section class='part' lang='{lang}'>",
        f"<h1>{e(content.title)}</h1>",
        f"<p class='meta'>{_label(L.DATE, lang)}: {e(content.meeting_date or '—')}</p>",
        f"<p class='ai-notice'>{_label(L.AI_NOTICE, lang)}</p>",
    ]

    if content.attendees:
        out.append(
            f"<h2>{_label(L.ATTENDEES, lang)}</h2><table>"
            "<col style='width:40%'><col style='width:60%'>"
            f"<tr><th>{_label(L.NAME, lang)}</th><th>{_label(L.ROLE, lang)}</th></tr>"
        )
        for a in content.attendees:
            out.append(f"<tr><td>{c(a.name)}</td><td>{c(a.role or '—')}</td></tr>")
        out.append("</table>")

    if content.summary:
        out.append(f"<h2>{_label(labels.summary_label, lang)}</h2><p>{e(content.summary)}</p>")

    if content.agenda:
        out.append(f"<h2>{_label(L.AGENDA, lang)}</h2><ol>")
        out.extend(f"<li>{e(item)}</li>" for item in content.agenda)
        out.append("</ol>")

    if content.discussion:
        out.append(f"<h2>{_label(labels.discussion_label, lang)}</h2>")
        for topic in content.discussion:
            out.append(f"<h3>{e(topic.topic)}</h3>")
            if topic.points:
                out.append("<ul>")
                out.extend(f"<li>{e(p)}</li>" for p in topic.points)
                out.append("</ul>")

    if content.decisions:
        out.append(f"<h2>{_label(L.DECISIONS, lang)}</h2><ol>")
        for d in content.decisions:
            rationale = f"<div class='rationale'>{e(d.rationale)}</div>" if d.rationale else ""
            out.append(f"<li>{e(d.decision)}{rationale}</li>")
        out.append("</ol>")

    if content.action_items:
        out.append(
            f"<h2 class='actions'>{_label(L.ACTIONS, lang)}</h2>"
            "<table><col style='width:62%'><col style='width:20%'><col style='width:18%'><tr>"
            f"<th>{_label(L.TASK, lang)}</th>"
            f"<th>{_label(L.OWNER, lang)}</th>"
            f"<th>{_label(L.DUE, lang)}</th></tr>"
        )
        for item in content.action_items:
            out.append(
                f"<tr><td>{c(item.task)}<span class='quote'>“{c(item.source_quote)}”</span></td>"
                f"<td>{c(item.owner or '—')}</td><td>{c(item.due or '—')}</td></tr>"
            )
        out.append("</table>")

    if content.open_questions:
        out.append(f"<h2>{_label(L.OPEN_QUESTIONS, lang)}</h2><ul>")
        out.extend(f"<li>{e(q)}</li>" for q in content.open_questions)
        out.append("</ul>")

    if content.next_meeting:
        out.append(f"<h2>{_label(L.NEXT_MEETING, lang)}</h2><p>{e(content.next_meeting)}</p>")

    out.append("</section>")
    return out


def to_html(minutes: MinutesJSON, *, model: str, meeting_type: MeetingType) -> str:
    """The whole document as one HTML string: the Thai part, then the English
    part on a new page when there is a translation."""
    out: list[str] = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<style>{_font_faces()}\n{_CSS % {'font': FONT_NAME}}</style></head><body>",
    ]
    out.extend(_part(minutes, "th", meeting_type))
    if minutes.english is not None:
        out.extend(_part(minutes.english, "en", meeting_type))

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out.append(f"<p class='footer'>Generated by Sarai AI · {escape(model)} · {generated}</p>")
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
