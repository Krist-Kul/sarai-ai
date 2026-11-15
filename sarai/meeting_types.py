"""What changes when the meeting is not an executive meeting.

The MinutesJSON schema stays the same for every meeting type -- one contract
for the API, the editor and the .docx. What a type changes is *emphasis*: who
the model writes as, what the summary is for, which sections usually carry the
weight and which are normally empty. Empty sections are already skipped by the
renderer and the editor, so a lecture with no decisions simply has none.

The evidence rules in the system prompt (never invent, verbatim source quotes,
conservative decisions) are not per-type and are never relaxed here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sarai.models import MeetingType


@dataclass(frozen=True)
class Profile:
    # Who the model writes as -- the first line of the system prompt.
    persona: str
    # What the `summary` field is for; replaces "executive overview".
    summary_guidance: str
    # Type-specific emphasis, appended to the system prompt as extra rules.
    focus: str
    # Section heading for the summary, (thai, english).
    summary_label: tuple[str, str]
    # Section heading for discussion, (thai, english).
    discussion_label: tuple[str, str]


PROFILES: dict[MeetingType, Profile] = {
    MeetingType.GENERAL: Profile(
        persona=(
            "You are an experienced Thai note-taker writing clear, accurate meeting "
            "notes (บันทึกการประชุม) for people who were not in the room."
        ),
        summary_guidance="3-5 sentences: what the meeting was about and what came out of it",
        focus=(
            "Adapt to whatever kind of meeting this is. Fill the sections the "
            "conversation actually supports and leave the rest empty."
        ),
        summary_label=("สรุปการประชุม", "Summary"),
        discussion_label=("รายละเอียดการประชุม", "Discussion"),
    ),
    MeetingType.EXECUTIVE: Profile(
        persona=(
            "You are an experienced Thai corporate secretary writing formal meeting "
            "minutes (รายงานการประชุม)."
        ),
        summary_guidance="3-5 sentences, executive overview",
        focus=(
            "This is an executive or management meeting. Decisions (มติที่ประชุม), "
            "owners and deadlines matter most. Write in a formal register."
        ),
        summary_label=("สรุปผู้บริหาร", "Executive summary"),
        discussion_label=("รายละเอียดการประชุม", "Discussion"),
    ),
    MeetingType.STANDUP: Profile(
        persona=(
            "You are a Thai engineering team lead writing short notes from a team "
            "stand-up or status sync."
        ),
        summary_guidance="2-3 sentences: overall progress and the most important blocker",
        focus=(
            "Use one discussion topic per person or workstream; its points are what "
            "was done, what is next, and any blocker. Put unresolved blockers in "
            "open_questions. Agenda is usually empty. Keep wording short."
        ),
        summary_label=("ภาพรวม", "Overview"),
        discussion_label=("ความคืบหน้ารายบุคคล", "Updates"),
    ),
    MeetingType.LECTURE: Profile(
        persona=(
            "You are a careful Thai student writing study notes from a lecture, "
            "seminar or presentation."
        ),
        summary_guidance="3-5 sentences: the main argument or lesson of the session",
        focus=(
            "Use agenda for the outline of the talk and one discussion topic per "
            "concept, with its key points, definitions, figures and examples. Put "
            "audience questions that were not answered in open_questions. Decisions "
            "and action items are usually empty; only include assignments or "
            "follow-ups the speaker explicitly gave."
        ),
        summary_label=("สาระสำคัญ", "Key takeaways"),
        discussion_label=("เนื้อหา", "Content"),
    ),
    MeetingType.INTERVIEW: Profile(
        persona=(
            "You are a Thai researcher or recruiter writing a neutral record of an interview."
        ),
        summary_guidance="3-5 sentences: who was interviewed, about what, and the main findings",
        focus=(
            "Use one discussion topic per question or theme; its points are what the "
            "interviewee said, as close to their words as possible. Do not evaluate "
            "or score the interviewee. Decisions are usually empty; action items "
            "only for explicit follow-ups."
        ),
        summary_label=("สรุปการสัมภาษณ์", "Interview summary"),
        discussion_label=("คำถามและคำตอบ", "Questions and answers"),
    ),
    MeetingType.WORKSHOP: Profile(
        persona=(
            "You are a Thai facilitator writing up the output of a workshop or "
            "brainstorming session."
        ),
        summary_guidance="3-5 sentences: the goal of the session and what it produced",
        focus=(
            "Use one discussion topic per theme or exercise and capture every "
            "distinct idea raised, not only the popular ones. Decisions are only "
            "ideas the group explicitly chose to pursue."
        ),
        summary_label=("สรุปผลเวิร์กช็อป", "Workshop summary"),
        discussion_label=("แนวคิดที่ได้", "Ideas"),
    ),
}


def profile(meeting_type: MeetingType) -> Profile:
    return PROFILES[meeting_type]
