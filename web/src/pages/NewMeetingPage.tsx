import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { AttendeeRows } from "../components/AttendeeRows";
import { ChipInput } from "../components/ChipInput";
import { Dropzone } from "../components/Dropzone";
import type { Attendee, LanguageHint } from "../types";

const LANG_OPTIONS: { value: LanguageHint; key: "langAuto" | "langTh" | "langEn" }[] = [
  { value: "auto", key: "langAuto" },
  { value: "th", key: "langTh" },
  { value: "en", key: "langEn" },
];

export function NewMeetingPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [meetingDate, setMeetingDate] = useState("");
  const [languageHint, setLanguageHint] = useState<LanguageHint>("auto");
  const [attendees, setAttendees] = useState<Attendee[]>([{ name: "", role: null }]);
  const [glossary, setGlossary] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);

  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new ApiError("No file selected", 0);
      return api.createMeeting({
        file,
        title: title.trim() || file.name,
        meetingDate: meetingDate || undefined,
        languageHint,
        attendees: attendees.filter((a) => a.name.trim() !== ""),
        glossary,
        onProgress: setProgress,
      });
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      navigate(`/meetings/${created.meeting_id}`);
    },
  });

  const label = "block text-sm font-medium text-ink-900";
  const input =
    "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500";

  return (
    <form
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (file && !upload.isPending) upload.mutate();
      }}
    >
      <h1 className="text-xl font-semibold">{t("newMeeting")}</h1>

      <Dropzone file={file} onSelect={setFile} />

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={label} htmlFor="title">
            {t("title")}
          </label>
          <input
            id="title"
            className={input}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={file?.name ?? ""}
          />
        </div>
        <div>
          <label className={label} htmlFor="date">
            {t("date")}
          </label>
          <input
            id="date"
            type="date"
            className={input}
            value={meetingDate}
            onChange={(e) => setMeetingDate(e.target.value)}
          />
        </div>
      </div>

      <fieldset>
        <legend className={label}>{t("language")}</legend>
        <div className="mt-2 flex gap-2">
          {LANG_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setLanguageHint(option.value)}
              className={`rounded-lg border px-3 py-1.5 text-sm ${
                languageHint === option.value
                  ? "border-brand-600 bg-brand-50 text-brand-600"
                  : "border-slate-300 bg-white text-ink-600 hover:border-brand-500"
              }`}
            >
              {t(option.key)}
            </button>
          ))}
        </div>
      </fieldset>

      <div>
        <span className={label}>{t("attendees")}</span>
        <div className="mt-2">
          <AttendeeRows values={attendees} onChange={setAttendees} />
        </div>
      </div>

      <div>
        <span className={label}>{t("glossary")}</span>
        <p className="mt-1 mb-2 text-xs text-ink-600">{t("glossaryHelp")}</p>
        <ChipInput values={glossary} onChange={setGlossary} />
      </div>

      {upload.isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {upload.error instanceof ApiError ? upload.error.message : String(upload.error)}
        </div>
      )}

      {upload.isPending && (
        <div className="h-2 overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full bg-brand-600 transition-[width]"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>
      )}

      <button
        type="submit"
        disabled={!file || upload.isPending}
        className="rounded-lg bg-brand-600 px-5 py-2.5 font-medium text-white hover:bg-brand-500 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {upload.isPending ? t("submitting") : t("submit")}
      </button>
    </form>
  );
}
