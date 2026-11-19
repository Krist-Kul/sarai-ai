import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { MEETING_TYPES } from "../lib/meetingType";
import { AttendeeRows, fieldClass } from "../components/AttendeeRows";
import { ChipInput } from "../components/ChipInput";
import { Dropzone } from "../components/Dropzone";
import { Icon } from "../components/Icon";
import { Button, Card, Notice, PrivacyNote, Progress } from "../components/ui";
import type { Attendee, MeetingType } from "../types";

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

const STEPS = ["01 UPLOAD", "02 TRANSCRIBE", "03 REVIEW", "04 MINUTES"];

function Stepper() {
  return (
    <ol className="flex flex-wrap items-center gap-2">
      {STEPS.map((step, i) => (
        <li key={step} className="flex items-center gap-2">
          {i > 0 && <span aria-hidden className="h-px w-5 bg-line-control" />}
          <span
            aria-current={i === 0 ? "step" : undefined}
            className={`rounded-full border px-2.5 py-1 text-eyebrow ${
              i === 0 ? "border-brand bg-brand-soft text-brand-ink" : "border-line text-ink-subtle"
            }`}
          >
            {step}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Switch({
  checked,
  onChange,
  labelledBy,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  labelledBy: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-labelledby={labelledBy}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-10 shrink-0 cursor-pointer rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
        checked ? "bg-brand" : "bg-line-control"
      }`}
    >
      <span
        aria-hidden
        className={`absolute top-[3px] size-[18px] rounded-full bg-white transition-[left] ${
          checked ? "left-[19px]" : "left-[3px]"
        }`}
      />
    </button>
  );
}

/** "auto" leaves the type to the worker, which reads it from the transcript. */
type TypeChoice = MeetingType | "auto";

// Upload is the only step a person has to take. Everything below the file is
// optional: left alone, the worker detects the type, finds speaker names and
// writes the minutes; the meeting page follows it through to the PDF and .docx.
export function NewMeetingPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [meetingTime, setMeetingTime] = useState("");
  const [meetingType, setMeetingType] = useState<TypeChoice>("auto");
  const [autoSummarize, setAutoSummarize] = useState(true);
  const [glossary, setGlossary] = useState<string[]>([]);
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
        meetingType: meetingType === "auto" ? undefined : meetingType,
        autoSummarize,
        attendees: speakers.filter((a) => a.name.trim() !== ""),
        glossary,
        onProgress: setProgress,
      });
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      navigate(`/meetings/${created.meeting_id}`);
    },
  });

  const label = "text-small-strong text-ink";
  const typeChoices: { value: TypeChoice; key: Parameters<typeof t>[0] }[] = [
    { value: "auto", key: "typeAuto" },
    ...MEETING_TYPES,
  ];

  return (
    <form
      className="mx-auto flex max-w-[720px] flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (file && !upload.isPending) upload.mutate();
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Stepper />
        <h1 className="mt-2.5 text-[24px] leading-[34px] font-semibold tracking-[-0.3px] sm:text-display">
          {t("newMeeting")}
        </h1>
        <p className="text-[16px] leading-[28px] text-ink-muted">{t("autoNote")}</p>
      </div>

      <div className="flex flex-col gap-2.5">
        <Dropzone file={file} onSelect={setFile} />
        <PrivacyNote />
      </div>

      <Card className="flex flex-col gap-5 p-5 sm:p-6">
        <h2 className="text-[20px] leading-[30px] font-semibold tracking-[-0.1px]">
          {t("meetingDetails")}
        </h2>
        <div className="grid gap-4 sm:grid-cols-[1fr_220px]">
          <div className="flex flex-col gap-1.5">
            <label className={label} htmlFor="title">
              {t("title")}
            </label>
            <input
              id="title"
              className={`h-10 ${fieldClass}`}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={file ? baseName(file.name) : ""}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className={label} htmlFor="time">
              {t("dateTime")}
            </label>
            <input
              id="time"
              type="datetime-local"
              className={`h-10 ${fieldClass}`}
              value={meetingTime}
              onChange={(e) => setMeetingTime(e.target.value)}
            />
          </div>
        </div>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 flex flex-wrap items-baseline gap-x-2">
            <span className={label}>{t("meetingType")}</span>
            <span className="text-small text-ink-subtle">{t("meetingTypeHelp")}</span>
          </legend>
          <div className="flex flex-wrap gap-2">
            {typeChoices.map((choice) => {
              const active = meetingType === choice.value;
              return (
                <button
                  key={choice.value}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setMeetingType(choice.value)}
                  className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3.5 py-[5px] text-small-strong ${
                    active
                      ? "border-ink bg-ink text-on-ink"
                      : "border-line bg-surface-raised text-ink-muted hover:text-ink"
                  }`}
                >
                  {active && <Icon name="check-14" />}
                  {t(choice.key)}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="flex items-center gap-3 pt-1">
          <Switch
            checked={autoSummarize}
            onChange={setAutoSummarize}
            labelledBy="auto-summarize-label"
          />
          <div className="flex min-w-0 flex-col">
            <span id="auto-summarize-label" className={label}>
              {t("autoSummarize")}
            </span>
            <span className="text-small text-ink-muted">{t("autoSummarizeHelp")}</span>
          </div>
        </div>
      </Card>

      <Card className="flex flex-col gap-4 p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <h2 className="text-[20px] leading-[30px] font-semibold tracking-[-0.1px]">
              {t("helpTitle")}
            </h2>
            <p className="text-small text-ink-muted">{t("helpSubtitle")}</p>
          </div>
          <span className="shrink-0 rounded-full bg-surface-raised px-2.5 py-px text-small-strong text-ink-muted">
            {t("optional")}
          </span>
        </div>
        <label className={label} htmlFor="glossary">
          {t("glossary")}
        </label>
        <ChipInput id="glossary" values={glossary} onChange={setGlossary} />
        <hr className="border-line" />
        <span className={label}>{t("speakersOptional")}</span>
        <AttendeeRows values={speakers} onChange={setSpeakers} />
      </Card>

      {upload.isError && (
        <Notice tone="danger" inline>
          {upload.error instanceof ApiError ? upload.error.message : String(upload.error)}
        </Notice>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {upload.isPending ? (
          <Progress value={progress} className="min-w-48 flex-1" />
        ) : (
          <p className="min-w-48 flex-1 text-small text-ink-subtle">{t("speedNote")}</p>
        )}
        <Button variant="ghost" onClick={() => navigate("/")} disabled={upload.isPending}>
          {t("cancel")}
        </Button>
        <Button type="submit" icon="arrow-right" disabled={!file || upload.isPending}>
          {upload.isPending ? t("submitting") : t("submit")}
        </Button>
      </div>
    </form>
  );
}
