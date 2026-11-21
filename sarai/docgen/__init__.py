"""MinutesJSON -> .docx.

Two rules run through everything below.

*Every* piece of text goes through `styled_run`. python-docx sets `w:ascii` and
`w:hAnsi` when you assign `run.font.name`, and stops there -- Thai is a complex
script, so without `w:cs` Word picks its own substitute font, and without
`w:szCs` it renders at the wrong point size. Missing either is invisible on a
developer machine with Sarabun installed and obvious to everyone else.

The document has two parts: the minutes as written (Thai), then the same
minutes translated into English (`MinutesJSON.english`), each with its own
headings. Within a part, the section order is the one Thai minutes are read
in: attendees, summary,
agenda, discussion, decisions, action items, open questions. Action items are
the section people actually act on, so they get a table. The summary and
discussion headings follow the meeting type (sarai/meeting_types.py).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from docx import Document as new_document
from docx.document import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from sarai.docgen import labels as L
from sarai.docgen.fonts import FONT_NAME, embed_fonts
from sarai.docgen.labels import Lang
from sarai.meeting_types import profile
from sarai.models import MeetingType, MinutesContent, MinutesJSON

log = logging.getLogger("sarai.docgen")

BODY_PT = 12
H1_PT = 18
H2_PT = 14
SMALL_PT = 10


def styled_run(
    paragraph: Paragraph,
    text: str,
    *,
    size: int = BODY_PT,
    bold: bool = False,
    italic: bool = False,
    color: tuple[int, int, int] | None = None,
) -> Run:
    """The only way text enters the document. See the module docstring."""
    run = paragraph.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.name = FONT_NAME
    run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = RGBColor(*color)

    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:ascii"), FONT_NAME)
    rfonts.set(qn("w:hAnsi"), FONT_NAME)
    rfonts.set(qn("w:cs"), FONT_NAME)  # complex script -- required for Thai
    # w:sz is set by python-docx above; w:szCs is the complex-script twin and
    # is what actually sizes Thai glyphs. Half-points, hence the doubling.
    sz_cs = rpr.makeelement(qn("w:szCs"), {qn("w:val"): str(size * 2)})
    rpr.append(sz_cs)
    return run


def _heading(doc: Document, text: str, *, size: int = H2_PT, space_before: int = 14) -> Paragraph:
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(space_before)
    para.paragraph_format.space_after = Pt(4)
    styled_run(para, text, size=size, bold=True)
    return para


def _body(doc: Document, text: str, *, size: int = BODY_PT, italic: bool = False) -> Paragraph:
    para = doc.add_paragraph()
    # Thai tone marks collide with the line above at the default spacing.
    para.paragraph_format.line_spacing = 1.5
    para.paragraph_format.space_after = Pt(4)
    styled_run(para, text, size=size, italic=italic)
    return para


def _bullet(doc: Document, text: str, *, prefix: str = "•") -> Paragraph:
    para = doc.add_paragraph()
    para.paragraph_format.left_indent = Pt(18)
    para.paragraph_format.line_spacing = 1.5
    para.paragraph_format.space_after = Pt(2)
    styled_run(para, f"{prefix} {text}")
    return para


def _label(labels: tuple[str, str], lang: Lang) -> str:
    """A (thai, english) heading pair, in the language of the part."""
    return labels[0] if lang == "th" else labels[1]


def _attendee_table(doc: Document, content: MinutesContent, lang: Lang) -> None:
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    header = table.rows[0].cells
    for cell, label in zip(header, (_label(L.NAME, lang), _label(L.ROLE, lang)), strict=True):
        styled_run(cell.paragraphs[0], label, bold=True, size=SMALL_PT + 1)
    for attendee in content.attendees:
        row = table.add_row().cells
        styled_run(row[0].paragraphs[0], attendee.name)
        styled_run(row[1].paragraphs[0], attendee.role or "—")


def _action_table(doc: Document, content: MinutesContent, lang: Lang) -> None:
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    header = table.rows[0].cells
    for cell, label in zip(
        header, (_label(L.TASK, lang), _label(L.OWNER, lang), _label(L.DUE, lang)), strict=True
    ):
        styled_run(cell.paragraphs[0], label, bold=True, size=SMALL_PT + 1)

    for item in content.action_items:
        cells = table.add_row().cells
        styled_run(cells[0].paragraphs[0], item.task)
        styled_run(cells[1].paragraphs[0], item.owner or "—")
        styled_run(cells[2].paragraphs[0], item.due or "—")
        # The quote is the evidence the item is real; it belongs next to it.
        quote = cells[0].add_paragraph()
        styled_run(
            quote, f"“{item.source_quote}”", size=SMALL_PT, italic=True, color=(0x6F, 0x66, 0x59)
        )


def _part(doc: Document, content: MinutesContent, lang: Lang, meeting_type: MeetingType) -> None:
    """One language's full minutes. The part is not labelled: its headings
    already show which language it is."""
    labels = profile(meeting_type)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    styled_run(title, content.title, size=H1_PT, bold=True)

    meta = doc.add_paragraph()
    styled_run(meta, f"{_label(L.DATE, lang)}: {content.meeting_date or '—'}", size=SMALL_PT)

    notice = doc.add_paragraph()
    notice.paragraph_format.space_before = Pt(4)
    notice.paragraph_format.space_after = Pt(8)
    styled_run(
        notice, _label(L.AI_NOTICE, lang), size=SMALL_PT, italic=True, color=(0x9A, 0x34, 0x12)
    )

    if content.attendees:
        _heading(doc, _label(L.ATTENDEES, lang))
        _attendee_table(doc, content, lang)

    if content.summary:
        _heading(doc, _label(labels.summary_label, lang))
        _body(doc, content.summary)

    if content.agenda:
        _heading(doc, _label(L.AGENDA, lang))
        for index, item in enumerate(content.agenda, start=1):
            _bullet(doc, item, prefix=f"{index}.")

    if content.discussion:
        _heading(doc, _label(labels.discussion_label, lang))
        for topic in content.discussion:
            _heading(doc, topic.topic, size=BODY_PT + 1, space_before=8)
            for point in topic.points:
                _bullet(doc, point)

    if content.decisions:
        _heading(doc, _label(L.DECISIONS, lang))
        for index, decision in enumerate(content.decisions, start=1):
            _bullet(doc, decision.decision, prefix=f"{index}.")
            if decision.rationale:
                para = doc.add_paragraph()
                para.paragraph_format.left_indent = Pt(36)
                styled_run(para, decision.rationale, size=SMALL_PT, italic=True)

    if content.action_items:
        # The section people actually read; a long document should not make
        # them hunt for it across a page break.
        doc.add_page_break()  # type: ignore[no-untyped-call]
        _heading(doc, _label(L.ACTIONS, lang), size=H2_PT + 1)
        _action_table(doc, content, lang)

    if content.open_questions:
        _heading(doc, _label(L.OPEN_QUESTIONS, lang))
        for question in content.open_questions:
            _bullet(doc, question)

    if content.next_meeting:
        _heading(doc, _label(L.NEXT_MEETING, lang))
        _body(doc, content.next_meeting)


def render(
    minutes: MinutesJSON,
    dest: Path,
    *,
    model: str,
    meeting_type: MeetingType = MeetingType.GENERAL,
) -> Path:
    """Write the minutes to `dest`: the Thai part, then the English part on a
    new page when there is a translation. Returns the path written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = new_document()

    _part(doc, minutes, "th", meeting_type)
    if minutes.english is not None:
        doc.add_page_break()  # type: ignore[no-untyped-call]
        _part(doc, minutes.english, "en", meeting_type)

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    footer = doc.add_paragraph()
    footer.paragraph_format.space_before = Pt(24)
    styled_run(
        footer,
        f"Generated by Sarai AI · {model} · {generated}",
        size=SMALL_PT,
        color=(0x9C, 0x91, 0x84),
    )

    embed_fonts(doc)
    doc.save(str(dest))
    log.info("rendered minutes to %s", dest)
    return dest


def render_documents(
    minutes: MinutesJSON,
    docx_dest: Path,
    pdf_dest: Path,
    *,
    model: str,
    meeting_type: MeetingType = MeetingType.GENERAL,
) -> tuple[Path, Path | None]:
    """The .docx, then the PDF. Returns (docx path, pdf path or None).

    A PDF failure -- most likely Pango missing on the host -- is logged and
    leaves the .docx in place: the editable document is the one that matters,
    and losing it over the PDF would throw away a finished LLM call.
    """
    from sarai.docgen.pdf import render_pdf

    docx = render(minutes, docx_dest, model=model, meeting_type=meeting_type)
    try:
        pdf: Path | None = render_pdf(minutes, pdf_dest, model=model, meeting_type=meeting_type)
    except Exception:
        log.exception("PDF rendering failed; the .docx was still written")
        pdf_dest.unlink(missing_ok=True)
        pdf = None
    return docx, pdf
