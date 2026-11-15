/**
 * Meeting type -> UI labels. Mirrors sarai/meeting_types.py, which owns the
 * prompt side and the .docx headings; keep the section labels in step with it.
 */
import type { MeetingType } from "../types";
import type { StringKey } from "./i18n";

export const MEETING_TYPES: { value: MeetingType; key: StringKey }[] = [
  { value: "general", key: "typeGeneral" },
  { value: "executive", key: "typeExecutive" },
  { value: "standup", key: "typeStandup" },
  { value: "lecture", key: "typeLecture" },
  { value: "interview", key: "typeInterview" },
  { value: "workshop", key: "typeWorkshop" },
];

const SUMMARY_LABEL: Record<MeetingType, StringKey> = {
  general: "sectionSummary",
  executive: "sectionSummaryExecutive",
  standup: "sectionSummaryStandup",
  lecture: "sectionSummaryLecture",
  interview: "sectionSummaryInterview",
  workshop: "sectionSummaryWorkshop",
};

const DISCUSSION_LABEL: Record<MeetingType, StringKey> = {
  general: "sectionDiscussion",
  executive: "sectionDiscussion",
  standup: "sectionDiscussionStandup",
  lecture: "sectionDiscussionLecture",
  interview: "sectionDiscussionInterview",
  workshop: "sectionDiscussionWorkshop",
};

export function sectionLabels(type: MeetingType | undefined): {
  summary: StringKey;
  discussion: StringKey;
} {
  const t = type ?? "general";
  return { summary: SUMMARY_LABEL[t], discussion: DISCUSSION_LABEL[t] };
}
