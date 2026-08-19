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
  const [helpOpen, setHelpOpen] = useState(true);

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
      <div className="flex flex-wrap items-center gap-3.5">
        <h1 className="text-2xl font-bold tracking-tight">{t("newMeeting")}</h1>
        <span className="text-[13px] text-ink-600">{t("uploadStep")}</span>
        {/* Four dashes for four steps: upload, transcribe, review, minutes.
            Only the first is on this screen; the rest live on the job page. */}
        <span className="ml-auto flex items-center gap-1.5" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <span
              key={i}
              className={`h-1.5 w-6 rounded-full ${i === 0 ? "bg-brand-600" : "bg-line"}`}
            />
          ))}
        </span>
      </div>

      <div className={card}>
        <Dropzone file={file} onSelect={setFile} />
      </div>

      <div className={card}>
        <h2 className="mb-3 text-[15px] font-bold">{t("meetingDetails")}</h2>
        <div className="grid gap-3.5 sm:grid-cols-[1fr_220px_200px]">
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
          <fieldset>
            <legend className={label}>{t("language")}</legend>
            <div className="mt-1.5 flex rounded-[10px] border border-line bg-canvas p-0.5">
              {LANG_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setLanguageHint(option.value)}
                  className={`flex-1 rounded-lg py-1.5 text-[13px] whitespace-nowrap ${
                    languageHint === option.value
                      ? "bg-surface font-semibold shadow-sm"
                      : "text-ink-600 hover:text-ink-900"
                  }`}
                >
                  {t(option.key)}
                </button>
              ))}
            </div>
          </fieldset>
        </div>
      </div>

      <div className={card}>
        <div className="flex flex-wrap items-baseline gap-2.5">
          <h2 className="text-[15px] font-bold">{t("helpTitle")}</h2>
          <span className="text-[12.5px] text-ink-600">{t("helpSubtitle")}</span>
          <button
            type="button"
            onClick={() => setHelpOpen((open) => !open)}
            className="ml-auto text-[12.5px] font-semibold text-brand-600 hover:underline"
          >
            {helpOpen ? t("hide") : t("show")}
          </button>
        </div>

        {helpOpen && (
          <div className="mt-3.5 grid gap-6 md:grid-cols-2">
            <div>
              <span className={label}>{t("attendees")}</span>
              <div className="mt-2">
                <AttendeeRows values={attendees} onChange={setAttendees} />
              </div>
            </div>
            <div>
              <span className={label}>{t("glossary")}</span>
              <p className="mt-1 mb-2 text-xs text-ink-400">{t("glossaryHelp")}</p>
              <ChipInput values={glossary} onChange={setGlossary} />
            </div>
          </div>
        )}
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
        <span className="text-[13px] text-ink-600">{t("submitNote")}</span>
      </div>
    </form>
  );
}
