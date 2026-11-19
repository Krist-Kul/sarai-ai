/**
 * Bilingual UI. Thai is the default -- the users are Thai, English is the
 * fallback for the occasional expat in the room.
 */
import { createContext, useContext } from "react";

export type Lang = "th" | "en";

const STORAGE_KEY = "sarai.lang";

export function loadLang(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "en" || stored === "th" ? stored : "th";
}

export function saveLang(lang: Lang): void {
  localStorage.setItem(STORAGE_KEY, lang);
}

type Entry = { th: string; en: string };

export const strings = {
  appName: { th: "Sarai AI", en: "Sarai AI" },
  tagline: {
    th: "เปลี่ยนเสียงประชุมเป็นรายงานการประชุม",
    en: "Meeting audio into meeting minutes",
  },
  meetings: { th: "การประชุม", en: "Meetings" },
  newMeeting: { th: "อัปโหลดการประชุม", en: "Upload meeting" },
  emptyTitle: { th: "ยังไม่มีการประชุม", en: "No meetings yet" },
  emptyBody: {
    th: "อัปโหลดไฟล์เสียงการประชุมเพื่อเริ่มถอดเสียงและสรุปรายงาน — ทั้งหมดประมวลผลบนเครื่องของคุณเอง",
    en: "Upload a recording to transcribe it and draft the minutes — all of it processed on your own machine.",
  },
  meetingsSubtitle: {
    th: "ไฟล์เสียงทั้งหมดถูกประมวลผลบนเครื่องนี้ — ไม่มีอะไรออกนอกองค์กร",
    en: "Every recording is processed on this machine — nothing leaves the organization.",
  },
  statReview: { th: "รอตรวจทาน", en: "Awaiting review" },
  statProcessing: { th: "กำลังประมวลผล", en: "Processing" },
  statDoneMonth: { th: "เสร็จสิ้นเดือนนี้", en: "Finished this month" },
  statHours: { th: "ชั่วโมงที่ถอดเสียง", en: "Hours transcribed" },
  filterReview: { th: "รอตรวจทาน", en: "To review" },
  filterProcessing: { th: "กำลังประมวลผล", en: "Processing" },
  filterFinished: { th: "เสร็จสิ้น", en: "Done" },
  filterFailed: { th: "ล้มเหลว", en: "Failed" },
  sortBy: { th: "เรียงตาม", en: "Sort by" },
  sortNewest: { th: "ล่าสุดก่อน", en: "Newest first" },
  sortOldest: { th: "เก่าสุดก่อน", en: "Oldest first" },
  stepUploadTitle: { th: "อัปโหลดไฟล์", en: "Upload a file" },
  stepUploadBody: { th: "รองรับเสียงและวิดีโอทั่วไป ไม่เกิน 500 MB", en: "Common audio and video, up to 500 MB" },
  stepTranscribeTitle: { th: "ถอดเสียงอัตโนมัติ", en: "Automatic transcription" },
  stepTranscribeBody: {
    th: "แยกผู้พูดและถอดเสียงทีละช่วง บน GPU ของคุณ",
    en: "Speakers separated and transcribed turn by turn, on your GPU",
  },
  stepReviewTitle: { th: "ตรวจทานข้อความ", en: "Review the text" },
  stepReviewBody: { th: "ตั้งชื่อผู้พูดครั้งเดียว แก้คำผิดได้ทันที", en: "Name speakers once, fix typos in place" },
  stepMinutesTitle: { th: "รับรายงาน", en: "Get the minutes" },
  stepMinutesBody: {
    th: "สรุป มติ และสิ่งที่ต้องทำ เป็น PDF และ .docx",
    en: "Summary, resolutions and action items as PDF and .docx",
  },
  uploadCta: { th: "อัปโหลดไฟล์เสียง", en: "Upload audio" },
  title: { th: "หัวข้อการประชุม", en: "Meeting title" },
  date: { th: "วันที่ประชุม", en: "Meeting date" },
  language: { th: "ภาษา", en: "Language" },
  langAuto: { th: "อัตโนมัติ", en: "Auto" },
  meetingType: { th: "ประเภทการประชุม", en: "Meeting type" },
  autoSummarize: {
    th: "สร้างรายงานการประชุมทันทีหลังถอดเสียงเสร็จ",
    en: "Generate minutes as soon as transcription finishes",
  },
  autoSummarizeHelp: {
    th: "ปิดไว้ถ้าต้องการตรวจทานบทถอดเสียงและชื่อผู้พูดก่อน",
    en: "Turn off to review the transcript and speaker names first",
  },
  meetingTypeHelp: {
    th: "กำหนดรูปแบบของสรุปและหัวข้อในเอกสาร",
    en: "Shapes the summary and the document's sections",
  },
  typeAuto: { th: "ตรวจจับอัตโนมัติ", en: "Detect automatically" },
  typeGeneral: { th: "ทั่วไป", en: "General" },
  typeExecutive: { th: "ผู้บริหาร", en: "Executive" },
  typeStandup: { th: "อัปเดตงานทีม", en: "Stand-up" },
  typeLecture: { th: "บรรยาย / สัมมนา", en: "Lecture / seminar" },
  typeInterview: { th: "สัมภาษณ์", en: "Interview" },
  typeWorkshop: { th: "เวิร์กช็อป / ระดมความคิด", en: "Workshop / brainstorm" },
  langTh: { th: "ไทย", en: "Thai" },
  langEn: { th: "อังกฤษ", en: "English" },
  attendees: { th: "ผู้เข้าร่วมประชุม", en: "Attendees" },
  attendeeName: { th: "ชื่อ", en: "Name" },
  attendeeRole: { th: "ตำแหน่ง", en: "Role" },
  addAttendee: { th: "เพิ่มผู้เข้าร่วม", en: "Add attendee" },
  glossary: { th: "คำศัพท์เฉพาะ", en: "Glossary" },
  glossaryHelp: {
    th: "ใส่ชื่อโครงการ ชื่อคน ตัวย่อ หรือศัพท์เทคนิคที่ใช้ในที่ประชุม การใส่คำเหล่านี้ช่วยให้ระบบถอดชื่อและศัพท์เฉพาะได้ถูกต้องขึ้นอย่างชัดเจน",
    en: "Add project names, people, acronyms and technical terms used in the meeting. This measurably improves how accurately names and jargon are transcribed.",
  },
  glossaryPlaceholder: { th: "พิมพ์แล้วกด Enter", en: "Type and press Enter" },
  dropzone: { th: "ลากไฟล์มาวาง หรือคลิกเพื่อเลือก", en: "Drag a file here, or click to browse" },
  dropzoneHint: {
    th: "รองรับไฟล์เสียงและวิดีโอทั่วไป (mp3, m4a, wav, mp4, mov, webm ฯลฯ) — ไม่เกิน 500 MB",
    en: "Common audio and video files (mp3, m4a, wav, mp4, mov, webm…) — up to 500 MB",
  },
  privacyNote: {
    th: "ไฟล์เสียงถูกประมวลผลบนเครื่องของคุณเท่านั้น ไม่ถูกส่งออกไปยังบริการภายนอก",
    en: "Audio is processed on your own machine. It is never sent to a third-party service.",
  },
  submit: { th: "เริ่มถอดเสียง", en: "Start transcription" },
  submitting: { th: "กำลังอัปโหลด…", en: "Uploading…" },
  cancel: { th: "ยกเลิก", en: "Cancel" },
  delete: { th: "ลบ", en: "Delete" },
  deleteConfirm: {
    th: "ลบการประชุมนี้และไฟล์ทั้งหมดถาวรหรือไม่",
    en: "Permanently delete this meeting and all its files?",
  },
  duration: { th: "ความยาว", en: "Duration" },
  status: { th: "สถานะ", en: "Status" },
  created: { th: "อัปโหลดเมื่อ", en: "Uploaded" },
  open: { th: "เปิด", en: "Open" },
  back: { th: "ย้อนกลับ", en: "Back" },
  workerDown: {
    th: "ไม่พบ worker ที่ทำงานอยู่ — งานจะค้างอยู่ในคิวจนกว่าจะเริ่ม worker",
    en: "No worker is running. Jobs will sit in the queue until one starts.",
  },
  errorTitle: { th: "เกิดข้อผิดพลาด", en: "Something went wrong" },
  retry: { th: "ลองใหม่", en: "Retry" },
  loading: { th: "กำลังโหลด…", en: "Loading…" },
  progress: { th: "ความคืบหน้า", en: "Progress" },
  elapsed: { th: "เวลาที่ผ่านไป", en: "Elapsed" },
  liveLive: { th: "อัปเดตสด", en: "Live" },
  liveConnecting: { th: "กำลังเชื่อมต่อ…", en: "Connecting…" },
  liveLost: { th: "ขาดการเชื่อมต่อสด — สลับไปสำรวจสถานะแทน", en: "Live stream lost — polling instead" },
  queuedNote: {
    th: "อยู่ในคิว รอ worker ว่างเพื่อเริ่มประมวลผล",
    en: "In the queue, waiting for a free worker.",
  },
  retryingNote: {
    th: "การประมวลผลครั้งก่อนล้มเหลว ระบบจะลองใหม่อัตโนมัติ —",
    en: "The last attempt failed and will be retried automatically —",
  },
  readyNote: {
    th: "ถอดเสียงเสร็จแล้ว พร้อมให้ตรวจทาน",
    en: "Transcription finished and is ready for review.",
  },
  failedNote: {
    th: "งานนี้ล้มเหลว ระบบลองใหม่จนครบจำนวนครั้งที่กำหนดแล้ว",
    en: "This job failed after exhausting its retries.",
  },
  stageQueued: { th: "รอคิว", en: "Queued" },
  stageNormalizing: { th: "แปลงไฟล์เสียง", en: "Normalizing" },
  stageDiarizing: { th: "แยกผู้พูด", en: "Diarizing" },
  stageTranscribing: { th: "ถอดเสียง", en: "Transcribing" },
  stageAwaitingReview: { th: "พร้อมตรวจทาน", en: "Ready for review" },
  stageSummarizing: { th: "กำลังสรุป", en: "Summarizing" },
  stageRendering: { th: "สร้างเอกสาร", en: "Rendering" },
  stageDone: { th: "เสร็จสิ้น", en: "Done" },
  stageFailed: { th: "ล้มเหลว", en: "Failed" },

  meetingsSummary: {
    th: "{n} การประชุม · รอคุณ {k} รายการ",
    en: "{n} meetings · {k} need you",
  },
  searchMeetings: { th: "ค้นหาการประชุม", en: "Search meetings" },
  filterAll: { th: "ทั้งหมด", en: "All" },
  filterAttention: { th: "รอคุณ", en: "Needs you" },
  filterActive: { th: "กำลังทำงาน", en: "In progress" },
  filterDone: { th: "เสร็จแล้ว", en: "Finished" },
  noMatches: {
    th: "ไม่มีการประชุมที่ตรงกับที่ค้นหา",
    en: "No meetings match this filter.",
  },
  clearFilters: { th: "ล้างตัวกรอง", en: "Clear filters" },
  actionWatch: { th: "ดูความคืบหน้า", en: "Watch progress" },
  actionReview: { th: "ตรวจทานข้อความ", en: "Review transcript" },
  actionOpen: { th: "เปิดรายงาน", en: "Open minutes" },
  actionDetails: { th: "ดูรายละเอียด", en: "View details" },
  // Phone-width labels: the row keeps everything on one line, so the verb
  // alone has to carry it.
  actionWatchShort: { th: "ดู", en: "Watch" },
  actionReviewShort: { th: "ตรวจทาน", en: "Review" },
  actionOpenShort: { th: "เปิด", en: "Open" },
  actionDetailsShort: { th: "รายละเอียด", en: "Details" },
  speakersDetected: { th: "พบผู้พูด {n} คน", en: "{n} speakers detected" },

  uploadStep: { th: "ขั้นที่ 1 จาก 4 · อัปโหลด", en: "Step 1 of 4 · Upload" },
  dateTime: { th: "วันและเวลาประชุม", en: "Meeting date and time" },
  speakersOptional: { th: "ผู้พูด (ไม่บังคับ)", en: "Speakers (optional)" },
  speakersOptionalHelp: {
    th: "ใส่ชื่อถ้าทราบ ระบบจะจับคู่ชื่อกับเสียงเอง ถ้าไม่ใส่ ระบบจะหาชื่อจากบทสนทนา",
    en: "Add names if you know them and the system matches them to voices. Leave empty and it finds names in the conversation.",
  },
  autoNote: {
    th: "ระบบจะถอดเสียง ระบุผู้พูด เลือกประเภทการประชุม และสรุปเป็น PDF และ .docx ให้เอง ปิดแท็บได้เลย",
    en: "Transcription, speaker names, meeting type and the summary are all automatic, ending in a PDF and a .docx. You can close the tab.",
  },
  fileReady: { th: "พร้อมอัปโหลด", en: "ready to upload" },
  replaceFile: { th: "เปลี่ยนไฟล์", en: "Replace" },
  unsupportedFile: {
    th: "ไฟล์นี้ไม่รองรับ ใช้ไฟล์เสียง (.mp3 .m4a .wav .ogg .flac .aac .opus .wma .amr .aiff) หรือวิดีโอ (.mp4 .mov .mkv .webm .m4v .avi .3gp)",
    en: "Unsupported file. Use audio (.mp3 .m4a .wav .ogg .flac .aac .opus .wma .amr .aiff) or video (.mp4 .mov .mkv .webm .m4v .avi .3gp)",
  },
  meetingDetails: { th: "รายละเอียดการประชุม", en: "Meeting details" },
  helpTitle: { th: "ช่วยให้ถอดเสียงแม่นยำขึ้น", en: "Help the transcription" },
  helpSubtitle: {
    th: "ไม่บังคับ — แต่ชื่อคนและศัพท์เฉพาะจะออกมาถูกต้องขึ้นชัดเจน",
    en: "Optional — but names and jargon come out measurably better",
  },
  optional: { th: "ไม่บังคับ", en: "Optional" },
  speedNote: {
    th: "ถอดเสียงบนเครื่องนี้ ใช้เวลาราวหนึ่งในสิบของความยาวไฟล์",
    en: "Transcribing runs on this machine at roughly a tenth of the recording length.",
  },
  hide: { th: "ซ่อน", en: "Hide" },
  show: { th: "แสดง", en: "Show" },
  submitNote: {
    th: "ถอดเสียงบนเครื่องนี้ ใช้เวลาราวหนึ่งในสิบของความยาวไฟล์ ปิดแท็บได้เลย",
    en: "Transcribing runs on this machine at roughly a tenth of the recording length. You can close the tab.",
  },

  currentStep: { th: "ขั้นตอนตอนนี้", en: "Current step" },
  nextUp: { th: "ขั้นต่อไป", en: "Next up" },
  allMeetings: { th: "การประชุมทั้งหมด", en: "All meetings" },
  eta: { th: "คาดว่าเสร็จใน", en: "Estimated remaining" },
  latestTranscript: { th: "ถอดเสียงล่าสุด", en: "Latest transcript" },
  openTranscript: { th: "เปิดบทถอดเสียง", en: "Open transcript" },
  nextUpReview: {
    th: "เมื่อถอดเสียงเสร็จ คุณจะได้ตั้งชื่อผู้พูดและแก้ข้อความ ก่อนสร้างรายงาน ปิดแท็บนี้ได้เลย",
    en: "When transcription finishes you name the speakers and fix the text before the minutes are made. You can close this tab.",
  },
  nextUpAuto: {
    th: "เมื่อถอดเสียงเสร็จ ระบบจะตั้งชื่อผู้พูดและสรุปเป็น PDF และ .docx ให้เอง ปิดแท็บนี้ได้เลย",
    en: "When transcription finishes the speakers are named and the minutes written as a PDF and .docx. You can close this tab.",
  },
  nextUpMinutes: {
    th: "กำลังเขียนรายงาน เสร็จแล้วจะดาวน์โหลดเป็น PDF และ .docx ได้ที่นี่",
    en: "The minutes are being written. The PDF and .docx will be downloadable here.",
  },
  stopJob: { th: "หยุดงาน", en: "Stop job" },
  stopJobConfirm: { th: "ยืนยันหยุดงาน", en: "Confirm stop" },
  stopJobCancel: { th: "ไม่หยุด", en: "Keep running" },
  stoppingJob: { th: "กำลังหยุด…", en: "Stopping…" },
  cancelledNote: {
    th: "งานนี้ถูกหยุดโดยผู้ใช้",
    en: "This job was stopped by a user.",
  },
  listen: { th: "ฟังไฟล์เสียง", en: "Listen to the recording" },
  reviewReady: {
    th: "ถอดเสียงเสร็จแล้ว ตั้งชื่อผู้พูดและแก้ข้อความให้ถูกต้อง แล้วจึงสร้างรายงาน",
    en: "Transcription is done. Name the speakers and fix the text, then generate the minutes.",
  },

  // --- review screen ---
  reviewTitle: { th: "ตรวจทานข้อความ", en: "Review transcript" },
  speakers: { th: "ผู้พูด", en: "Speakers" },
  segmentCount: { th: "{n} ช่วงการพูด", en: "{n} segments" },
  searchTranscript: { th: "ค้นหาในข้อความ", en: "Search the transcript" },
  filterUnnamed: { th: "ยังไม่ตั้งชื่อ", en: "Unnamed speakers" },
  filterLowConfidence: { th: "ความมั่นใจต่ำ", en: "Low confidence" },
  filterEdited: { th: "ที่แก้ไขแล้ว", en: "Edited by me" },
  followPlayback: { th: "เลื่อนตามเสียง", en: "Follow playback" },
  speakersHint: { th: "ตั้งชื่อครั้งเดียว ใช้ทั้งบทสนทนา", en: "Rename once — it applies everywhere." },
  nameThisSpeaker: { th: "ตั้งชื่อผู้พูดนี้…", en: "Name this speaker…" },
  reassignSpeaker: { th: "เปลี่ยนผู้พูด", en: "Reassign speaker" },
  lowConfidenceHint: {
    th: "ความมั่นใจ {n}% — ควรฟังซ้ำ",
    en: "{n}% confidence — worth listening again",
  },
  generateMinutes: { th: "สร้างรายงานการประชุม", en: "Generate minutes" },
  play: { th: "เล่น", en: "Play" },
  pause: { th: "หยุด", en: "Pause" },
  seek: { th: "เลื่อนตำแหน่งเสียง", en: "Seek" },
  spaceToPlay: { th: "กด Space เพื่อเล่น/หยุด", en: "Space plays and pauses" },
  saving: { th: "กำลังบันทึก…", en: "Saving…" },
  allSaved: { th: "บันทึกแล้วทั้งหมด", en: "All changes saved" },
  autosaved: { th: "บันทึกอัตโนมัติ", en: "Autosaved" },
  speakerCount: { th: "{n} ผู้พูด", en: "{n} speakers" },
  turnCount: { th: "{n} ช่วง", en: "{n} turns" },
  unsaved: { th: "ยังไม่ได้บันทึก", en: "Unsaved changes" },
  saveFailed: { th: "บันทึกไม่สำเร็จ", en: "Could not save" },

  // --- minutes screen ---
  minutes: { th: "รายงานการประชุม", en: "Minutes" },
  contents: { th: "สารบัญ", en: "Contents" },
  aiDraftNote: {
    th: "สร้างจากบทถอดเสียงที่ตรวจทานแล้ว · แก้ไขได้",
    en: "Drafted from the reviewed transcript · editable",
  },
  attendeeCount: { th: "{n} ผู้เข้าร่วม", en: "{n} attendees" },
  sectionSummary: { th: "สรุปการประชุม", en: "Summary" },
  sectionSummaryExecutive: { th: "สรุปผู้บริหาร", en: "Executive summary" },
  sectionSummaryStandup: { th: "ภาพรวม", en: "Overview" },
  sectionSummaryLecture: { th: "สาระสำคัญ", en: "Key takeaways" },
  sectionSummaryInterview: { th: "สรุปการสัมภาษณ์", en: "Interview summary" },
  sectionSummaryWorkshop: { th: "สรุปผลเวิร์กช็อป", en: "Workshop summary" },
  sectionAgenda: { th: "วาระการประชุม", en: "Agenda" },
  sectionDiscussion: { th: "รายละเอียดการประชุม", en: "Discussion" },
  sectionDiscussionStandup: { th: "ความคืบหน้ารายบุคคล", en: "Updates" },
  sectionDiscussionLecture: { th: "เนื้อหา", en: "Content" },
  sectionDiscussionInterview: { th: "คำถามและคำตอบ", en: "Questions and answers" },
  sectionDiscussionWorkshop: { th: "แนวคิดที่ได้", en: "Ideas" },
  sectionDecisions: { th: "มติที่ประชุม", en: "Decisions" },
  sectionActions: { th: "สิ่งที่ต้องดำเนินการ", en: "Action items" },
  sectionQuestions: { th: "ประเด็นค้าง", en: "Open questions" },
  sectionNextMeeting: { th: "การประชุมครั้งต่อไป", en: "Next meeting" },
  minutesEditableNote: {
    th: "แก้ไขได้ทุกส่วน ไฟล์ .docx จะถูกสร้างใหม่ทุกครั้งที่บันทึก",
    en: "Everything here is editable. The .docx is re-rendered on every save.",
  },
  task: { th: "สิ่งที่ต้องทำ", en: "Task" },
  owner: { th: "ผู้รับผิดชอบ", en: "Owner" },
  due: { th: "กำหนดส่ง", en: "Due" },
  rationale: { th: "เหตุผล", en: "Rationale" },
  addActionItem: { th: "เพิ่มรายการ", en: "Add action item" },
  regenerate: { th: "สร้างใหม่", en: "Regenerate" },
  regenerateQueued: {
    th: "ส่งคำขอสร้างรายงานใหม่แล้ว รายงานเดิมจะถูกแทนที่เมื่อเสร็จ",
    en: "Regeneration queued. The current minutes are replaced when it finishes.",
  },
  downloadDocx: { th: "ดาวน์โหลด .docx", en: "Download .docx" },
  downloadPdf: { th: "ดาวน์โหลด PDF", en: "Download PDF" },
  noMinutesTitle: { th: "ยังไม่มีรายงานการประชุม", en: "No minutes yet" },
  noMinutesBody: {
    th: "ตรวจทานข้อความให้เรียบร้อยแล้วกดสร้างรายงาน",
    en: "Review the transcript, then generate the minutes from that screen.",
  },
  stepNormalizingHint: { th: "แปลงเป็น 16 kHz โมโน", en: "Converting to 16 kHz mono" },
  stepDiarizingHint: { th: "แยกว่าใครพูดช่วงไหน", en: "Working out who speaks when" },
  stepTranscribingHint: { th: "ถอดเสียงทีละช่วงการพูด", en: "Writing the transcript, turn by turn" },
  stepReviewHint: {
    th: "คุณตั้งชื่อผู้พูด แล้วจึงสร้างรายงาน",
    en: "You name the speakers, then generate minutes",
  },
} satisfies Record<string, Entry>;

export type StringKey = keyof typeof strings;

export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({
  lang: "th",
  setLang: () => {},
});

/** `{name}` placeholders, filled from a plain object. Thai and English put the
 *  same numbers in different places, so the order lives in the string. */
function fill(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in vars ? String(vars[key]) : match,
  );
}

export function useI18n() {
  const { lang, setLang } = useContext(LangContext);
  const t = (key: StringKey, vars?: Record<string, string | number>): string =>
    fill(strings[key][lang], vars);
  return { lang, setLang, t };
}

/** Seconds to h:mm:ss, or mm:ss when under an hour. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

/** `2026-11-17 14:05` in local time: the data style used in lists. */
export function formatIsoDateTime(iso: string): string {
  const date = new Date(iso.replace(" ", "T") + "Z");
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function formatDateTime(iso: string, lang: Lang): string {
  // The API stores UTC without a zone marker; make that explicit before parsing.
  const date = new Date(iso.replace(" ", "T") + "Z");
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(lang === "th" ? "th-TH" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
