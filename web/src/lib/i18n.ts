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
    th: "อัปโหลดไฟล์เสียงการประชุมเพื่อเริ่มถอดเสียงและสรุปรายงาน",
    en: "Upload a recording to transcribe it and draft the minutes.",
  },
  uploadCta: { th: "อัปโหลดไฟล์เสียง", en: "Upload audio" },
  title: { th: "หัวข้อการประชุม", en: "Meeting title" },
  date: { th: "วันที่ประชุม", en: "Meeting date" },
  language: { th: "ภาษา", en: "Language" },
  langAuto: { th: "ตรวจอัตโนมัติ", en: "Auto-detect" },
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
    th: "รองรับ mp3, m4a, wav, ogg, flac, mp4 — ไม่เกิน 500 MB",
    en: "mp3, m4a, wav, ogg, flac, mp4 — up to 500 MB",
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
} satisfies Record<string, Entry>;

export type StringKey = keyof typeof strings;

export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({
  lang: "th",
  setLang: () => {},
});

export function useI18n() {
  const { lang, setLang } = useContext(LangContext);
  const t = (key: StringKey): string => strings[key][lang];
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
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
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
