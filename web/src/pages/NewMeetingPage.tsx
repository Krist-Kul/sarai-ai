import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { AttendeeRows } from "../components/AttendeeRows";
import { Dropzone } from "../components/Dropzone";
import type { Attendee } from "../types";

/** `2026-11-18T14:30` from <input type="datetime-local"> -> `2026-11-18 14:30`,
 * which is how it reads in the minutes. */
function formatMeetingTime(value: string): string | undefined {
  return value ? value.replace("T", " ") : undefined;
}

/** `weekly sync.mp4` -> `weekly sync`: the default title, without the extension. */
function baseName(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

// Upload is the only step a person takes. Language, meeting type, speaker
// names and the summary are all worked out by the worker; the meeting page
// follows it through to the PDF and .docx.
export function NewMeetingPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [meetingTime, setMeetingTime] = useState("");
  const [speakers, setSpeakers] = useState<Attendee[]>([]);
  const [progress, setProgress] = useState(0);

  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new ApiError("No file selected", 0);
      return api.createMeeting({
        file,
        title: title.trim() || baseName(file.name),
        meetingDate: formatMeetingTime(meetingTime),
        languageHint: "auto",
        autoSummarize: true,
        attendees: speakers.filter((a) => a.name.trim() !== ""),
        onProgress: setProgress,
      });
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      navigate(`/meetings/${created.meeting_id}`);
    },
  });

  const label = "text-[12.5px] font-semibold text-ink-600";
  const input =
    "mt-1.5 w-full rounded-[10px] border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand-600";
  const card = "rounded-2xl border border-line bg-surface p-5";

  return (
    <form
      className="mx-auto max-w-4xl space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (file && !upload.isPending) upload.mutate();
      }}
    >
      <h1 className="text-2xl font-bold tracking-tight">{t("newMeeting")}</h1>

      <div className={card}>
        <Dropzone file={file} onSelect={setFile} />
      </div>

      <div className={card}>
        <h2 className="mb-3 text-[15px] font-bold">{t("meetingDetails")}</h2>
        <div className="grid gap-3.5 sm:grid-cols-[1fr_240px]">
          <div>
            <label className={label} htmlFor="title">
              {t("title")}
            </label>
            <input
              id="title"
              className={input}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={file ? baseName(file.name) : ""}
            />
          </div>
          <div>
            <label className={label} htmlFor="time">
              {t("dateTime")}
            </label>
            <input
              id="time"
              type="datetime-local"
              className={input}
              value={meetingTime}
              onChange={(e) => setMeetingTime(e.target.value)}
            />
          </div>
        </div>

        <div className="mt-4">
          <span className={label}>{t("speakersOptional")}</span>
          <p className="mt-1 mb-2 text-xs text-ink-400">{t("speakersOptionalHelp")}</p>
          <AttendeeRows values={speakers} onChange={setSpeakers} />
        </div>
      </div>

      {upload.isError && (
        <div className="rounded-xl border border-bad-line bg-bad-50 p-3 text-sm text-bad-600">
          {upload.error instanceof ApiError ? upload.error.message : String(upload.error)}
        </div>
      )}

      {upload.isPending && (
        <div className="h-1.5 overflow-hidden rounded-full bg-sand">
          <div
            className="h-full rounded-full bg-brand-600 transition-[width]"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3.5">
        <button
          type="submit"
          disabled={!file || upload.isPending}
          className="rounded-full bg-brand-600 px-6 py-2.5 text-[14.5px] font-bold text-white hover:bg-brand-600/90 disabled:cursor-not-allowed disabled:bg-ink-200"
        >
          {upload.isPending ? t("submitting") : t("submit")}
        </button>
        <span className="text-[13px] text-ink-600">{t("autoNote")}</span>
      </div>
    </form>
  );
}
